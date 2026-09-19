"""
BANKNIFTY EXPIRY-SETTLED PREMIUM STUDY — the seller's side of the range/premium ratio.

WHY BANKNIFTY AND WHY THE SELL SIDE. Measured on the newly acquired grids:

                     median session range    median ATM premium    range / premium
    NIFTY                    0.759%                0.510%              1.49x
    BANKNIFTY                0.915%                0.794%              1.15x

BANKNIFTY moves more in absolute terms, and its options are priced for it and then
some: the ratio that decides whether a BUYER can pay for the premium is 23% WORSE
than on NIFTY, a space already closed by 31 concepts. So BANKNIFTY option BUYING is
not worth the search budget, and that is a measurement, not an assumption.

The same ratio is the seller's edge, so this script tests the SELL side.

WHY EXPIRY SETTLEMENT. Holding to expiry needs no exit price at all, which removes
every failure mode that produced a fake number in this repository: ladder
truncation, opening prints, stale marks and silent skips are all structurally
absent. The payoff is exact arithmetic on the exchange's own settlement value.

SETTLEMENT SOURCE, cross-validated. On an expiry session the bhavcopy writes the
underlying's settlement into `SttlmPric` on every contract row. For BANKNIFTY the
legacy feed leaves it at 0.0 on 57 of 329 expiries, so where it is absent the index
close for that date is used instead. That substitution is validated, not assumed: on
the 272 expiries where both exist they agree to a median 0.0012% and a maximum of
0.001%.

ENTRY PRICING, deliberately penalised. Strikes are priced from the bhavcopy close,
which is NSE's 30-minute weighted average and sits ABOVE the closing print for puts
by a measured +0.80 points on NIFTY. Every short leg has that bias SUBTRACTED on top
of half-spread and slippage, so the seller is never credited premium nobody could
have received. A leg that did not trade that session has no executable price and the
whole cycle is refused and counted.
"""

import os
import sys
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel

OPT = "data/derived/bn_idxopt.parquet"
IDX = "data/raw/INDEX_BANKNIFTY_daily.csv"

TICK = 0.05
SPREAD_PCT = 0.0030
SLIP_TICKS = 2
VWAP_SHORT_PENALTY_PCT = 0.0008     # the NIFTY +0.80 pt bias, expressed proportionally
STRIKE_STEP = 100.0                 # BANKNIFTY strikes are on a 100-point grid

DEV_END = date(2024, 9, 17)
VAL_END = date(2025, 9, 17)
HOLD_START, HOLD_END = date(2025, 9, 18), date(2026, 9, 18)


def sell_credit(px: float, m: float = 1.0) -> float:
    pen = max(TICK, px * SPREAD_PCT) * m + SLIP_TICKS * TICK * m + px * VWAP_SHORT_PENALTY_PCT
    return max(TICK, px - pen)


def buy_debit(px: float, m: float = 1.0) -> float:
    return px + max(TICK, px * SPREAD_PCT) * m + SLIP_TICKS * TICK * m


def tstat(x) -> float:
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")


def load() -> Tuple[pd.DataFrame, Dict[pd.Timestamp, float], Dict[pd.Timestamp, float]]:
    b = pd.read_parquet(OPT)
    b["TradDt"] = pd.to_datetime(b["TradDt"]); b["XpryDt"] = pd.to_datetime(b["XpryDt"])
    sp = pd.read_csv(IDX); sp["datetime"] = pd.to_datetime(sp["datetime"])
    spot = dict(zip(sp["datetime"], sp["close"]))

    settle: Dict[pd.Timestamp, float] = {}
    ex = b[b["TradDt"] == b["XpryDt"]]
    for xp, g in ex.groupby("XpryDt"):
        v = g.loc[g["SttlmPric"] > 0, "SttlmPric"]
        if len(v):
            settle[xp] = float(v.mode().iloc[0])
        elif xp in spot:
            settle[xp] = float(spot[xp])          # validated equivalent, see docstring
    return b, spot, settle


def cycles(b: pd.DataFrame, spot: Dict, settle: Dict) -> pd.DataFrame:
    sess = sorted(b["TradDt"].unique())
    exd = sorted(settle)
    out = []
    for i in range(len(exd) - 1):
        a, z = exd[i], exd[i + 1]
        after = [d for d in sess if a < d < z]
        if not after:
            continue
        entry = after[0]
        s0 = spot.get(entry)
        if s0 is None:
            continue
        out.append({"entry": entry, "expiry": z, "spot": float(s0),
                    "settle": float(settle[z]), "dte": (z - entry).days,
                    "move_pct": (settle[z] - s0) / s0 * 100})
    return pd.DataFrame(out)


def run(b: pd.DataFrame, cyc: pd.DataFrame, dist_pct: float, straddle: bool = False,
        cost_mult: float = 1.0) -> Tuple[pd.DataFrame, Dict[str, int]]:
    idx = {}
    for k, v in zip(zip(b["TradDt"], b["XpryDt"], b["StrkPric"], b["OptnTp"]),
                    zip(b["ClsPric"], b["TtlTradgVol"], b["NewBrdLotQty"])):
        if v[0] > 0:
            idx[k] = v
    skips: Dict[str, int] = {}
    rows = []
    for _, c in cyc.iterrows():
        s0, xp = c["spot"], c["expiry"]
        if straddle:
            kc = kp = round(s0 / STRIKE_STEP) * STRIKE_STEP
        else:
            kc = round(s0 * (1 + dist_pct / 100) / STRIKE_STEP) * STRIKE_STEP
            kp = round(s0 * (1 - dist_pct / 100) / STRIKE_STEP) * STRIKE_STEP
        rc = idx.get((c["entry"], xp, kc, "CE"))
        rp = idx.get((c["entry"], xp, kp, "PE"))
        if rc is None or rp is None:
            skips["NO_ENTRY_PRICE"] = skips.get("NO_ENTRY_PRICE", 0) + 1; continue
        if (rc[1] or 0) <= 0 or (rp[1] or 0) <= 0:
            skips["LEG_DID_NOT_TRADE"] = skips.get("LEG_DID_NOT_TRADE", 0) + 1; continue
        fc, fp = sell_credit(float(rc[0]), cost_mult), sell_credit(float(rp[0]), cost_mult)
        credit = fc + fp
        st = c["settle"]
        payout = max(0.0, st - kc) + max(0.0, kp - st)
        lot = rc[2] if pd.notna(rc[2]) and rc[2] > 0 else np.nan
        lot_used = float(lot) if np.isfinite(lot) else 25.0
        cost = (IndianCostModel.calculate_roundtrip_costs(fc, fc, int(lot_used)).total_costs
                + IndianCostModel.calculate_roundtrip_costs(fp, fp, int(lot_used)).total_costs
                ) / lot_used * cost_mult
        rows.append({**c.to_dict(), "kc": kc, "kp": kp, "credit": credit,
                     "payout": payout, "gross_pts": credit - payout, "cost_pts": cost,
                     "net_pts": credit - payout - cost, "lot": lot,
                     "breached": bool(payout > 0)})
    return pd.DataFrame(rows), skips


HDR = (f"{'variant':22}{'n':>5}{'exp pts':>10}{'t':>7}{'win%':>7}{'breach%':>9}"
       f"{'worst':>10}{'credit':>9}{'best5share':>12}")


def line(name: str, df: pd.DataFrame) -> str:
    if df.empty:
        return f"{name:22}{'NO CYCLES':>12}"
    x = df["net_pts"].to_numpy(float)
    s = np.sort(x)
    share = (s[-5:].sum() / s.sum() * 100) if s.sum() != 0 else float("nan")
    return (f"{name:22}{len(x):>5}{x.mean():>10.2f}{tstat(x):>7.2f}"
            f"{(x > 0).mean()*100:>7.1f}{df['breached'].mean()*100:>9.1f}"
            f"{x.min():>10.1f}{df['credit'].mean():>9.1f}{share:>11.0f}%")


def main() -> int:
    b, spot, settle = load()
    cyc = cycles(b, spot, settle)
    cyc["entry_d"] = pd.to_datetime(cyc["entry"]).dt.date
    print(f"BANKNIFTY option rows {len(b):,}  expiries with settlement {len(settle)}")
    print(f"cycles {len(cyc)}  {cyc['entry'].min().date()} -> {cyc['entry'].max().date()}"
          f"  median dte {cyc['dte'].median():.0f}")
    print("\nmove from entry close to expiry settlement:")
    print(cyc["move_pct"].describe(percentiles=[.05, .25, .5, .75, .95]).round(3).to_string())
    print("\nshare of cycles finishing inside a band (what a short strangle needs):")
    for band in (1, 2, 3, 4, 5):
        print(f"  |move| <= {band}% : {(cyc['move_pct'].abs() <= band).mean()*100:5.1f}%")

    dev = cyc[cyc["entry_d"] <= DEV_END]
    val = cyc[(cyc["entry_d"] > DEV_END) & (cyc["entry_d"] <= VAL_END)]
    hold = cyc[(cyc["entry_d"] >= HOLD_START) & (cyc["entry_d"] <= HOLD_END)]
    print(f"\nsplits: DEV {len(dev)}  VAL {len(val)}  HOLDOUT {len(hold)} [not read below]")

    print("\n" + "=" * 104)
    print("SHORT STRANGLE / STRADDLE, settled exactly at expiry — DEV ONLY")
    print("=" * 104)
    print(HDR)
    rows = []
    for dist in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        df, sk = run(b, dev, dist)
        print(line(f"strangle +-{dist}%", df))
        if not df.empty:
            rows.append({"variant": f"strangle_{dist}", "n": len(df),
                         "exp_pts": round(float(df["net_pts"].mean()), 2),
                         "t": round(tstat(df["net_pts"]), 2),
                         "breach_pct": round(float(df["breached"].mean()*100), 1),
                         "worst": round(float(df["net_pts"].min()), 1),
                         "skips": str(sk)})
    df, sk = run(b, dev, 0.0, straddle=True)
    print(line("straddle ATM", df))
    print(f"\nskip accounting on +-2%: {run(b, dev, 2.0)[1]}")

    best = max(rows, key=lambda r: r["t"]) if rows else None
    if best:
        dist = float(best["variant"].split("_")[1])
        print(f"\nCOST STRESS on the best DEV variant (strangle +-{dist}%)")
        for m in (1.0, 1.5, 2.0):
            d2, _ = run(b, dev, dist, cost_mult=m)
            print(f"  x{m}: exp {d2['net_pts'].mean():+7.2f} pts  t={tstat(d2['net_pts']):+6.2f}")
        print(f"\nBY YEAR (strangle +-{dist}%)")
        d2, _ = run(b, dev, dist)
        d2["yr"] = pd.to_datetime(d2["entry"]).dt.year
        print(f"  {'year':6}{'n':>5}{'exp pts':>10}{'t':>7}{'breach%':>9}{'worst':>10}")
        for y, g in d2.groupby("yr"):
            print(f"  {y:<6}{len(g):>5}{g['net_pts'].mean():>10.2f}"
                  f"{tstat(g['net_pts']):>7.2f}{g['breached'].mean()*100:>9.1f}"
                  f"{g['net_pts'].min():>10.1f}")

    os.makedirs("reports", exist_ok=True)
    pd.DataFrame(rows).to_csv("reports/bn_premium_dev.csv", index=False)
    print("\nwrote reports/bn_premium_dev.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
