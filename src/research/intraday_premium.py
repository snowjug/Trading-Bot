"""
INTRADAY DEFINED-RISK SHORT PREMIUM.

WHY THIS FAMILY EXISTS. Every long-option concept in this study fought the same
wall: a bought option pays two sides of spread plus theta, and NIFTY's realised
intraday movement has compressed sharply. Measured on this dataset, the share of
sessions whose 09:15-09:29 range reaches 0.35% of spot fell from 10.1% in 2022 to
2.4% in 2023 and has stayed near 2% since. Directional long premium is the wrong
side of that trade; the same measurement is the case for being short it.

STRUCTURE. Sell an out-of-the-money strangle and buy wings, so loss is capped by
construction and no naked short exists at any point. Entered after the opening
range is known, closed the same session before the close. No overnight gap risk,
which is the main hazard of the weekly short-premium structures already rejected
in the previous study.

RISK. Max loss = (wing width - credit) x lot, realised only if spot finishes
beyond a long wing. A stop on the spread's own mark closes the position early when
the mark reaches `stop_mult` times the credit taken.

EXECUTION. Identical convention to lab2: each side pays max(1 tick, 0.30%) of
half-spread plus 2 ticks of slippage, then statutory charges from IndianCostModel,
all scalable by `cost_mult` for sensitivity. A short leg is opened with sell_fill
and closed with buy_fill; a long wing is the reverse. Every leg must be quoted with
positive volume at entry or the cycle is refused — it fails closed, never
substituted.

CAUSALITY. Strikes are chosen from the entry bar's spot and the prior session's
ATR/VIX. Exit scans forward only to resolve a stop or the clock.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import date, time as dtime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel
from src.research.lab2 import LOT, STRIKE_STEP, buy_fill, sell_fill


@dataclass
class IPSpec:
    name: str
    legs: str = "condor"              # condor | vertical_put | vertical_call
    short_atr: float = 0.35           # short strike distance, in prior-day ATR
    wing_steps: int = 3
    entry_t: dtime = dtime(9, 45)
    exit_t: dtime = dtime(15, 10)
    stop_mult: float = 2.5            # close if mark >= stop_mult x credit
    max_vix: float = 30.0
    min_credit_pts: float = 2.0
    max_stale_bars: int = 2      # refuse an exit priced off a quote older than this
    notes: str = ""


@dataclass
class IPTrade:
    name: str
    sess: date
    entry_time: str
    exit_time: str
    spot_in: float
    spot_out: float
    short_put: float
    short_call: float
    width: float
    credit_pts: float
    exit_pts: float
    max_risk: float
    gross: float
    costs: float
    net: float
    breached: bool
    exit_reason: str
    stale_bars: int = 0
    legs: List[Dict[str, Any]] = field(default_factory=list)


def _leg_costs(side: str, open_px: float, close_px: float, qty: int, mult: float) -> float:
    """A short leg is sold then bought; a long leg is bought then sold."""
    if side == "SELL":
        c = IndianCostModel.calculate_roundtrip_costs(close_px, open_px, qty)
    else:
        c = IndianCostModel.calculate_roundtrip_costs(open_px, close_px, qty)
    return c.total_costs * mult


def run_intraday_premium(spec: IPSpec, sessions: List[date], daily: pd.DataFrame,
                         panels: Dict[date, Dict[str, Any]],
                         opts: Dict[str, Dict[date, pd.DataFrame]],
                         cost_mult: float = 1.0,
                         skips: Optional[Dict[str, int]] = None) -> List[IPTrade]:
    skips = skips if skips is not None else {}
    dpos = {d: i for i, d in enumerate(daily["sess"])}
    out: List[IPTrade] = []

    def bump(k: str) -> None:
        skips[k] = skips.get(k, 0) + 1

    for sess in sessions:
        p = panels.get(sess)
        if p is None:
            bump("NO_PANEL"); continue
        if sess not in dpos or dpos[sess] < 60:
            bump("NO_PRIOR_HISTORY"); continue
        prior = daily.iloc[dpos[sess] - 1]
        atr, vix = float(prior["atr14"]), float(prior["vix"])
        if not np.isfinite(atr) or atr <= 0 or not np.isfinite(vix):
            bump("NO_REGIME"); continue
        if vix >= spec.max_vix:
            bump("VIX_BLOCK"); continue
        dce, dpe = opts["ce"].get(sess), opts["pe"].get(sess)
        if dce is None or dpe is None:
            bump("NO_OPTION_DATA"); continue

        times, stamps, vals = p["times"], p["stamps"], p["spot"]
        ei = next((j for j, tt in enumerate(times) if tt >= spec.entry_t), None)
        if ei is None:
            bump("NO_ENTRY_BAR"); continue
        spot = float(vals[ei])
        ts = stamps[ei]

        d = spec.short_atr * atr
        sc = round((spot + d) / STRIKE_STEP) * STRIKE_STEP
        sp = round((spot - d) / STRIKE_STEP) * STRIKE_STEP
        w = spec.wing_steps * STRIKE_STEP
        if spec.legs == "condor":
            want = [("short_call", "ce", "SELL", sc), ("long_call", "ce", "BUY", sc + w),
                    ("short_put", "pe", "SELL", sp), ("long_put", "pe", "BUY", sp - w)]
        elif spec.legs == "vertical_put":
            want = [("short_put", "pe", "SELL", sp), ("long_put", "pe", "BUY", sp - w)]
        else:
            want = [("short_call", "ce", "SELL", sc), ("long_call", "ce", "BUY", sc + w)]

        frames = {"ce": dce, "pe": dpe}
        legs, bad = [], False
        for role, ot, side, k in want:
            f = frames[ot]
            at = f[(f["datetime"] == ts) & (f["strike"] == k)]
            if at.empty:
                bad = True; break
            r = at.iloc[0]
            px = float(r["close"])
            if px <= 0 or float(r["volume"]) <= 0:
                bad = True; break
            fill = sell_fill(px, cost_mult) if side == "SELL" else buy_fill(px, cost_mult)
            legs.append({"role": role, "ot": ot, "side": side, "strike": k,
                         "open_px": px, "open_fill": fill})
        if bad or not legs:
            bump("LEG_UNPRICEABLE"); continue

        credit = sum((1 if l["side"] == "SELL" else -1) * l["open_fill"] for l in legs)
        if credit < spec.min_credit_pts:
            bump("CREDIT_TOO_THIN"); continue

        # forward marks for every leg, keyed by timestamp
        marks: Dict[Any, Dict[str, float]] = {}
        for l in legs:
            f = frames[l["ot"]]
            fw = f[(f["strike"] == l["strike"]) & (f["datetime"] >= ts)]
            for dt_, px in zip(fw["datetime"], fw["close"]):
                marks.setdefault(dt_, {})[l["role"]] = float(px)

        # Each leg's mark is carried forward from its own last quote, so a bar at
        # which one leg happens to be unquoted cannot move the exit. Without this,
        # the exit bar is chosen by data availability rather than by the rules,
        # which silently selects the sample. Staleness is measured and capped.
        last: Dict[str, float] = {}
        last_at: Dict[str, int] = {}
        held: Dict[int, Dict[str, float]] = {}
        stale: Dict[int, int] = {}
        for j in range(ei, len(vals)):
            mk = marks.get(stamps[j], {})
            for role, px in mk.items():
                last[role] = px
                last_at[role] = j
            if len(last) == len(legs):
                held[j] = dict(last)
                stale[j] = j - min(last_at[l["role"]] for l in legs)

        xi, reason = None, "CLOSE"
        for j in range(ei + 1, len(vals)):
            mk = held.get(j)
            if mk is None:
                continue
            mark = sum((1 if l["side"] == "SELL" else -1) * mk[l["role"]] for l in legs)
            if mark >= spec.stop_mult * credit:
                xi, reason = j, "STOP"; break
            if times[j] >= spec.exit_t:
                xi, reason = j, "CLOSE"; break
        if xi is None:
            back = [j for j in sorted(held, reverse=True) if j > ei]
            if not back:
                bump("NO_EXIT_MARK"); continue
            xi, reason = back[0], "SESSION_END"
        if stale.get(xi, 99) > spec.max_stale_bars:
            bump("EXIT_MARK_STALE"); continue

        mk = held[xi]
        gross = 0.0
        costs = 0.0
        for l in legs:
            cpx = mk[l["role"]]
            cfill = buy_fill(cpx, cost_mult) if l["side"] == "SELL" else sell_fill(cpx, cost_mult)
            l["close_px"], l["close_fill"] = cpx, cfill
            sgn = 1 if l["side"] == "SELL" else -1
            gross += sgn * (l["open_fill"] - cfill) * LOT
            costs += _leg_costs(l["side"], l["open_fill"], cfill, LOT, cost_mult)

        exit_pts = sum((1 if l["side"] == "SELL" else -1) * l["close_fill"] for l in legs)
        spot_out = float(vals[xi])
        breached = bool((spec.legs in ("condor", "vertical_call") and spot_out > sc)
                        or (spec.legs in ("condor", "vertical_put") and spot_out < sp))
        out.append(IPTrade(
            name=spec.name, sess=sess, entry_time=str(times[ei]), exit_time=str(times[xi]),
            spot_in=spot, spot_out=spot_out,
            short_put=sp if spec.legs != "vertical_call" else float("nan"),
            short_call=sc if spec.legs != "vertical_put" else float("nan"),
            width=w, credit_pts=round(credit, 2), exit_pts=round(exit_pts, 2),
            max_risk=round((w - credit) * LOT, 2),
            gross=round(gross, 2), costs=round(costs, 2),
            net=round(gross - costs, 2), breached=breached, exit_reason=reason,
            stale_bars=int(stale.get(xi, 0)), legs=legs))
    return out


def ip_metrics(trades: List[IPTrade], sessions: List[date],
               account: float = 100000.0, lots: int = 1) -> Dict[str, Any]:
    n_sess = len(sessions)
    if not trades:
        return {"trades": 0, "sessions": n_sess, "net": 0.0, "note": "no trades"}
    df = pd.DataFrame([{k: v for k, v in t.__dict__.items() if k != "legs"} for t in trades])
    net = df["net"].astype(float) * lots
    wins, losses = net[net > 0], net[net <= 0]
    eq = net.cumsum()
    dd = abs(float((eq - eq.cummax()).min()))
    streak = mx = 0
    for x in net:
        if x <= 0:
            streak += 1; mx = max(mx, streak)
        else:
            streak = 0
    per_day = pd.Series(0.0, index=pd.Index(sorted(sessions)))
    for s, v in df.assign(net=net).groupby("sess")["net"].sum().items():
        if s in per_day.index:
            per_day.loc[s] += v
    rp = per_day / account * 100
    gw, gl = float(wins.sum()), float(abs(losses.sum()))
    sd = float(net.std(ddof=1)) if len(net) > 1 else 0.0
    return {
        "trades": int(len(df)), "sessions": n_sess,
        "win_rate": round(len(wins) / len(df) * 100, 1),
        "gross": round(float(df["gross"].sum()) * lots, 2),
        "costs": round(float(df["costs"].sum()) * lots, 2),
        "net": round(float(net.sum()), 2),
        "expectancy": round(float(net.mean()), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "max_dd": round(dd, 2), "max_losing_streak": int(mx),
        "avg_credit_pts": round(float(df["credit_pts"].mean()), 2),
        "avg_max_risk": round(float(df["max_risk"].mean()) * lots, 2),
        "max_risk_worst": round(float(df["max_risk"].max()) * lots, 2),
        "breaches": int(df["breached"].sum()),
        "breach_pct": round(float(df["breached"].mean()) * 100, 1),
        "worst_trade": round(float(net.min()), 2),
        "best_trade": round(float(net.max()), 2),
        "trades_per_day": round(len(df) / n_sess, 3) if n_sess else 0.0,
        "pct_sessions_traded": round(len(set(df["sess"])) / n_sess * 100, 1) if n_sess else 0.0,
        "ret_on_risk": round(float(net.sum()) / (float(df["max_risk"].mean()) * lots) * 100, 2),
        "ret_on_account": round(float(net.sum()) / account * 100, 2),
        "avg_daily_pct": round(float(rp.mean()), 4),
        "median_daily_pct": round(float(rp.median()), 4),
        "best_day": round(float(per_day.max()), 2), "worst_day": round(float(per_day.min()), 2),
        "pct_days_profitable": round(float((rp > 0).mean() * 100), 1),
        "pct_days_ge_0p25": round(float((rp >= 0.25).mean() * 100), 1),
        "pct_days_ge_0p5": round(float((rp >= 0.5).mean() * 100), 1),
        "pct_days_ge_1": round(float((rp >= 1).mean() * 100), 1),
        "pct_days_ge_2": round(float((rp >= 2).mean() * 100), 1),
        "pct_days_le_m0p5": round(float((rp <= -0.5).mean() * 100), 1),
        "pct_days_le_m1": round(float((rp <= -1).mean() * 100), 1),
        "pct_days_le_m2": round(float((rp <= -2).mean() * 100), 1),
        "profitable_days": int((per_day > 0).sum()), "losing_days": int((per_day < 0).sum()),
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
        "tstat": round(float(net.mean() / (sd / np.sqrt(len(net)))), 2) if sd > 0 else None,
    }
