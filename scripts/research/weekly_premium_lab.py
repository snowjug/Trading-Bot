"""
Weekly short-premium candidates, DEV / VAL split.

WHY THIS FAMILY. The intraday long-option family just failed validation outright:
every wide-target variant that made money on 2020-2024 lost on 2025-2026, some by
more than it had made. The only structure in this whole body of work with a
positive multi-year net was Bot 1's weekly condor (+2.90 points per cycle, t=+1.40
over 158 cycles), and its mechanism — the variance risk premium — does not depend
on predicting direction, which is precisely where everything else failed.

THE LEVER BEING TESTED. Cost scales with leg count. Measured on the expiry-day iron
fly: gross +Rs 21,551 against Rs 43,645 of costs over 318 trades — Rs 137 per trade
of statutory charges on four legs against Rs 68 of gross edge. A two-leg vertical
pays roughly half that. So the question is whether halving the leg count converts a
real gross edge into a real net one.

EXECUTION. Entry at each leg's own traded close, and only if that contract actually
traded. Exit by exact cash settlement at expiry against the exchange's official
settlement price. Side-aware statutory costs. Slippage charged per leg at the same
conservative rate used everywhere else in this study.

CAUSALITY. The regime read comes from sessions strictly before the entry day; the
settlement used for the exit is the expiry session's own official price.
"""

import os
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot1_condor_real import (
    ChainIndex, condor_leg_costs, load_bhavcopy_store, weekly_expiry_calendar,
)
from src.research.strategy_lab import DEV_END, VAL_END, HOLDOUT_START, SPREAD_PCT, SLIP_TICKS, TICK

LOT_FALLBACK = None          # never guessed; a missing lot size skips the cycle


@dataclass
class WSpec:
    name: str
    legs: str                # "condor" | "vertical_put" | "vertical_call" | "vertical_auto"
    short_sd: float
    wing_steps: int          # wing distance in strike steps from the short
    hold_sessions: int = 5
    max_vix: float = 20.0
    min_rsi: float = 40.0
    max_rsi: float = 68.0
    notes: str = ""


def sell_credit(px: float) -> float:
    """Selling a leg receives less than the traded print."""
    return max(TICK, px * (1 - SPREAD_PCT) - SLIP_TICKS * TICK)


def buy_debit(px: float) -> float:
    return px * (1 + SPREAD_PCT) + SLIP_TICKS * TICK


def daily_with_rsi() -> pd.DataFrame:
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    c = d["close"]
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi14"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    d["sess"] = d["datetime"].dt.date
    return d


def run(spec: WSpec, sessions: List[date], daily: pd.DataFrame, store: pd.DataFrame,
        chains: ChainIndex, expiries: List[date], skips: Dict[str, int]) -> List[Dict]:
    dpos = {v: i for i, v in enumerate(daily["sess"])}
    index_close = dict(zip(daily["sess"], daily["close"].astype(float)))
    sess_list = list(daily["sess"])
    spos = {v: i for i, v in enumerate(sess_list)}
    out: List[Dict] = []
    used = set()

    def bump(k):
        skips[k] = skips.get(k, 0) + 1

    for sess in sessions:
        i = dpos.get(sess)
        if i is None or i < 60:
            bump("NO_HISTORY"); continue
        prior = daily.iloc[i - 1]                       # strictly completed
        vix, rsi = float(prior["vix"]), float(prior["rsi14"])
        if not np.isfinite(vix) or not np.isfinite(rsi):
            bump("NO_REGIME"); continue
        if vix >= spec.max_vix:
            bump("VIX_BLOCK"); continue
        if not (spec.min_rsi <= rsi <= spec.max_rsi):
            bump("RSI_BLOCK"); continue

        nxt = [e for e in expiries if e > sess]
        if not nxt:
            bump("NO_EXPIRY"); continue
        expiry = nxt[0]
        if expiry in used:
            bump("EXPIRY_USED"); continue
        ep, cp = spos.get(expiry), spos.get(sess)
        if ep is None or cp is None or ep - cp != spec.hold_sessions:
            bump("NOT_ENTRY_SESSION"); continue

        settle = chains.settlement(expiry, index_close)
        if settle is None:
            bump("NO_SETTLEMENT"); continue
        chain = chains.chain(sess, expiry)
        if chain.empty:
            bump("NO_CHAIN"); continue

        spot = float(daily.iloc[i]["close"])
        em = spot * (vix / 100.0) * np.sqrt(5.0 / 365.0)
        step = 50.0
        call_k = round((spot + spec.short_sd * em) / step) * step
        put_k = round((spot - spec.short_sd * em) / step) * step
        w = spec.wing_steps * step

        if spec.legs == "condor":
            want = [("short_call", "CE", "SELL", call_k), ("long_call", "CE", "BUY", call_k + w),
                    ("short_put", "PE", "SELL", put_k), ("long_put", "PE", "BUY", put_k - w)]
        elif spec.legs == "vertical_put":
            want = [("short_put", "PE", "SELL", put_k), ("long_put", "PE", "BUY", put_k - w)]
        elif spec.legs == "vertical_call":
            want = [("short_call", "CE", "SELL", call_k), ("long_call", "CE", "BUY", call_k + w)]
        else:  # vertical_auto — sell the side spot is further from
            if (call_k - spot) >= (spot - put_k):
                want = [("short_call", "CE", "SELL", call_k), ("long_call", "CE", "BUY", call_k + w)]
            else:
                want = [("short_put", "PE", "SELL", put_k), ("long_put", "PE", "BUY", put_k - w)]

        legs, bad, lot = [], False, None
        for role, ot, side, k in want:
            r = chain[(chain["StrkPric"] == k) & (chain["OptnTp"] == ot)]
            if r.empty:
                bad = True; break
            rr = r.iloc[0]
            if int(rr["TtlTradgVol"]) <= 0 or float(rr["ClsPric"]) <= 0:
                bad = True; break
            if "NewBrdLotQty" not in rr.index or not pd.notna(rr["NewBrdLotQty"]) \
                    or int(rr["NewBrdLotQty"]) <= 0:
                bad = True; break
            q = int(rr["NewBrdLotQty"])
            lot = q if lot is None else lot
            if q != lot:
                bad = True; break
            px = float(rr["ClsPric"])
            fill = sell_credit(px) if side == "SELL" else buy_debit(px)
            intr = max(0.0, settle - k) if ot == "CE" else max(0.0, k - settle)
            legs.append({"role": role, "type": ot, "side": side, "strike": k,
                         "traded": px, "fill": round(fill, 2), "exit": round(intr, 2),
                         "qty": q})
        if bad or not legs:
            bump("LEG_UNPRICEABLE"); continue

        gross = sum((1 if l["side"] == "BUY" else -1) * (l["exit"] - l["fill"]) * l["qty"]
                    for l in legs)
        credit = sum((-1 if l["side"] == "BUY" else 1) * l["fill"] for l in legs)
        costs = sum(condor_leg_costs(l["side"], l["fill"], l["exit"], l["qty"]) for l in legs)
        # defined risk: widest spread minus credit
        if spec.legs == "condor":
            width = max(w, w)
        else:
            width = w
        max_risk = (width - credit) * lot

        used.add(expiry)
        out.append({
            "sess": str(sess), "expiry": str(expiry), "spot": spot, "settle": settle,
            "vix": vix, "rsi": rsi, "credit_pts": round(credit, 2),
            "width": width, "max_risk": round(max_risk, 2), "lot": lot,
            "gross": round(gross, 2), "costs": round(costs, 2),
            "net": round(gross - costs, 2), "legs": legs, "n_legs": len(legs),
        })
    return out


def metrics(trades: List[Dict], n_cycles: int) -> Dict[str, Any]:
    if not trades:
        return {"trades": 0, "net": 0.0}
    df = pd.DataFrame(trades)
    net = df["net"]
    wins, losses = net[net > 0], net[net <= 0]
    eq = net.cumsum()
    dd = float((eq - eq.cummax()).min())
    streak = mx = 0
    for x in net:
        if x <= 0:
            streak += 1; mx = max(mx, streak)
        else:
            streak = 0
    a = net.values.astype(float)
    t = float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))) if len(a) > 2 and a.std(ddof=1) else 0.0
    return {
        "trades": len(df), "win_rate": round(float((net > 0).mean() * 100), 1),
        "gross": round(float(df["gross"].sum()), 2),
        "costs": round(float(df["costs"].sum()), 2),
        "net": round(float(net.sum()), 2),
        "expectancy": round(float(net.mean()), 2),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3)
        if len(losses) and losses.sum() != 0 else None,
        "max_dd": round(abs(dd), 2), "max_losing_streak": mx,
        "avg_win": round(float(wins.mean()), 2) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else None,
        "avg_credit_pts": round(float(df["credit_pts"].mean()), 2),
        "avg_max_risk": round(float(df["max_risk"].mean()), 2),
        "max_max_risk": round(float(df["max_risk"].max()), 2),
        "ret_on_risk": round(float(net.sum() / df["max_risk"].mean() / len(df) * 100), 3),
        "ret_on_avg_risk_total": round(float(net.sum() / df["max_risk"].mean() * 100), 2),
        "tstat": round(t, 2),
    }


def show(name: str, m: Dict) -> str:
    if m.get("trades", 0) == 0:
        return f"{name:26}  no trades"
    return (f"{name:26}n={m['trades']:>4} win={m['win_rate']:>5.1f}% "
            f"gross={m['gross']:>9,.0f} costs={m['costs']:>8,.0f} net={m['net']:>9,.0f} "
            f"exp={m['expectancy']:>7,.0f} pf={str(m['profit_factor']):>6} "
            f"dd={m['max_dd']:>8,.0f} risk={m['avg_max_risk']:>8,.0f} t={m['tstat']:>5.2f}")


def main() -> int:
    daily = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    all_sess = sorted(set(store["TradDt"].unique()))
    dev = [d for d in all_sess if d <= DEV_END]
    val = [d for d in all_sess if DEV_END < d <= VAL_END]
    print(f"DEV {len(dev)} sessions {dev[0]}..{dev[-1]} | VAL {len(val)} {val[0]}..{val[-1]}")

    specs = [
        WSpec("condor_1.8sd_w4", "condor", 1.8, 4, notes="Bot 1 as built"),
        WSpec("condor_1.5sd_w4", "condor", 1.5, 4, notes="closer shorts"),
        WSpec("condor_2.2sd_w4", "condor", 2.2, 4, notes="further shorts"),
        WSpec("vert_auto_1.8sd_w4", "vertical_auto", 1.8, 4, notes="2 legs, safer side"),
        WSpec("vert_auto_1.5sd_w4", "vertical_auto", 1.5, 4, notes="2 legs, closer"),
        WSpec("vert_put_1.8sd_w4", "vertical_put", 1.8, 4, notes="bull put only"),
        WSpec("vert_call_1.8sd_w4", "vertical_call", 1.8, 4, notes="bear call only"),
        WSpec("vert_auto_1.8sd_w2", "vertical_auto", 1.8, 2, notes="narrow wing = less risk"),
        WSpec("vert_auto_1.8sd_w8", "vertical_auto", 1.8, 8, notes="wide wing = more credit"),
        WSpec("condor_1.8sd_w2", "condor", 1.8, 2, notes="narrow wings"),
    ]

    print("\n" + "=" * 132)
    print("DEV")
    print("=" * 132)
    dev_m = {}
    for s in specs:
        sk = {}
        tr = run(s, dev, daily, store, chains, expiries, sk)
        m = metrics(tr, len(dev))
        dev_m[s.name] = m
        print(show(s.name, m))

    print("\n" + "=" * 132)
    print("VALIDATION")
    print("=" * 132)
    val_m = {}
    for s in specs:
        sk = {}
        tr = run(s, val, daily, store, chains, expiries, sk)
        m = metrics(tr, len(val))
        val_m[s.name] = m
        print(show(s.name, m))

    print("\n" + "=" * 132)
    print("PROMOTION GATE — positive on DEV and VAL, >= 15 VAL trades")
    print("=" * 132)
    print(f"{'candidate':26}{'DEV net':>11}{'DEV t':>7}{'VAL net':>11}{'VAL t':>7}"
          f"{'VAL exp':>9}{'VAL PF':>8}  verdict")
    promoted = []
    for s in specs:
        dm, vm = dev_m[s.name], val_m[s.name]
        ok = dm.get("net", 0) > 0 and vm.get("net", 0) > 0 and vm.get("trades", 0) >= 15
        if ok:
            promoted.append(s.name)
        print(f"{s.name:26}{dm.get('net',0):>11,.0f}{dm.get('tstat',0):>7.2f}"
              f"{vm.get('net',0):>11,.0f}{vm.get('tstat',0):>7.2f}"
              f"{vm.get('expectancy',0):>9,.0f}{str(vm.get('profit_factor')):>8}"
              f"  {'PROMOTE' if ok else 'reject'}")
    print(f"\nPROMOTED: {promoted or 'NONE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
