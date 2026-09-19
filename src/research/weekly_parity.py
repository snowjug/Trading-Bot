"""
WEEKLY PARITY ENGINE — measures BOT 1 and BOT 2 by CALLING the live signal
functions, so research and live cannot diverge.

WHY THIS REPLACES `scripts/research/weekly_premium_lab.py` FOR ANY MONEY CLAIM.

`src/execution/bot_signals.py` opens with: "Research and live share these
functions, so parity is structural rather than something to be audited later."
That is true of Bots 6, 7 and 8 — `scripts/research/holdout_6m.frozen()` calls
them. It was NOT true of the weekly bots. `weekly_premium_lab` reimplemented them,
and the reimplementation differs from the live definition in ways that changed the
reported money. Measured on the one-year holdout (2025-09-18 .. 2026-09-18):

  BOT 1 — Iron Condor
    live      wings at (wing_sd - otm_sd) = 0.6 EXPECTED MOVES from the short,
              so the wing WIDTH scales with VIX: 150 pts at VIX 10, 350 at VIX 20
    research  wings at a FIXED 4 strike steps = 200 points
    effect    the two disagreed on 15 of 28 cycles; max risk per lot was reported
              as Rs 14,630 when the live structure needs Rs 21,759 — the
              difference between BOT1 fitting a Rs 20,000 sleeve and not fitting it

  BOT 2 — vertical credit spread
    live      side chosen by RSI: <= 44 sell puts, >= 62 sell calls, OTHERWISE NO
              TRADE; wings at 1.9 vs 1.3 expected moves
    research  side chosen by "sell whichever side spot is further from", no RSI
              gate at all, wings at a FIXED 12 steps = 600 points
    effect    research took 28 cycles; the live rule would have taken 5. The side
              agreed on 3 of 28. Research net was Rs 30,241 against Rs 5,623 for
              the cycles the live bot would actually have entered on the same side.

So this module takes no strategy parameters of its own. It asks
`bot_signals.bot1_apex_vrp` / `bot2_zen_curvature` what to do, resolves whatever
legs they return against the authentic chain, and settles at expiry. If a
parameter changes in the live bot, this measurement changes with it.

PRICING. Entry is the bhavcopy close of the entry session for the target expiry,
penalised per side (a sell receives less than the print, a buy pays more). A leg
that did not trade that session has no executable price and the whole cycle is
refused — recorded, not dropped. Exit needs no price at all: the position is held
to expiry and settled against the underlying's official settlement value, which
the bhavcopy publishes on every expiry session.

LOT SIZE is read from `NewBrdLotQty` and never assumed. All legs must agree on it;
a mismatch refuses the cycle. Sessions before 2024 have no lot size published, so
rupee figures there are impossible and the cycle is refused rather than guessed.
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

from src.execution import bot_signals as BS
from src.research.bot1_condor_real import (
    ChainIndex, condor_leg_costs, load_bhavcopy_store, weekly_expiry_calendar,
)

STRIKE_STEP = 50.0
TICK = 0.05
SPREAD_PCT = 0.0030
SLIP_TICKS = 2
DECISION_TIME = dtime(15, 0)      # the live bots require now >= 14:45


def sell_credit(px: float, m: float = 1.0) -> float:
    return max(TICK, px - max(TICK, px * SPREAD_PCT) * m - SLIP_TICKS * TICK * m)


def buy_debit(px: float, m: float = 1.0) -> float:
    return px + max(TICK, px * SPREAD_PCT) * m + SLIP_TICKS * TICK * m


@dataclass
class Cycle:
    bot: str
    entry_session: date
    expiry: date
    dte_entry: int
    spot: float
    vix: float
    settle: float
    reason: str
    legs: List[Dict[str, Any]]
    n_legs: int
    lot: int
    credit_pts: float
    width_pts: float
    max_risk: float
    gross: float
    costs: float
    net: float
    breached: bool
    meta: Dict[str, Any] = field(default_factory=dict)


def daily_frame() -> pd.DataFrame:
    """NIFTY daily OHLC plus India VIX, the same frame the live session builds."""
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = (raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]]
         .rename(columns={"close": "vix"}))
    d = n.merge(v, on="datetime", how="left").sort_values("datetime").reset_index(drop=True)
    d["d"] = pd.to_datetime(d["datetime"]).dt.date
    return d


SIGNALS: Dict[str, Callable] = {
    "BOT1": BS.bot1_apex_vrp,
    "BOT2": BS.bot2_zen_curvature,
}


def _intrinsic(opt: str, strike: float, settle: float) -> float:
    return max(0.0, settle - strike) if opt == "CE" else max(0.0, strike - settle)


def run(bot: str, sessions: List[date], daily: pd.DataFrame, store: pd.DataFrame,
        chains: ChainIndex, expiries: List[date], calendar: List[date],
        cost_mult: float = 1.0, skips: Optional[Dict[str, int]] = None,
        require_lot: bool = True) -> Tuple[List[Cycle], Dict[str, int]]:
    """
    Every session is accounted for: it either produces a Cycle or lands in exactly
    one bucket of `skips`. Nothing is dropped.

    `calendar` is the TRADING-SESSION calendar, which is what `sessions_until`
    counts; `expiries` is the weekly expiry list. Passing the expiry list as the
    calendar makes every session report NOT_ENTRY_SESSION, because only one expiry
    date ever falls between today and the next expiry.
    """
    skips = skips if skips is not None else {}
    sig = SIGNALS[bot]
    settle_by_expiry = _settlement_map(store)
    vix_by_day = dict(zip(daily["d"], daily["vix"]))
    close_by_day = dict(zip(daily["d"], daily["close"]))

    def bump(k: str) -> None:
        skips[k] = skips.get(k, 0) + 1

    out: List[Cycle] = []
    for day in sessions:
        spot = close_by_day.get(day)
        vix = vix_by_day.get(day)
        if spot is None or vix is None or not np.isfinite(vix) or vix <= 0:
            bump("NO_SPOT_OR_VIX"); continue
        fwd = [e for e in expiries if e > day]
        if not fwd:
            bump("NO_FORWARD_EXPIRY"); continue
        expiry = fwd[0]

        # The live bots read a trading calendar; give them the authentic one.
        dec = sig(float(spot), float(vix), daily, day, expiry, calendar, DECISION_TIME)
        if dec.action != "ENTER":
            bump(f"SIGNAL:{dec.reason.split(':')[0].split(' ')[0]}"); continue
        if not dec.legs:
            bump("SIGNAL_NO_LEGS"); continue

        if not chains.has_day(day):
            bump("NO_CHAIN"); continue
        chain = chains.chain(day, expiry)
        if chain is None or chain.empty:
            bump("NO_CHAIN_FOR_EXPIRY"); continue
        settle = settle_by_expiry.get(expiry)
        if settle is None or not np.isfinite(settle) or settle <= 0:
            bump("NO_SETTLEMENT"); continue

        atm = round(float(spot) / STRIKE_STEP) * STRIKE_STEP
        legs, lot, bad = [], None, None
        for ls in dec.legs:
            k = float(ls.strike) if ls.strike is not None else atm + ls.strike_offset * STRIKE_STEP
            r = chain[(chain["StrkPric"] == k) & (chain["OptnTp"] == ls.option_type)]
            if r.empty:
                bad = "LEG_NOT_LISTED"; break
            rr = r.iloc[0]
            if float(rr["TtlTradgVol"]) <= 0 or float(rr["ClsPric"]) <= 0:
                bad = "LEG_DID_NOT_TRADE"; break
            if require_lot:
                if "NewBrdLotQty" not in rr.index or not pd.notna(rr["NewBrdLotQty"]) \
                        or int(rr["NewBrdLotQty"]) <= 0:
                    bad = "NO_AUTHENTIC_LOT_SIZE"; break
                q = int(rr["NewBrdLotQty"])
                if lot is None:
                    lot = q
                elif q != lot:
                    bad = "LOT_SIZE_MISMATCH_ACROSS_LEGS"; break
            else:
                lot = lot or 1
                q = lot
            px = float(rr["ClsPric"])
            fill = (sell_credit(px, cost_mult) if ls.side == "SELL"
                    else buy_debit(px, cost_mult))
            legs.append({
                "role": ls.role, "option_type": ls.option_type, "side": ls.side,
                "strike": k, "traded": px, "fill": round(fill, 2),
                "exit": round(_intrinsic(ls.option_type, k, float(settle)), 2),
                "qty": q, "expiry": str(expiry),
                "instrument": str(rr.get("FinInstrmNm", "")),
                "security_id": str(rr.get("FinInstrmId", "")),
            })
        if bad:
            bump(bad); continue
        if len(legs) != len(dec.legs):
            bump("LEG_RESOLUTION_INCOMPLETE"); continue

        credit = sum((1 if L["side"] == "SELL" else -1) * L["fill"] for L in legs)
        gross = sum((1 if L["side"] == "BUY" else -1) * (L["exit"] - L["fill"]) * L["qty"]
                    for L in legs)
        costs = sum(condor_leg_costs(L["side"], L["fill"], L["exit"], L["qty"])
                    for L in legs) * cost_mult
        width = _worst_width(legs)
        max_risk = max((width - credit) * (lot or 1), 1.0)
        breached = any(L["exit"] > 0 for L in legs if L["side"] == "SELL")
        out.append(Cycle(
            bot=bot, entry_session=day, expiry=expiry,
            dte_entry=(expiry - day).days, spot=float(spot), vix=float(vix),
            settle=float(settle), reason=dec.reason, legs=legs, n_legs=len(legs),
            lot=int(lot or 1), credit_pts=round(credit, 2), width_pts=round(width, 2),
            max_risk=round(max_risk, 2), gross=round(gross, 2), costs=round(costs, 2),
            net=round(gross - costs, 2), breached=bool(breached),
            meta={"direction": dec.direction},
        ))
    return out, skips


def _worst_width(legs: List[Dict[str, Any]]) -> float:
    """
    Worst reachable spread width: the widest short-to-long distance on either side.
    A short leg with no protecting long leg on its own side is unbounded and is
    reported as such rather than silently given a number.
    """
    worst = 0.0
    for L in legs:
        if L["side"] != "SELL":
            continue
        same = [x for x in legs if x["side"] == "BUY"
                and x["option_type"] == L["option_type"]]
        if not same:
            return float("inf")
        if L["option_type"] == "CE":
            prot = min((x for x in same if x["strike"] > L["strike"]),
                       key=lambda x: x["strike"], default=None)
        else:
            prot = max((x for x in same if x["strike"] < L["strike"]),
                       key=lambda x: x["strike"], default=None)
        if prot is None:
            return float("inf")
        worst = max(worst, abs(prot["strike"] - L["strike"]))
    return worst


def _settlement_map(store: pd.DataFrame) -> Dict[date, float]:
    """
    Official settlement value per expiry session. On an expiry session the bhavcopy
    writes the UNDERLYING's final settlement into SttlmPric on every contract row,
    so the modal value of that session is the settlement.
    """
    out: Dict[date, float] = {}
    s = store[store["TradDt"] == store["XpryDt"]]
    for xp, g in s.groupby("XpryDt"):
        v = g["SttlmPric"].dropna()
        if len(v):
            out[xp] = float(v.mode().iloc[0])
    return out


def metrics(cycles: List[Cycle], n_sessions: int, account: float = 100000.0,
            lots: int = 1) -> Dict[str, Any]:
    if not cycles:
        return {"cycles": 0, "sessions": n_sessions, "net": 0.0, "note": "no cycles"}
    df = pd.DataFrame([{k: v for k, v in c.__dict__.items() if k != "legs"}
                       for c in cycles])
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
    gw, gl = float(wins.sum()), float(abs(losses.sum()))
    risk = float(df["max_risk"].max()) * lots
    x = net.to_numpy(float)
    t = float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")
    return {
        "cycles": int(len(df)), "sessions": n_sessions,
        "win_rate": round(len(wins) / len(df) * 100, 1),
        "breach_rate": round(float(df["breached"].mean() * 100), 1),
        "gross": round(float(df["gross"].sum()) * lots, 2),
        "costs": round(float(df["costs"].sum()) * lots, 2),
        "net": round(float(net.sum()), 2),
        "expectancy": round(float(net.mean()), 2),
        "median": round(float(net.median()), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "max_dd": round(abs(dd), 2),
        "max_losing_streak": int(mx),
        "worst_cycle": round(float(net.min()), 2),
        "best_cycle": round(float(net.max()), 2),
        "max_risk_per_lot": round(float(df["max_risk"].max()), 2),
        "avg_credit_pts": round(float(df["credit_pts"].mean()), 2),
        "avg_width_pts": round(float(df["width_pts"].mean()), 2),
        "ret_on_max_risk": round(float(net.sum()) / risk * 100, 2) if risk else 0.0,
        "ret_on_account": round(float(net.sum()) / account * 100, 2),
        "tstat": round(t, 2),
        "breakeven_win_rate": (
            round(float(df["max_risk"].max()) /
                  (float(df["max_risk"].max()) + float(wins.mean())) * 100, 2)
            if len(wins) else None),
    }


def load_all():
    store = load_bhavcopy_store()
    if store is None or store.empty:
        raise SystemExit("bhavcopy store missing — cannot measure anything")
    return daily_frame(), store, ChainIndex(store), weekly_expiry_calendar(store)
