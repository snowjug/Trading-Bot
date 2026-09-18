"""
Bot 7 — autonomous strategy discovery.

Each candidate here is implemented EXACTLY as `reports/BOT7_RESEARCH_LEDGER.md`
specified it before any result was seen. Nothing is tuned after the fact. Failed
candidates are kept, not deleted.

Every candidate is priced on authentic data:
  * intraday candidates on the 5-minute NIFTY option grid (real strike, real spot,
    real OHLC), holding ONE fixed contract chosen at entry
  * the spread candidate on NSE bhavcopy option prices with cash settlement at
    expiry against the exchange's official settlement price

Shared limits, stated not hidden: no bid/ask history exists here, so fills are at
traded prices and every result is stress-tested for slippage rather than assumed
clean. Lot size is held at the current 65 for comparability.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import date, time as dtime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel
from src.research.bot1_condor_real import condor_leg_costs
from src.utils.logging import setup_logging

logger = setup_logging("research.bot7")

LOT = 65
EOD_FLAT = dtime(15, 15)
OPEN_TIME = dtime(9, 15)
EXECUTION_BASIS = "TRADED_PRICE_NO_BIDASK"


@dataclass
class Trade:
    candidate: str
    date: str
    direction: int                 # +1 long call, -1 long put
    option_type: str
    strike: float
    entry_time: str
    exit_time: str
    entry_spot: float
    exit_spot: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    costs: float
    net_pnl: float
    reason: str
    execution_basis: str = EXECUTION_BASIS


# ────────────────────── SHARED INTRADAY OPTION EXECUTION ──────────────────────

def index_by_session(bars: Dict[str, pd.DataFrame]) -> Dict[str, Dict[Any, pd.DataFrame]]:
    """Group the grid by session once; the loops below would otherwise rescan ~1.5M rows."""
    return {
        side: {k: v for k, v in bars[side].groupby(bars[side]["datetime"].dt.date, sort=False)}
        for side in ("ce", "pe")
    }


def spot_path(day_grid: pd.DataFrame) -> pd.DataFrame:
    """One spot observation per timestamp — spot is common to every strike."""
    return day_grid.groupby("datetime")["spot"].first().sort_index().reset_index()


def buy_option_at(day_grid: pd.DataFrame, ts: pd.Timestamp, spot: float
                  ) -> Optional[Tuple[float, float]]:
    """
    Fix the ATM contract at this instant and return (strike, price).

    The strike is chosen ONCE, at entry, and the caller then follows that same
    strike. This is what stops the rolling-ATM label silently swapping the contract
    underneath an open position.
    """
    at = day_grid[day_grid["datetime"] == ts]
    if at.empty:
        return None
    row = at.iloc[(at["strike"] - spot).abs().argsort()].iloc[0]
    price = float(row["close"])
    return (float(row["strike"]), price) if price > 0 else None


def hold_to(day_grid: pd.DataFrame, strike: float, entry_ts: pd.Timestamp,
            flat_at: dtime = EOD_FLAT) -> Optional[pd.Series]:
    """Follow ONE contract forward and return the bar it is closed on."""
    leg = (day_grid[(day_grid["strike"] == strike) & (day_grid["datetime"] >= entry_ts)]
           .sort_values("datetime").reset_index(drop=True))
    if len(leg) < 2:
        return None                      # not continuously quoted — fail closed
    for k in range(1, len(leg)):
        if leg.iloc[k]["datetime"].time() >= flat_at:
            return leg.iloc[k]
    return leg.iloc[-1]


def long_option_costs(entry: float, exit_: float, qty: int = LOT) -> float:
    """Round trip for a bought option: both sides are real orders."""
    return IndianCostModel.calculate_roundtrip_costs(entry, exit_, qty).total_costs


def _make_trade(cand: str, sess, direction: int, day_grid: pd.DataFrame,
                entry_ts, entry_spot: float, reason: str) -> Optional[Trade]:
    got = buy_option_at(day_grid, entry_ts, entry_spot)
    if got is None:
        return None
    strike, entry_price = got
    exit_row = hold_to(day_grid, strike, entry_ts)
    if exit_row is None:
        return None
    exit_price = float(exit_row["close"])
    gross = (exit_price - entry_price) * LOT
    costs = long_option_costs(entry_price, exit_price)
    return Trade(
        candidate=cand, date=str(sess), direction=direction,
        option_type="CE" if direction > 0 else "PE", strike=strike,
        entry_time=str(pd.Timestamp(entry_ts).time()),
        exit_time=str(exit_row["datetime"].time()),
        entry_spot=entry_spot, exit_spot=float(exit_row["spot"]),
        entry_price=entry_price, exit_price=exit_price,
        gross_pnl=round(gross, 2), costs=round(costs, 2),
        net_pnl=round(gross - costs, 2), reason=reason,
    )


# ────────────────────────────── C1: OVERNIGHT GAP ──────────────────────────────

def c1_overnight_gap(daily: pd.DataFrame, bars: Dict[str, pd.DataFrame],
                     pct: float = 0.80, lookback: int = 60) -> List[Trade]:
    """
    Ledger C1. Trade the open in the direction of a large overnight gap; flat at the
    close.

    The threshold is a TRAILING percentile computed strictly from sessions before t,
    so nothing about day t's own distribution is used to decide day t's trade.
    """
    d = daily.sort_values("datetime").reset_index(drop=True).copy()
    d["sess"] = d["datetime"].dt.date
    d["gap"] = d["open"] / d["close"].shift(1) - 1.0
    d["abs_gap"] = d["gap"].abs()
    # shift(1) on the rolling quantile: the threshold uses only prior sessions.
    d["thresh"] = d["abs_gap"].rolling(lookback, min_periods=30).quantile(pct).shift(1)

    by_day = index_by_session(bars)
    out: List[Trade] = []
    for i in range(len(d)):
        row = d.iloc[i]
        if not np.isfinite(row["gap"]) or not np.isfinite(row["thresh"]):
            continue
        if row["abs_gap"] < row["thresh"] or row["gap"] == 0:
            continue
        direction = 1 if row["gap"] > 0 else -1
        side = "ce" if direction > 0 else "pe"
        dg = by_day[side].get(row["sess"])
        if dg is None or dg.empty:
            continue
        sp = spot_path(dg)
        first = sp[sp["datetime"].dt.time >= OPEN_TIME]
        if first.empty:
            continue
        b = first.iloc[0]
        t = _make_trade("C1_overnight_gap", row["sess"], direction, dg,
                        b["datetime"], float(b["spot"]), "EOD")
        if t:
            out.append(t)
    return out


# ───────────────────────── C2: VOLATILITY CONTRACTION ─────────────────────────

def c2_nr_breakout(daily: pd.DataFrame, bars: Dict[str, pd.DataFrame],
                   n: int = 7) -> List[Trade]:
    """
    Ledger C2. After the narrowest range in `n` sessions, trade the break of that
    day's range on the following session; flat at the close.
    """
    d = daily.sort_values("datetime").reset_index(drop=True).copy()
    d["sess"] = d["datetime"].dt.date
    d["range"] = d["high"] - d["low"]
    d["is_nr"] = d["range"] == d["range"].rolling(n).min()

    by_day = index_by_session(bars)
    out: List[Trade] = []
    for i in range(n, len(d) - 1):
        if not bool(d.iloc[i]["is_nr"]):
            continue
        hi, lo = float(d.iloc[i]["high"]), float(d.iloc[i]["low"])
        nxt = d.iloc[i + 1]
        for side, direction, cond in (("ce", 1, "up"), ("pe", -1, "down")):
            dg = by_day[side].get(nxt["sess"])
            if dg is None or dg.empty:
                continue
            sp = spot_path(dg)
            hit = sp[sp["spot"] > hi] if direction > 0 else sp[sp["spot"] < lo]
            if hit.empty:
                continue
            b = hit.iloc[0]
            t = _make_trade(f"C2_nr{n}_breakout", nxt["sess"], direction, dg,
                            b["datetime"], float(b["spot"]), "EOD")
            if t:
                out.append(t)
            break                       # first break of the day only
    return out


# ────────────────────────── C4: OPENING-RANGE BREAK ──────────────────────────

def c4_opening_range(daily: pd.DataFrame, bars: Dict[str, pd.DataFrame],
                     minutes: int = 30) -> List[Trade]:
    """
    Ledger C4. Break of the first `minutes` of the session, taken after that window
    closes; flat at 15:15.
    """
    cutoff = (pd.Timestamp("2000-01-01 09:15") + pd.Timedelta(minutes=minutes)).time()
    by_day = index_by_session(bars)
    sessions = sorted(set(by_day["ce"]) & set(by_day["pe"]))
    out: List[Trade] = []
    for sess in sessions:
        dg_ce, dg_pe = by_day["ce"][sess], by_day["pe"][sess]
        sp = spot_path(dg_ce)
        opening = sp[sp["datetime"].dt.time < cutoff]
        rest = sp[sp["datetime"].dt.time >= cutoff]
        if len(opening) < 3 or rest.empty:
            continue
        hi, lo = float(opening["spot"].max()), float(opening["spot"].min())
        for _, b in rest.iterrows():
            if b["spot"] > hi:
                direction, dg = 1, dg_ce
            elif b["spot"] < lo:
                direction, dg = -1, dg_pe
            else:
                continue
            t = _make_trade("C4_opening_range", sess, direction, dg,
                            b["datetime"], float(b["spot"]), "EOD")
            if t:
                out.append(t)
            break
    return out


# ───────────────────── C3: VIX-CONDITIONED VERTICAL SPREAD ─────────────────────

@dataclass
class SpreadTrade:
    candidate: str
    entry_date: str
    expiry: str
    side: str                       # CE (bear call) or PE (bull put)
    short_strike: float
    long_strike: float
    short_entry: float
    long_entry: float
    credit_points: float
    width: float
    settle: float
    loss_points: float
    costs_points: float
    net_points: float
    vix_z: float
    execution_basis: str = "EXCHANGE_CLOSE_ENTRY_SETTLEMENT_EXIT_NO_BIDASK"


def c3_vix_spread(daily: pd.DataFrame, store: pd.DataFrame, otm_sd: float = 1.0,
                  wing_steps: int = 4, z_threshold: float = 1.0,
                  hold_sessions: int = 5, strike_step: float = 50.0) -> List[SpreadTrade]:
    """
    Ledger C3. When VIX sits high relative to its own 60-session history, sell a
    defined-risk vertical 1 SD out of the money and hold it to expiry.

    Direction: a high-VIX reading says implied volatility is rich, not which way the
    market will go, so the side is chosen by which short strike the spot is further
    from — the structurally safer of the two. That rule is fixed here and never
    varied by outcome.

    Both legs must exist AND have traded, or the cycle is skipped. Exit is exact
    cash settlement against the exchange's official settlement price. Costs are
    side-aware (sell-side STT on the premium received; exercise STT on an ITM long).
    """
    from src.research.bot1_condor_real import ChainIndex, weekly_expiry_calendar

    d = daily.sort_values("datetime").reset_index(drop=True).copy()
    d["sess"] = d["datetime"].dt.date
    mu = d["vix"].rolling(60).mean().shift(1)
    sd = d["vix"].rolling(60).std().shift(1)
    d["vix_z"] = (d["vix"] - mu) / sd

    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    index_close = dict(zip(d["sess"], d["close"].astype(float)))
    pos = {v: k for k, v in enumerate(d["sess"])}

    out: List[SpreadTrade] = []
    used: set = set()
    for i in range(len(d)):
        sess = d.loc[i, "sess"]
        z = d.loc[i, "vix_z"]
        if not np.isfinite(z) or z < z_threshold:
            continue
        nxt = [e for e in expiries if e > sess]
        if not nxt:
            continue
        expiry = nxt[0]
        if expiry in used:
            continue
        ep = pos.get(expiry)
        if ep is None or ep - i != hold_sessions:
            continue
        settle = chains.settlement(expiry, index_close)
        if settle is None:
            continue

        spot = float(d.loc[i, "close"])
        vix = float(d.loc[i, "vix"])
        exp_move = spot * (vix / 100.0) * np.sqrt(5.0 / 365.0)
        call_k = round((spot + otm_sd * exp_move) / strike_step) * strike_step
        put_k = round((spot - otm_sd * exp_move) / strike_step) * strike_step
        # Safer side: the short strike the spot sits further away from.
        if (call_k - spot) >= (spot - put_k):
            side, short_k, long_k = "CE", call_k, call_k + wing_steps * strike_step
        else:
            side, short_k, long_k = "PE", put_k, put_k - wing_steps * strike_step

        chain = chains.chain(sess, expiry)
        if chain.empty:
            continue
        legs = {}
        ok = True
        for role, k in (("short", short_k), ("long", long_k)):
            r = chain[(chain["StrkPric"] == k) & (chain["OptnTp"] == side)]
            if r.empty or int(r.iloc[0]["TtlTradgVol"]) <= 0 or float(r.iloc[0]["ClsPric"]) <= 0:
                ok = False
                break
            legs[role] = float(r.iloc[0]["ClsPric"])
        if not ok:
            continue

        credit = legs["short"] - legs["long"]
        width = abs(long_k - short_k)
        intr_s = max(0.0, settle - short_k) if side == "CE" else max(0.0, short_k - settle)
        intr_l = max(0.0, settle - long_k) if side == "CE" else max(0.0, long_k - settle)
        loss = min(max(0.0, intr_s - intr_l), width)
        costs_pts = (condor_leg_costs("SELL", legs["short"], intr_s, LOT)
                     + condor_leg_costs("BUY", legs["long"], intr_l, LOT)) / LOT

        used.add(expiry)
        out.append(SpreadTrade(
            candidate="C3_vix_vertical", entry_date=str(sess), expiry=str(expiry),
            side=side, short_strike=short_k, long_strike=long_k,
            short_entry=legs["short"], long_entry=legs["long"],
            credit_points=round(credit, 2), width=width, settle=settle,
            loss_points=round(loss, 2), costs_points=round(costs_pts, 2),
            net_points=round(credit - loss - costs_pts, 2), vix_z=float(z),
        ))
    return out


# ─────────────────────────────── SUMMARY ───────────────────────────────

def summarise(trades: List[Trade], initial_capital: float = 100000.0) -> Dict[str, Any]:
    if not trades:
        return {"total_trades": 0, "note": "no trades", "execution_basis": EXECUTION_BASIS}
    df = pd.DataFrame([t.__dict__ for t in trades])
    eq = initial_capital + df["net_pnl"].cumsum()
    dd = ((eq - eq.cummax()) / eq.cummax()).min()
    return {
        "total_trades": int(len(df)),
        "net_profit": float(df["net_pnl"].sum()),
        "gross_profit": float(df["gross_pnl"].sum()),
        "total_costs": float(df["costs"].sum()),
        "win_rate": float((df["net_pnl"] > 0).mean() * 100),
        "expectancy": float(df["net_pnl"].mean()),
        "max_drawdown_pct": float(abs(dd) * 100) if pd.notna(dd) else 0.0,
        "sessions": int(df["date"].nunique()),
        "avg_entry_price": float(df["entry_price"].mean()),
        "execution_basis": EXECUTION_BASIS,
    }
