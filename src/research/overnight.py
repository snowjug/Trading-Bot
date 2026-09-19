"""
OVERNIGHT — close-to-open engine for NIFTY option structures.

MECHANISM BEING TESTED. On the DEV window the NIFTY index earns +0.135% per night
between the close and the next open (t = 7.02, 68.6% of nights positive, positive
in each of six years) while the regular session between the open and the close is
NEGATIVE at -0.068% (t = -2.72). Every strategy previously tested in this
repository was flat by 15:15 and therefore held exposure only during the one
segment of the day that loses money. This module holds exposure only during the
other one.

WHY THE PRICES COME FROM TWO SOURCES. Neither source alone is honest here.

  ENTRY — the 5-minute grid's last print at 15:25. It is an authentic traded
  price. The bhavcopy `ClsPric` is NOT the closing print: it is NSE's weighted
  average of the last thirty minutes, and it sits a measured +0.80 points above
  the 15:2x print for puts (median, n=19,828). Selling at it would hand a short
  put 0.8 points of premium that nobody could have received.

  EXIT — the 09:15 grid BAR CLOSE, i.e. the price five minutes into the session,
  with the bhavcopy `OpnPric` used only when the grid cannot price the strike.
  The opening print itself is NOT used as the primary venue, and the reason is
  worth stating because it reverses a result: a long ATM+1 call exited at the
  bhavcopy opening print earns +3.49 points a night on DEV (t = 3.42), and the
  identical trade exited five minutes later loses -1.31 (t = -0.87). The whole
  apparent edge was the first print of the day being struck above where the
  contract actually traded moments later. Anything that needs the opening print
  to work does not work.

  The 5-minute grid is truncated to ATM+/-6, so on a big gap the strike held
  overnight can fall out of the next morning's ladder. Those
  are not random nights: measured over 786 DEV pairs, the nights dropped by the
  ladder moved the index by -185 to -279 points on average against +19 to +26 for
  the nights that survived, with a mean |move| of 289-391 points against 63-67.
  Pricing the exit from the grid therefore deletes precisely the gap-down nights
  a short put loses on -- the same silent-skip artefact that produced this
  repository's fake +Rs 456,653 short straddle. The bhavcopy carries every strike
  ever listed, so those nights are priced from it rather than dropped, and every
  night that uses the fallback is counted and reported. It was cross-checked
  against the grid's 09:15 open over 19,358 overlapping contract-sessions: median
  difference 0.000, correlation 0.978.

NO SILENT SKIPS. Every session that reaches the entry gate is accounted for in
one of the buckets returned in `skips`. If a leg cannot be priced at the next
open by any authentic route, the position is marked ADVERSELY (the short leg at
its full intrinsic value against the index open, the long leg at zero) rather
than dropped. A strategy that needs those nights removed does not survive here.

CAUSALITY. Entry uses only the 15:25 bar of session t and panel state published
for session t. The exit is the next session's 09:20 price. No bar between them is
consulted, because nothing between them is tradable by this strategy.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, time as dtime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel

BHAV = "data/raw/nse/fo_bhavcopy/.consolidated_1904_1789736982937725100.parquet"
GRID_CE = "data/derived/grid5m_ce.parquet"
GRID_PE = "data/derived/grid5m_pe.parquet"
PANEL = "data/derived/chain_panel.parquet"

TICK = 0.05
SPREAD_PCT = 0.0030          # per side, ~1.4x the 0.22% ATM spread observed live
SLIP_TICKS = 2
STRIKE_STEP = 50.0

# ── ONE-YEAR SPLITS. Fixed before any candidate in this study was written. ──
DEV_END = date(2024, 9, 17)
VAL_START = date(2024, 9, 18)
VAL_END = date(2025, 9, 17)
HOLDOUT_START = date(2025, 9, 18)
HOLDOUT_END = date(2026, 9, 18)


def buy_fill(px: float, m: float = 1.0) -> float:
    return round(px + max(TICK, px * SPREAD_PCT) * m + SLIP_TICKS * TICK * m, 2)


def sell_fill(px: float, m: float = 1.0) -> float:
    return round(max(TICK, px - max(TICK, px * SPREAD_PCT) * m - SLIP_TICKS * TICK * m), 2)


# ───────────────────────────── DATA ─────────────────────────────

@dataclass
class OvernightData:
    panel: pd.DataFrame
    close_px: Dict[Tuple[date, str, float], float]      # (sess, CE/PE, strike) -> 15:25 print
    close_vol: Dict[Tuple[date, str, float], float]
    bhav_close: Dict[Tuple[date, str, float, pd.Timestamp], float]
    open_px: Dict[Tuple[date, str, float, pd.Timestamp], float]   # + expiry
    px_0920: Dict[Tuple[date, str, float], float]       # 09:15 bar close = 09:20 price
    spot_close: Dict[date, float]
    spot_open: Dict[date, float]
    index_open: Dict[date, float]
    sessions: List[date]
    expiry: Dict[date, pd.Timestamp]
    lot: Dict[date, float]


def load_data() -> OvernightData:
    panel = pd.read_parquet(PANEL)
    panel["date"] = pd.to_datetime(panel["date"])
    panel["sess"] = panel["date"].dt.date

    bh = pd.read_parquet(BHAV, columns=[
        "TradDt", "XpryDt", "StrkPric", "OptnTp", "OpnPric", "ClsPric",
        "TtlTradgVol", "NewBrdLotQty"])
    bh["TradDt"] = pd.to_datetime(bh["TradDt"])
    bh["XpryDt"] = pd.to_datetime(bh["XpryDt"])
    bh["sess"] = bh["TradDt"].dt.date
    op = bh[bh["OpnPric"] > 0]
    open_px = dict(zip(zip(op["sess"], op["OptnTp"], op["StrkPric"], op["XpryDt"]),
                       op["OpnPric"].astype(float)))
    cl = bh[bh["ClsPric"] > 0]
    bhav_close = dict(zip(zip(cl["sess"], cl["OptnTp"], cl["StrkPric"], cl["XpryDt"]),
                          cl["ClsPric"].astype(float)))

    close_px: Dict[Tuple[date, str, float], float] = {}
    close_vol: Dict[Tuple[date, str, float], float] = {}
    px_0920: Dict[Tuple[date, str, float], float] = {}
    spot_close: Dict[date, float] = {}
    spot_open: Dict[date, float] = {}
    for side, path in (("CE", GRID_CE), ("PE", GRID_PE)):
        g = pd.read_parquet(path, columns=["datetime", "strike", "close", "open",
                                           "volume", "spot", "sess"])
        g["t"] = g["datetime"].dt.time
        last = g[(g["t"] >= dtime(15, 15)) & (g["t"] <= dtime(15, 25))]
        last = last.sort_values("datetime").groupby(["sess", "strike"]).last().reset_index()
        for s, k, c, v in zip(last["sess"], last["strike"], last["close"], last["volume"]):
            if c > 0:
                close_px[(s, side, float(k))] = float(c)
                close_vol[(s, side, float(k))] = float(v)
        tail = g[(g["t"] >= dtime(15, 15)) & (g["t"] <= dtime(15, 25))]
        for s, sp in tail.sort_values("datetime").groupby("sess")["spot"].last().items():
            spot_close[s] = float(sp)
        first = g[g["t"] == dtime(9, 15)]
        for s, sp in first.groupby("sess")["spot"].first().items():
            spot_open.setdefault(s, float(sp))
        for s, k, c in zip(first["sess"], first["strike"], first["close"]):
            if c > 0:
                px_0920[(s, side, float(k))] = float(c)

    idx = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = idx[idx["symbol"] == "NIFTY50"]
    index_open = {d.date(): float(o) for d, o in zip(n["datetime"], n["open"])}

    sessions = sorted(set(panel["sess"]) & set(spot_close))
    expiry = dict(zip(panel["sess"], panel["near_expiry"]))
    lot = dict(zip(panel["sess"], panel["lot_size"]))
    return OvernightData(panel=panel, close_px=close_px, close_vol=close_vol,
                         bhav_close=bhav_close, open_px=open_px, px_0920=px_0920,
                         spot_close=spot_close, spot_open=spot_open,
                         index_open=index_open, sessions=sessions, expiry=expiry, lot=lot)


# ───────────────────────────── SPEC ─────────────────────────────

@dataclass
class Leg:
    side: str            # "CE" / "PE"
    qty: int             # +1 long, -1 short
    offset: int          # strike = ATM + offset * 50


@dataclass
class OSpec:
    """A structure held from the 15:25 print to the next session's 09:20 price."""
    name: str
    family: str
    legs: List[Leg]
    filter_fn: Optional[Callable[[pd.Series], bool]] = None
    min_dte: int = 1                # contract must survive to the next session
    max_dte: int = 99
    min_close_vol: float = 0.0      # per leg, on the entry bar
    exit_venue: str = "GRID_0920"   # or "BHAV_OPEN" for the opening-print variant
    notes: str = ""


@dataclass
class ONight:
    name: str
    family: str
    sess: date
    nxt: date
    expiry: pd.Timestamp
    spot_close: float
    spot_open: float
    on_pts: float
    legs: List[Dict[str, Any]]
    entry_credit: float             # +ve = credit received, per unit
    exit_debit: float
    gross_pts: float
    cost_pts: float
    net_pts: float
    margin_pts: float               # capital a broker blocks, per unit, in points
    lot: float
    gross: float
    costs: float
    net: float
    capital: float
    exit_source: str
    entry_source: str
    dte: int
    meta: Dict[str, Any] = field(default_factory=dict)


# ───────────────────────────── SIMULATION ─────────────────────────────

def _leg_exit(d: OvernightData, nxt: date, side: str, strike: float,
              xpry: pd.Timestamp, index_open: float,
              qty: int, venue: str = "GRID_0920") -> Tuple[float, str]:
    """
    Exit price of one leg, five minutes into the next session.

    Order of preference: the 09:15 grid bar's CLOSE (the 09:20 price, a level the
    session has already traded through), then the bhavcopy opening print for
    strikes the grid's ATM+/-6 ladder cannot reach, then an ADVERSE mark. The
    night is never dropped: a short leg that cannot be priced is assumed to cost
    its full intrinsic value against the index open, a long leg that cannot be
    priced is assumed worthless.
    """
    if venue == "GRID_0920":
        px = d.px_0920.get((nxt, side, strike))
        if px is not None and px > 0:
            return float(px), "GRID_0920"
    px = d.open_px.get((nxt, side, strike, xpry))
    if px is not None and px > 0:
        return float(px), "BHAV_OPEN"
    intrinsic = max(0.0, index_open - strike) if side == "CE" else max(0.0, strike - index_open)
    return (intrinsic if qty < 0 else 0.0), "ADVERSE_MARK"


def simulate_overnight(spec: OSpec, sessions: List[date], d: OvernightData,
                       cost_mult: float = 1.0,
                       skips: Optional[Dict[str, int]] = None) -> List[ONight]:
    skips = skips if skips is not None else {}
    pan = d.panel.set_index("sess")
    allsess = d.sessions
    pos = {s: i for i, s in enumerate(allsess)}

    def bump(k: str) -> None:
        skips[k] = skips.get(k, 0) + 1

    out: List[ONight] = []
    for sess in sessions:
        if sess not in pos or pos[sess] + 1 >= len(allsess):
            bump("NO_NEXT_SESSION"); continue
        nxt = allsess[pos[sess] + 1]
        if sess not in pan.index:
            bump("NO_PANEL"); continue
        row = pan.loc[sess]
        dte = int(row["dte"])
        if dte < spec.min_dte or dte > spec.max_dte:
            bump("DTE_GATE"); continue
        if spec.filter_fn is not None:
            try:
                if not spec.filter_fn(row):
                    bump("FILTER"); continue
            except Exception:                                     # noqa: BLE001
                bump("FILTER_ERROR"); continue

        spot_c = d.spot_close.get(sess)
        if spot_c is None:
            bump("NO_CLOSE_SPOT"); continue
        xpry = row["near_expiry"]
        atm = round(spot_c / STRIKE_STEP) * STRIKE_STEP
        io = d.index_open.get(nxt)
        if io is None:
            bump("NO_INDEX_OPEN"); continue

        legs, entry_credit, ok = [], 0.0, True
        for lg in spec.legs:
            k = atm + lg.offset * STRIKE_STEP
            c = d.close_px.get((sess, lg.side, k))
            entry_src = "GRID_1525"
            if c is None or c <= 0:
                # Outside the grid's ATM+/-6 ladder. The bhavcopy close is NSE's
                # weighted average of the last thirty minutes and sits ABOVE the
                # 15:2x print (median +0.80 points for puts), so it is only
                # allowed for a leg being BOUGHT, where paying more is the
                # conservative direction. A short leg is never priced this way.
                if lg.qty < 0:
                    bump("NO_ENTRY_PRINT_SHORT"); ok = False; break
                c = d.bhav_close.get((sess, lg.side, k, xpry))
                if c is None or c <= 0:
                    bump("NO_ENTRY_PRINT"); ok = False; break
                entry_src = "BHAV_VWAP"
            v = d.close_vol.get((sess, lg.side, k), 0.0)
            if lg.qty < 0 and v < spec.min_close_vol:
                bump("ENTRY_TOO_THIN"); ok = False; break
            fill = sell_fill(c, cost_mult) if lg.qty < 0 else buy_fill(c, cost_mult)
            entry_credit += -lg.qty * fill
            legs.append({"side": lg.side, "qty": lg.qty, "strike": k,
                         "entry_px": c, "entry_fill": fill, "vol": v,
                         "entry_src": entry_src})
        if not ok:
            continue

        exit_debit, src = 0.0, spec.exit_venue
        for L in legs:
            px, s = _leg_exit(d, nxt, L["side"], L["strike"], xpry, io, L["qty"],
                              spec.exit_venue)
            if s != spec.exit_venue:
                src = s
            fill = buy_fill(px, cost_mult) if L["qty"] < 0 else sell_fill(px, cost_mult)
            L["exit_px"], L["exit_fill"] = px, fill
            exit_debit += -L["qty"] * fill

        gross_pts = entry_credit - exit_debit

        # statutory charges, per leg, on the actual fills
        cost_pts = 0.0
        lot = float(row["lot_size"]) if np.isfinite(row["lot_size"]) else 65.0
        for L in legs:
            b = L["entry_fill"] if L["qty"] > 0 else L["exit_fill"]
            s_ = L["exit_fill"] if L["qty"] > 0 else L["entry_fill"]
            cost_pts += IndianCostModel.calculate_roundtrip_costs(
                b, s_, int(lot)).total_costs / lot
        cost_pts *= cost_mult
        net_pts = gross_pts - cost_pts

        # Margin actually blocked. For a defined-risk vertical this is the worst
        # case the position can reach; for anything with a naked short leg the
        # broker's SPAN+exposure is used instead and the structure is flagged.
        margin_pts = _margin_points(legs, spot_c)

        spot_o = d.spot_open.get(nxt, io)
        out.append(ONight(
            name=spec.name, family=spec.family, sess=sess, nxt=nxt, expiry=xpry,
            spot_close=spot_c, spot_open=float(spot_o),
            on_pts=float(spot_o) - spot_c, legs=legs,
            entry_credit=round(entry_credit, 2), exit_debit=round(exit_debit, 2),
            gross_pts=round(gross_pts, 2), cost_pts=round(cost_pts, 3),
            net_pts=round(net_pts, 2), margin_pts=round(margin_pts, 2), lot=lot,
            gross=round(gross_pts * lot, 2), costs=round(cost_pts * lot, 2),
            net=round(net_pts * lot, 2), capital=round(margin_pts * lot, 2),
            exit_source=src, dte=dte,
            entry_source=("BHAV_VWAP" if any(L["entry_src"] == "BHAV_VWAP" for L in legs)
                          else "GRID_1525"),
            meta={"vix": float(row["vix"]), "rv20": float(row["rv20"]),
                  "straddle_pct": float(row["straddle_pct"]),
                  "pcr_oi": float(row["pcr_oi"]), "dow": int(row["dow"]),
                  "atm": atm},
        ))
    return out


NAKED_SHORT_MARGIN_PCT = 0.12   # SPAN+exposure for a naked short index option leg


def _margin_points(legs: List[Dict[str, Any]], spot: float) -> float:
    """
    Capital blocked, per unit, in index points.

    A vertical whose short leg is protected by a long leg on the same side blocks
    at most the width minus the credit -- that is the position's worst reachable
    value, and it is what a defined-risk margin benefit gives. An unprotected
    short leg is charged 12% of spot, a deliberately conservative stand-in for
    SPAN+exposure on a NIFTY index option (typically 10-12%).
    """
    shorts = [L for L in legs if L["qty"] < 0]
    if not shorts:
        return sum(L["entry_fill"] for L in legs if L["qty"] > 0)
    worst = 0.0
    for L in shorts:
        same = [x for x in legs if x["qty"] > 0 and x["side"] == L["side"]]
        if not same:
            return spot * NAKED_SHORT_MARGIN_PCT
        if L["side"] == "PE":
            prot = max((x for x in same if x["strike"] < L["strike"]),
                       key=lambda x: x["strike"], default=None)
        else:
            prot = min((x for x in same if x["strike"] > L["strike"]),
                       key=lambda x: x["strike"], default=None)
        if prot is None:
            return spot * NAKED_SHORT_MARGIN_PCT
        worst += abs(L["strike"] - prot["strike"])
    credit = sum(-L["qty"] * L["entry_fill"] for L in legs)
    return max(worst - credit, 1.0)


# ───────────────────────────── METRICS ─────────────────────────────

def split(sessions: List[date]) -> Tuple[List[date], List[date], List[date]]:
    dev = [s for s in sessions if s <= DEV_END]
    val = [s for s in sessions if VAL_START <= s <= VAL_END]
    hold = [s for s in sessions if HOLDOUT_START <= s <= HOLDOUT_END]
    return dev, val, hold


def metrics(nights: List[ONight], n_sessions: int, account: float = 100000.0,
            lots: int = 1) -> Dict[str, Any]:
    if not nights:
        return {"trades": 0, "sessions": n_sessions, "net": 0.0, "note": "no trades"}
    df = pd.DataFrame([{k: v for k, v in n.__dict__.items() if k != "legs"} for n in nights])
    net = df["net"].astype(float) * lots
    wins, losses = net[net > 0], net[net <= 0]
    eq = net.cumsum()
    dd = float((eq - eq.cummax()).min())
    streak = mx = 0
    for x in net:
        if x <= 0:
            streak += 1; mx = max(mx, streak)
        else:
            streak = 0
    per_day = df.assign(net=net).groupby("sess")["net"].sum()
    rp = per_day / account * 100
    gw, gl = float(wins.sum()), float(abs(losses.sum()))
    cap = float(df["capital"].max()) * lots
    return {
        "trades": int(len(df)), "sessions": n_sessions,
        "win_rate": round(len(wins) / len(df) * 100, 1),
        "gross": round(float(df["gross"].sum()) * lots, 2),
        "costs": round(float(df["costs"].sum()) * lots, 2),
        "net": round(float(net.sum()), 2),
        "net_pts": round(float(df["net_pts"].sum()), 2),
        "expectancy": round(float(net.mean()), 2),
        "expectancy_pts": round(float(df["net_pts"].mean()), 3),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "payoff": round(float(wins.mean() / abs(losses.mean())), 2)
                  if len(wins) and len(losses) and losses.mean() != 0 else None,
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "max_dd": round(abs(dd), 2),
        "max_losing_streak": int(mx),
        "worst_night": round(float(net.min()), 2),
        "best_night": round(float(net.max()), 2),
        "max_capital_used": round(cap, 2),
        "avg_capital": round(float(df["capital"].mean()) * lots, 2),
        "ret_on_max_capital": round(float(net.sum()) / cap * 100, 2) if cap else 0.0,
        "ret_on_account": round(float(net.sum()) / account * 100, 2),
        "trades_per_day": round(len(df) / n_sessions, 3) if n_sessions else 0.0,
        "avg_daily_pct": round(float(rp.mean()), 4),
        "median_daily_pct": round(float(rp.median()), 4),
        "pct_days_profitable": round(float((per_day > 0).mean() * 100), 1),
        "pct_days_ge_0p5": round(float((rp >= 0.5).mean() * 100), 1),
        "pct_days_ge_1": round(float((rp >= 1).mean() * 100), 1),
        "pct_days_ge_2": round(float((rp >= 2).mean() * 100), 1),
        "pct_days_le_m0p5": round(float((rp <= -0.5).mean() * 100), 1),
        "pct_days_le_m1": round(float((rp <= -1).mean() * 100), 1),
        "pct_days_le_m2": round(float((rp <= -2).mean() * 100), 1),
        "adverse_marks": int((df["exit_source"] == "ADVERSE_MARK").sum()),
        "fallback_exits": int((df["exit_source"] != "GRID_0920").sum()),
        "tstat": round(tstat(df["net_pts"].to_numpy(float)), 2),
    }


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    if len(x) < 2:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")


HDR = (f"{'candidate':30}{'n':>5}{'win%':>7}{'netpts':>9}{'exp':>8}{'t':>7}"
       f"{'PF':>7}{'net Rs':>11}{'maxDD':>10}{'cap':>9}{'ret/cap':>9}{'adv':>5}")


def line(name: str, m: Dict[str, Any]) -> str:
    if m.get("trades", 0) == 0:
        return f"{name:30}{'NO TRADES':>10}"
    return (f"{name:30}{m['trades']:>5}{m['win_rate']:>7.1f}{m['net_pts']:>9.0f}"
            f"{m['expectancy_pts']:>8.2f}{m['tstat']:>7.2f}{str(m['profit_factor']):>7}"
            f"{m['net']:>11,.0f}{m['max_dd']:>10,.0f}{m['max_capital_used']:>9,.0f}"
            f"{m['ret_on_max_capital']:>8.0f}%{m['adverse_marks']:>5}")
