"""
REGIME CHECK — is the weekly condor's edge specific to 2024-2026?

The rupee-denominated study can only run from 2024 onward: legacy NSE bhavcopy
carries no NewBrdLotQty, so the simulator fails closed on lot size and produces no
trade. That silently excludes COVID, 2021-22 and the pre-2024 expiry regime — the
exact conditions under which a short-premium structure is supposed to break.

An earlier study of this same bot over 158 cycles, 2019-2026, reported +2.90 pts
per cycle at t=+1.40 — no demonstrable edge. The 2024-2026 rupee study reports
t=6.86. Both cannot be describing the same strategy in the same way.

This script settles it by measuring the identical geometry in POINTS, which needs
no lot size, over the whole 2019-2026 store. Gates are the same as
weekly_premium_lab.run: strictly-prior VIX/RSI, exactly `hold` sessions before
expiry, one entry per expiry, real chain, real settlement, traded volume > 0.

GROSS ONLY. Costs are rupee quantities and cannot be computed without a lot size,
so they are omitted here and this understates nothing about the direction of the
question being asked: if the gross edge is regime-dependent, costs cannot rescue it.
"""

import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot1_condor_real import (
    ChainIndex, load_bhavcopy_store, weekly_expiry_calendar,
)
from scripts.research.weekly_premium_lab import buy_debit, daily_with_rsi, sell_credit

SD, WINGS, HOLD, STEP = 1.8, 4, 5, 50.0
MAX_VIX = 30.0


def build(daily, store, chains, expiries):
    dpos = {v: i for i, v in enumerate(daily["sess"])}
    index_close = dict(zip(daily["sess"], daily["close"].astype(float)))
    spos = {v: i for i, v in enumerate(list(daily["sess"]))}
    sessions = sorted(set(store["TradDt"].unique()))
    rows, skips, used = [], {}, set()

    def bump(k):
        skips[k] = skips.get(k, 0) + 1

    for sess in sessions:
        i = dpos.get(sess)
        if i is None or i < 60:
            bump("NO_HISTORY"); continue
        prior = daily.iloc[i - 1]
        vix, rsi = float(prior["vix"]), float(prior["rsi14"])
        if not np.isfinite(vix) or not np.isfinite(rsi):
            bump("NO_REGIME"); continue
        if vix >= MAX_VIX:
            bump("VIX_BLOCK"); continue
        nxt = [e for e in expiries if e > sess]
        if not nxt:
            bump("NO_EXPIRY"); continue
        expiry = nxt[0]
        if expiry in used:
            bump("EXPIRY_USED"); continue
        ep, cp = spos.get(expiry), spos.get(sess)
        if ep is None or cp is None or ep - cp != HOLD:
            bump("NOT_ENTRY_SESSION"); continue
        settle = chains.settlement(expiry, index_close)
        if settle is None:
            bump("NO_SETTLEMENT"); continue
        chain = chains.chain(sess, expiry)
        if chain.empty:
            bump("NO_CHAIN"); continue

        spot = float(daily.iloc[i]["close"])
        em = spot * (vix / 100.0) * np.sqrt(5.0 / 365.0)
        call_k = round((spot + SD * em) / STEP) * STEP
        put_k = round((spot - SD * em) / STEP) * STEP
        w = WINGS * STEP
        want = [("short_call", "CE", "SELL", call_k), ("long_call", "CE", "BUY", call_k + w),
                ("short_put", "PE", "SELL", put_k), ("long_put", "PE", "BUY", put_k - w)]

        legs, bad = [], False
        for role, ot, side, k in want:
            r = chain[(chain["StrkPric"] == k) & (chain["OptnTp"] == ot)]
            if r.empty:
                bad = True; break
            rr = r.iloc[0]
            if int(rr["TtlTradgVol"]) <= 0 or float(rr["ClsPric"]) <= 0:
                bad = True; break
            px = float(rr["ClsPric"])
            fill = sell_credit(px) if side == "SELL" else buy_debit(px)
            intr = max(0.0, settle - k) if ot == "CE" else max(0.0, k - settle)
            legs.append({"role": role, "side": side, "strike": k,
                         "fill": round(fill, 2), "exit": round(intr, 2)})
        if bad or len(legs) != 4:
            bump("LEG_UNPRICEABLE"); continue

        # per-unit (points) P&L, lot size deliberately not required
        gross = sum((1 if l["side"] == "BUY" else -1) * (l["exit"] - l["fill"]) for l in legs)
        credit = sum((-1 if l["side"] == "BUY" else 1) * l["fill"] for l in legs)
        used.add(expiry)
        rows.append({"entry": sess, "expiry": expiry, "yr": expiry.year, "spot": spot,
                     "settle": settle, "vix": vix, "credit": round(credit, 2),
                     "gross_pts": round(gross, 2), "width": w,
                     "sp": put_k, "sc": call_k,
                     "breach": bool(settle > call_k or settle < put_k)})
    return pd.DataFrame(rows), skips


def blk(d, lab):
    if len(d) < 2:
        print(f"{lab:28} n={len(d)}  (too few)"); return
    mu, sd, n = d.gross_pts.mean(), d.gross_pts.std(ddof=1), len(d)
    t = mu / (sd / np.sqrt(n)) if sd > 0 else float("nan")
    print(f"{lab:28} n={n:>4}  win={100*(d.gross_pts>0).mean():>5.1f}%  "
          f"gross={mu:>7.2f} pts  t={t:>6.2f}  breach={100*d.breach.mean():>5.1f}%  "
          f"worst={d.gross_pts.min():>8.2f}  credit={d.credit.mean():>6.2f}")


def main() -> int:
    daily = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    df, skips = build(daily, store, chains, expiries)
    if df.empty:
        print("NO CYCLES BUILT"); print(skips); return 1

    print(f"CYCLES (points basis): {len(df)}   {df.entry.min()} .. {df.entry.max()}")
    print(f"skips: {dict(sorted(skips.items(), key=lambda x: -x[1])[:6])}\n")
    blk(df, "ALL")
    print()
    for y in sorted(df.yr.unique()):
        blk(df[df.yr == y], f"  {y}")
    print()
    cut = date(2024, 1, 1)
    blk(df[df.entry < cut], "PRE-2024 (rupee study omits)")
    blk(df[df.entry >= cut], "2024+ (rupee study window)")

    print("\n=== FULL MAX-LOSS EVENTS (entire wing width lost) ===")
    ml = df[df.gross_pts <= -(df.width - df.credit) + 0.01]
    print(f"  {len(ml)} of {len(df)} cycles ({100*len(ml)/len(df):.1f}%)")
    for _, r in ml.iterrows():
        print(f"    {r.entry} -> {r.expiry}  settle {r.settle:>9.1f}  "
              f"shorts {r.sp:.0f}/{r.sc:.0f}  {r.gross_pts:>8.2f} pts")

    print("\n=== DEEPEST 10 LOSSES ===")
    for _, r in df.nsmallest(10, "gross_pts").iterrows():
        print(f"    {r.entry} -> {r.expiry}  {r.gross_pts:>8.2f} pts "
              f"({100*r.gross_pts/r.width:>6.1f}% of width)  settle {r.settle:>9.1f}  "
              f"shorts {r.sp:.0f}/{r.sc:.0f}  vix {r.vix:.1f}")

    df.to_csv("reports/condor_regime_points_2019_2026.csv", index=False)
    print("\nwrote reports/condor_regime_points_2019_2026.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
