"""
ZERO-DTE IRON CONDOR, SETTLED AT EXPIRY.

WHY THIS REPLACES THE MARK-TO-MARKET VERSION. Closing the position at 15:10 needs
a live quote for all four legs. On expiry day the wings are far out of the money
and genuinely stop trading, so 68 of 211 development expiry sessions had no fresh
wing quote. Refusing those sessions removed the volatile ones: prior-day range
averaged 1.525% on the refused sessions against 0.843% on the taken ones. That is
a filter quietly deleting the days most likely to breach, which would flatter any
short-premium result.

The fix is to stop needing the quote. The position is opened intraday at real
traded prices and held to expiry, where every leg settles at intrinsic value
against the exchange settlement price from the NSE F&O bhavcopy. Nothing is
marked, nothing is carried forward, nothing is refused for staleness, and every
expiry session with a priceable entry is measured.

The cost of the fix is that the position can no longer be closed early, so it
carries full expiry risk. That is the conservative direction.

EXECUTION. Entry legs pay max(1 tick, 0.30%) of half-spread plus 2 ticks of
slippage, scalable by cost_mult. Settlement is exchange-determined and pays no
spread, but statutory charges are applied on both the opening trade and the
settlement, including the 0.125% exercise STT that an in-the-money long leg
attracts. Max loss stays capped at (wing width - credit) x lot by construction.
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
class ZSpec:
    name: str
    short_atr: float = 0.35
    wing_steps: int = 3
    entry_t: dtime = dtime(9, 45)
    max_vix: float = 30.0
    min_credit_pts: float = 2.0
    legs: str = "condor"
    notes: str = ""


@dataclass
class ZTrade:
    name: str
    sess: date
    entry_time: str
    spot_in: float
    settle: float
    short_put: float
    short_call: float
    width: float
    credit_pts: float
    settle_loss_pts: float
    max_risk: float
    gross: float
    costs: float
    net: float
    breached: bool
    max_loss_hit: bool
    legs: List[Dict[str, Any]] = field(default_factory=list)


def run_dte0(spec: ZSpec, sessions: List[date], daily: pd.DataFrame,
             panels: Dict[date, Dict[str, Any]],
             opts: Dict[str, Dict[date, pd.DataFrame]],
             settle_of: Dict[date, float],
             cost_mult: float = 1.0,
             skips: Optional[Dict[str, int]] = None) -> List[ZTrade]:
    skips = skips if skips is not None else {}
    dpos = {d: i for i, d in enumerate(daily["sess"])}
    out: List[ZTrade] = []

    def bump(k):
        skips[k] = skips.get(k, 0) + 1

    for sess in sessions:
        p = panels.get(sess)
        if p is None:
            bump("NO_PANEL"); continue
        if sess not in dpos or dpos[sess] < 60:
            bump("NO_PRIOR_HISTORY"); continue
        settle = settle_of.get(sess)
        if settle is None or not np.isfinite(settle) or settle <= 0:
            bump("NO_SETTLEMENT"); continue
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
        spot, ts = float(vals[ei]), stamps[ei]

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
            intr = max(0.0, settle - k) if ot == "ce" else max(0.0, k - settle)
            legs.append({"role": role, "ot": ot, "side": side, "strike": k,
                         "open_px": px, "open_fill": fill, "settle_px": round(intr, 2)})
        if bad or not legs:
            bump("LEG_UNPRICEABLE"); continue

        credit = sum((1 if l["side"] == "SELL" else -1) * l["open_fill"] for l in legs)
        if credit < spec.min_credit_pts:
            bump("CREDIT_TOO_THIN"); continue

        gross = sum((1 if l["side"] == "SELL" else -1)
                    * (l["open_fill"] - l["settle_px"]) * LOT for l in legs)
        costs = 0.0
        for l in legs:
            if l["side"] == "SELL":
                c = IndianCostModel.calculate_roundtrip_costs(l["settle_px"], l["open_fill"], LOT)
            else:
                c = IndianCostModel.calculate_roundtrip_costs(l["open_fill"], l["settle_px"], LOT)
            costs += c.total_costs * cost_mult
            # exercise STT on an in-the-money LONG leg at settlement
            if l["side"] == "BUY" and l["settle_px"] > 0:
                costs += 0.00125 * l["settle_px"] * LOT * cost_mult

        loss_pts = 0.0
        if spec.legs in ("condor", "vertical_call"):
            loss_pts += max(0.0, min(settle, sc + w) - sc)
        if spec.legs in ("condor", "vertical_put"):
            loss_pts += max(0.0, sp - max(settle, sp - w))
        breached = bool((spec.legs in ("condor", "vertical_call") and settle > sc)
                        or (spec.legs in ("condor", "vertical_put") and settle < sp))

        out.append(ZTrade(
            name=spec.name, sess=sess, entry_time=str(times[ei]), spot_in=spot,
            settle=round(float(settle), 2),
            short_put=sp if spec.legs != "vertical_call" else float("nan"),
            short_call=sc if spec.legs != "vertical_put" else float("nan"),
            width=w, credit_pts=round(credit, 2), settle_loss_pts=round(loss_pts, 2),
            max_risk=round((w - credit) * LOT, 2), gross=round(gross, 2),
            costs=round(costs, 2), net=round(gross - costs, 2), breached=breached,
            max_loss_hit=bool(loss_pts >= w - 0.01), legs=legs))
    return out


def z_metrics(trades: List[ZTrade], sessions: List[date],
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
        "max_loss_events": int(df["max_loss_hit"].sum()),
        "worst_trade": round(float(net.min()), 2), "best_trade": round(float(net.max()), 2),
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
        "tstat": round(float(net.mean() / (sd / np.sqrt(len(net)))), 2) if sd > 0 else None,
    }
