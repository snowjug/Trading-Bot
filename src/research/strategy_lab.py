"""
Strategy simulator and money accounting for candidate search.

ONE engine, reused by every candidate, so results are comparable and a difference
between two candidates is a difference in the RULES rather than in the harness.

EXECUTION MODEL — deliberately conservative, and the same for every candidate.
No historical bid/ask exists in this repository, so a traded price is NOT treated
as an achievable fill. Each side pays:

    half-spread  = max(1 tick, SPREAD_PCT x premium)
    slippage     = SLIP_TICKS x tick

Observed live NIFTY ATM spreads on 2026-09-18 were ~0.22% of mid (90.65 / 90.85),
so SPREAD_PCT = 0.30% is roughly 1.4x the observed half-spread on each side, and
the fixed slippage is charged on top. Statutory costs come from IndianCostModel.

SPLITS. Development, validation and holdout are separate by construction. A
candidate is built and tuned only on DEV, checked once on VAL, and measured on
HOLDOUT exactly once, frozen.

CAUSALITY. At decision bar i the simulator exposes only bars up to i of the current
session plus daily sessions strictly before it. Forward bars are used only to
resolve an exit that the rules already committed to.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import date, time as dtime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel

TICK = 0.05
SPREAD_PCT = 0.0030          # each side, on top of the traded price
SLIP_TICKS = 2               # 0.10 points of additional adverse fill per side
LOT = 65

DEV_END = pd.Timestamp("2024-12-31").date()
VAL_END = pd.Timestamp("2026-06-17").date()
HOLDOUT_START = pd.Timestamp("2026-06-18").date()


def buy_fill(px: float) -> float:
    """A buy pays up: traded price + half-spread + slippage."""
    return round(px * (1 + SPREAD_PCT) + SLIP_TICKS * TICK, 2)


def sell_fill(px: float) -> float:
    """A sell receives less: traded price - half-spread - slippage."""
    return round(max(TICK, px * (1 - SPREAD_PCT) - SLIP_TICKS * TICK), 2)


@dataclass
class Trade:
    bot: str
    sess: date
    entry_time: str
    exit_time: str
    option_type: str
    strike: float
    qty: int
    entry_px: float          # traded price at entry
    entry_fill: float        # what we actually paid
    exit_px: float
    exit_fill: float
    entry_spot: float
    exit_spot: float
    gross: float
    costs: float
    net: float
    capital: float           # premium actually outlaid
    exit_reason: str
    mfe: float = 0.0
    mae: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Spec:
    """A candidate's rules. Every field is an explicit decision, nothing implicit."""
    name: str
    signal: Callable         # (ctx) -> int   +1 long CE, -1 long PE, 0 none
    target_atr: float        # take profit at this much favourable SPOT movement
    stop_atr: float          # stop at this much adverse SPOT movement
    trail_atr: Optional[float] = None       # arm trail after this much favourable
    trail_give_atr: Optional[float] = None  # then give back at most this much
    entry_from: dtime = dtime(9, 45)
    entry_to: dtime = dtime(14, 30)
    flat_at: dtime = dtime(15, 10)
    max_trades_per_day: int = 1
    strike_offset: int = 0                  # 0 = ATM, +1 = one strike OTM etc.
    max_hold_bars: Optional[int] = None
    notes: str = ""


# ───────────────────────────── DATA ─────────────────────────────

def daily_frame() -> pd.DataFrame:
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    c = d["close"]
    prev = c.shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev).abs(),
                    (d["low"] - prev).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    d["ema9"] = c.ewm(span=9, adjust=False).mean()
    d["ema21"] = c.ewm(span=21, adjust=False).mean()
    d["ema50"] = c.ewm(span=50, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi14"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    d["sess"] = d["datetime"].dt.date
    return d


def index_grid(grid: Dict[str, pd.DataFrame]) -> Dict[str, Dict[date, pd.DataFrame]]:
    return {s: {k: v for k, v in grid[s].groupby(grid[s]["datetime"].dt.date, sort=False)}
            for s in ("ce", "pe")}


@dataclass
class Ctx:
    """Everything a signal may legally see at the decision bar."""
    t: dtime
    i: int
    spot: float
    path: np.ndarray         # session spots up to and including i
    atr: float
    open_px: float
    prev_close: float
    prev_high: float
    prev_low: float
    or_hi: float
    or_lo: float
    vix: float
    rsi: float
    ema_stack: int
    sess: date

    @property
    def twap(self) -> float:
        return float(self.path.mean())

    @property
    def sess_hi(self) -> float:
        return float(self.path.max())

    @property
    def sess_lo(self) -> float:
        return float(self.path.min())

    def z(self, x: float) -> float:
        return x / self.atr if self.atr else 0.0


# ───────────────────────────── SIMULATION ─────────────────────────────

def simulate(spec: Spec, sessions: List[date], daily: pd.DataFrame,
             by_day: Dict[str, Dict[date, pd.DataFrame]],
             skips: Optional[Dict[str, int]] = None) -> List[Trade]:
    skips = skips if skips is not None else {}
    dpos = {d: i for i, d in enumerate(daily["sess"])}
    trades: List[Trade] = []

    def bump(k: str) -> None:
        skips[k] = skips.get(k, 0) + 1

    for sess in sessions:
        if sess not in dpos or dpos[sess] < 60:
            bump("NO_PRIOR_HISTORY"); continue
        prior = daily.iloc[dpos[sess] - 1]
        atr = float(prior["atr14"])
        if not np.isfinite(atr) or atr <= 0:
            bump("NO_ATR"); continue
        dce = by_day["ce"].get(sess)
        dpe = by_day["pe"].get(sess)
        if dce is None or dpe is None:
            bump("NO_OPTION_DATA"); continue

        sp = dce.groupby("datetime")["spot"].first().sort_index()
        sp = sp[(sp.index.time >= dtime(9, 15)) & (sp.index.time <= dtime(15, 25))]
        if len(sp) < 40:
            bump("SHORT_SESSION"); continue
        vals = sp.values.astype(float)
        stamps = list(sp.index)
        times = [t.time() for t in stamps]
        or_mask = [t <= dtime(9, 45) for t in times]
        or_hi = float(np.max(vals[or_mask])) if any(or_mask) else np.nan
        or_lo = float(np.min(vals[or_mask])) if any(or_mask) else np.nan

        taken = 0
        i = 0
        while i < len(vals):
            if taken >= spec.max_trades_per_day:
                break
            t = times[i]
            if t < spec.entry_from or t > spec.entry_to:
                i += 1; continue

            ctx = Ctx(t=t, i=i, spot=float(vals[i]), path=vals[:i + 1], atr=atr,
                      open_px=float(vals[0]), prev_close=float(prior["close"]),
                      prev_high=float(prior["high"]), prev_low=float(prior["low"]),
                      or_hi=or_hi, or_lo=or_lo, vix=float(prior["vix"]),
                      rsi=float(prior["rsi14"]),
                      ema_stack=(1 if prior["ema9"] > prior["ema21"] > prior["ema50"]
                                 else (-1 if prior["ema9"] < prior["ema21"] < prior["ema50"] else 0)),
                      sess=sess)
            try:
                direction = int(spec.signal(ctx))
            except Exception:                                   # noqa: BLE001
                direction = 0
            if direction == 0:
                i += 1; continue

            side = "ce" if direction > 0 else "pe"
            dg = dce if direction > 0 else dpe
            ts = stamps[i]
            at = dg[dg["datetime"] == ts]
            if at.empty:
                bump("NO_OPTION_BAR_AT_ENTRY"); i += 1; continue
            atm = round(ctx.spot / 50.0) * 50.0
            want = atm + spec.strike_offset * 50.0 * (1 if direction > 0 else -1)
            cand = at.iloc[(at["strike"] - want).abs().argsort()]
            row = cand.iloc[0]
            if abs(float(row["strike"]) - want) > 50.0:
                bump("STRIKE_NOT_AVAILABLE"); i += 1; continue
            strike = float(row["strike"])
            entry_px = float(row["close"])
            if entry_px <= 0:
                bump("ZERO_OPTION_PRICE"); i += 1; continue

            leg = dg[(dg["strike"] == strike) & (dg["datetime"] >= ts)].sort_values("datetime")
            if len(leg) < 2:
                bump("CONTRACT_NOT_QUOTED_FORWARD"); i += 1; continue

            e_fill = buy_fill(entry_px)
            capital = round(e_fill * LOT, 2)
            tgt = spec.target_atr * atr
            stp = spec.stop_atr * atr
            trail_on = spec.trail_atr * atr if spec.trail_atr else None
            trail_gb = spec.trail_give_atr * atr if spec.trail_give_atr else None

            peak_fav = 0.0
            mfe = mae = 0.0
            exit_row = None
            reason = "EOD"
            bars = 0
            for k in range(1, len(leg)):
                b = leg.iloc[k]
                bt = b["datetime"].time()
                bars += 1
                move = (float(b["spot"]) - ctx.spot) * direction
                peak_fav = max(peak_fav, move)
                # option-level excursion for reporting
                m = (float(b["close"]) - e_fill) * LOT
                mfe = max(mfe, m); mae = min(mae, m)
                if move <= -stp:
                    exit_row, reason = b, "STOP"; break
                if move >= tgt:
                    exit_row, reason = b, "TARGET"; break
                if trail_on and trail_gb and peak_fav >= trail_on and move <= peak_fav - trail_gb:
                    exit_row, reason = b, "TRAIL"; break
                if spec.max_hold_bars and bars >= spec.max_hold_bars:
                    exit_row, reason = b, "TIME"; break
                if bt >= spec.flat_at:
                    exit_row, reason = b, "EOD"; break
            if exit_row is None:
                exit_row, reason = leg.iloc[-1], "SESSION_END"

            exit_px = float(exit_row["close"])
            x_fill = sell_fill(exit_px)
            gross = round((x_fill - e_fill) * LOT, 2)
            costs = round(IndianCostModel.calculate_roundtrip_costs(
                e_fill, x_fill, LOT).total_costs, 2)
            trades.append(Trade(
                bot=spec.name, sess=sess, entry_time=str(t),
                exit_time=str(exit_row["datetime"].time()),
                option_type="CE" if direction > 0 else "PE", strike=strike, qty=LOT,
                entry_px=entry_px, entry_fill=e_fill, exit_px=exit_px, exit_fill=x_fill,
                entry_spot=ctx.spot, exit_spot=float(exit_row["spot"]),
                gross=gross, costs=costs, net=round(gross - costs, 2),
                capital=capital, exit_reason=reason,
                mfe=round(mfe, 2), mae=round(mae, 2),
                meta={"atr": round(atr, 1), "vix": round(ctx.vix, 2)},
            ))
            taken += 1
            # resume scanning after the exit bar, so trades never overlap
            nxt = [j for j, s in enumerate(stamps) if s > exit_row["datetime"]]
            i = nxt[0] if nxt else len(vals)
    return trades


# ───────────────────────────── METRICS ─────────────────────────────

def money_metrics(trades: List[Trade], sessions: List[date],
                  account: float = 100000.0) -> Dict[str, Any]:
    n_sessions = len(sessions)
    if not trades:
        return {"trades": 0, "sessions": n_sessions, "net": 0.0, "note": "no trades"}
    df = pd.DataFrame([t.__dict__ for t in trades])
    net = df["net"].astype(float)
    wins, losses = net[net > 0], net[net <= 0]
    eq = net.cumsum()
    dd = float((eq - eq.cummax()).min())

    streak = mx_streak = 0
    for x in net:
        if x <= 0:
            streak += 1; mx_streak = max(mx_streak, streak)
        else:
            streak = 0

    daily = df.groupby("sess")["net"].sum()
    cap_daily = df.groupby("sess")["capital"].max()          # peak capital that day
    daily_ret = (daily / cap_daily.replace(0, np.nan) * 100).dropna()

    return {
        "trades": int(len(df)), "wins": int(len(wins)), "losses": int(len(losses)),
        "win_rate": round(float(len(wins) / len(df) * 100), 1),
        "gross": round(float(df["gross"].sum()), 2),
        "costs": round(float(df["costs"].sum()), 2),
        "net": round(float(net.sum()), 2),
        "capital_deployed": round(float(df["capital"].sum()), 2),
        "avg_capital": round(float(df["capital"].mean()), 2),
        "max_capital": round(float(df["capital"].max()), 2),
        "ret_on_deployed": round(float(net.sum() / df["capital"].sum() * 100), 2),
        "ret_on_max_capital": round(float(net.sum() / df["capital"].max() * 100), 2),
        "ret_on_account": round(float(net.sum() / account * 100), 2),
        "avg_trade": round(float(net.mean()), 2),
        "median_trade": round(float(net.median()), 2),
        "expectancy": round(float(net.mean()), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and losses.sum() != 0 else None,
        "max_dd": round(abs(dd), 2),
        "max_losing_streak": int(mx_streak),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else None,
        "best_day": f"{daily.idxmax()} {daily.max():+,.0f}",
        "worst_day": f"{daily.idxmin()} {daily.min():+,.0f}",
        "profitable_days": int((daily > 0).sum()),
        "losing_days": int((daily <= 0).sum()),
        "no_trade_days": int(n_sessions - daily.shape[0]),
        "sessions": n_sessions,
        "pct_sessions_traded": round(float(daily.shape[0] / n_sessions * 100), 1),
        "trades_per_day": round(float(len(df) / n_sessions), 2),
        "avg_daily_ret_pct": round(float(daily_ret.mean()), 3) if len(daily_ret) else None,
        "median_daily_ret_pct": round(float(daily_ret.median()), 3) if len(daily_ret) else None,
        "pct_days_ge_1pct": round(float((daily_ret >= 1).mean() * 100), 1) if len(daily_ret) else None,
        "pct_days_ge_2pct": round(float((daily_ret >= 2).mean() * 100), 1) if len(daily_ret) else None,
        "pct_days_le_m1pct": round(float((daily_ret <= -1).mean() * 100), 1) if len(daily_ret) else None,
        "pct_days_le_m2pct": round(float((daily_ret <= -2).mean() * 100), 1) if len(daily_ret) else None,
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
    }


def tstat(trades: List[Trade]) -> float:
    if len(trades) < 3:
        return 0.0
    a = np.array([t.net for t in trades], dtype=float)
    sd = a.std(ddof=1)
    return float(a.mean() / (sd / np.sqrt(len(a)))) if sd else 0.0


def split_sessions(all_sessions: List[date]) -> Tuple[List[date], List[date], List[date]]:
    dev = [d for d in all_sessions if d <= DEV_END]
    val = [d for d in all_sessions if DEV_END < d <= VAL_END]
    hold = [d for d in all_sessions if d >= HOLDOUT_START]
    return dev, val, hold


def line(name: str, m: Dict[str, Any], t: float = None) -> str:
    if m.get("trades", 0) == 0:
        return f"{name:28s} NO TRADES ({m.get('sessions', 0)} sessions)"
    return (f"{name:28s} n={m['trades']:>4} win={m['win_rate']:>5.1f}% "
            f"net={m['net']:>10,.0f} exp={m['expectancy']:>8,.0f} "
            f"pf={str(m['profit_factor']):>6} dd={m['max_dd']:>9,.0f} "
            f"ret/dep={m['ret_on_deployed']:>6.2f}% "
            f"trd/day={m['trades_per_day']:>4.2f}"
            + (f" t={t:+.2f}" if t is not None else ""))
