"""
WEEKLY CYCLE STUDY — short strangle/straddle over one full expiry cycle.

SOURCE. Durgia, "Weekly Behavior of the Nifty Index: A Comprehensive Decade-Long
Study for Strategic Option Selling from Friday to Thursday" (SSRN 5353404, 2015-2025).
The abstract's reproducible core is a calendar claim: measure NIFTY from the open
of the session after one weekly expiry to the close of the next expiry, and use
that distribution to size a systematic weekly option SALE. The paper itself returns
HTTP 403 to automated fetches, so only the rules implied by its own title and
abstract are reproduced here, and no numeric claim from it is treated as evidence.
The "Friday to Thursday" anchor is generalised to "the session after one expiry, to
the next expiry", because NIFTY's weekly expiry weekday changed during the sample.

WHY THIS IS WORTH ONE MORE TEST after the weekly condor was closed: settling at
expiry needs NO exit price at all. The bhavcopy writes the underlying's final
settlement value into `SttlmPric` on every expiry session, so each cycle's payoff
is exact arithmetic on an authentic print. Every failure mode that produced a fake
number in this repository — ladder truncation, opening prints, stale marks, silent
skips — is structurally absent. If a weekly short premium edge exists, this is the
cleanest possible way to see it.

ENTRY PRICING, deliberately penalised. Strikes 1.5-3% out sit outside the 5-minute
grid's ATM+-6 ladder, so entry must come from the bhavcopy `ClsPric`, which is
NSE's 30-minute weighted average and sits a measured +0.80 points ABOVE the 15:2x
print for puts. Selling at it would credit premium nobody could receive, so
VWAP_SHORT_PENALTY subtracts that measured bias from every short leg's fill, on top
of the usual half-spread and slippage.
"""

import os
import sys
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel
from src.research.overnight import (
    DEV_END, HOLDOUT_END, HOLDOUT_START, VAL_END, VAL_START, sell_fill, tstat,
)

BHAV = "data/raw/nse/fo_bhavcopy/.consolidated_1904_1789736982937725100.parquet"
VWAP_SHORT_PENALTY = 0.80          # measured bias of ClsPric above the 15:2x print
STRIKE_STEP = 50.0


def load() -> Tuple[pd.DataFrame, pd.DataFrame]:
    bh = pd.read_parquet(BHAV, columns=[
        "TradDt", "XpryDt", "StrkPric", "OptnTp", "ClsPric", "SttlmPric",
        "TtlTradgVol", "OpnIntrst", "NewBrdLotQty"])
    bh["TradDt"] = pd.to_datetime(bh["TradDt"])
    bh["XpryDt"] = pd.to_datetime(bh["XpryDt"])
    panel = pd.read_parquet("data/derived/chain_panel.parquet")
    panel["date"] = pd.to_datetime(panel["date"])
    return bh, panel


def cycles(panel: pd.DataFrame) -> List[Dict]:
    """
    One row per weekly cycle: the FIRST session strictly after an expiry (the entry
    session) and the expiry it runs to, with that expiry's authentic settlement.
    """
    p = panel.sort_values("date").reset_index(drop=True)
    exp_rows = p[p["dte"] == 0]
    out: List[Dict] = []
    for i in range(len(exp_rows) - 1):
        prev_exp = exp_rows.iloc[i]
        nxt_exp = exp_rows.iloc[i + 1]
        after = p[(p["date"] > prev_exp["date"]) & (p["date"] < nxt_exp["date"])]
        if after.empty:
            continue
        entry = after.iloc[0]
        settle = nxt_exp["expiry_settle"]
        if not np.isfinite(settle) or settle <= 0:
            continue
        out.append({
            "entry_date": entry["date"], "expiry_date": nxt_exp["date"],
            "entry_spot": float(entry["close"]), "settle": float(settle),
            "expiry_of_entry": entry["near_expiry"],
            "vix": float(entry["vix"]), "straddle_pct": float(entry["straddle_pct"]),
            "pcr_oi": float(entry["pcr_oi"]), "rv20": float(entry["rv20"]),
            "vrp": float(entry["vrp"]), "dte": int(entry["dte"]),
            "lot": float(entry["lot_size"]) if np.isfinite(entry["lot_size"]) else np.nan,
            "move_pct": (float(settle) - float(entry["close"])) / float(entry["close"]) * 100,
        })
    return out


def run(cyc: List[Dict], bh: pd.DataFrame, dist_pct: float,
        straddle: bool = False, cost_mult: float = 1.0,
        filt=None) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Sell one CE dist_pct above and one PE dist_pct below (or an ATM straddle), hold
    to expiry, settle exactly. Returns points per unit.
    """
    idx = {}
    for (d, x, k, t), c in zip(
            zip(bh["TradDt"], bh["XpryDt"], bh["StrkPric"], bh["OptnTp"]), bh["ClsPric"]):
        if c > 0:
            idx[(d, x, float(k), t)] = float(c)
    skips: Dict[str, int] = {}
    rows = []
    for c in cyc:
        if filt is not None and not filt(c):
            skips["FILTER"] = skips.get("FILTER", 0) + 1
            continue
        # the contract must be the one expiring at the cycle's end
        xp = pd.Timestamp(c["expiry_date"])
        s0 = c["entry_spot"]
        if straddle:
            kc = kp = round(s0 / STRIKE_STEP) * STRIKE_STEP
        else:
            kc = round(s0 * (1 + dist_pct / 100) / STRIKE_STEP) * STRIKE_STEP
            kp = round(s0 * (1 - dist_pct / 100) / STRIKE_STEP) * STRIKE_STEP
        pc = idx.get((pd.Timestamp(c["entry_date"]), xp, kc, "CE"))
        pp = idx.get((pd.Timestamp(c["entry_date"]), xp, kp, "PE"))
        if pc is None or pp is None:
            skips["NO_ENTRY_PRICE"] = skips.get("NO_ENTRY_PRICE", 0) + 1
            continue
        fc = max(0.05, sell_fill(pc, cost_mult) - VWAP_SHORT_PENALTY)
        fp = max(0.05, sell_fill(pp, cost_mult) - VWAP_SHORT_PENALTY)
        credit = fc + fp
        st = c["settle"]
        payout = max(0.0, st - kc) + max(0.0, kp - st)        # exact, at settlement
        lot = c["lot"] if np.isfinite(c["lot"]) else 65.0
        # only the ENTRY is a traded order; expiry settlement is not a sell order,
        # but STT on exercised/settled options applies, so charge a round trip
        cost = (IndianCostModel.calculate_roundtrip_costs(fc, fc, int(lot)).total_costs
                + IndianCostModel.calculate_roundtrip_costs(fp, fp, int(lot)).total_costs
                ) / lot * cost_mult
        rows.append({**c, "kc": kc, "kp": kp, "credit": credit, "payout": payout,
                     "gross_pts": credit - payout, "cost_pts": cost,
                     "net_pts": credit - payout - cost, "lot": lot,
                     "breached": bool(payout > 0)})
    return pd.DataFrame(rows), skips


def summary(df: pd.DataFrame, label: str) -> str:
    if df.empty:
        return f"{label:26}{'NO CYCLES':>12}"
    x = df["net_pts"].to_numpy(float)
    return (f"{label:26}{len(x):>6}{x.mean():>10.2f}{tstat(x):>8.2f}"
            f"{(x > 0).mean()*100:>8.1f}{df['breached'].mean()*100:>9.1f}"
            f"{x.min():>10.1f}{df['credit'].mean():>9.1f}"
            f"{(df['net_pts']*df['lot']).sum():>12,.0f}")


HDR = (f"{'variant':26}{'n':>6}{'exp pts':>10}{'t':>8}{'win%':>8}{'breach%':>9}"
       f"{'worst':>10}{'credit':>9}{'net Rs':>12}")


def main() -> None:
    bh, panel = load()
    cyc = cycles(panel)
    dev = [c for c in cyc if c["entry_date"].date() <= DEV_END]
    val = [c for c in cyc if VAL_START <= c["entry_date"].date() <= VAL_END]
    hold = [c for c in cyc if HOLDOUT_START <= c["entry_date"].date() <= HOLDOUT_END]
    print(f"weekly cycles: total {len(cyc)}  DEV {len(dev)}  VAL {len(val)}  HOLDOUT {len(hold)}")
    print(f"DEV {dev[0]['entry_date'].date()} -> {dev[-1]['entry_date'].date()}\n")

    d = pd.DataFrame(dev)
    print("THE CALENDAR CLAIM ITSELF — entry-close to next-expiry-settlement move, DEV")
    print(d["move_pct"].describe(percentiles=[.05, .25, .5, .75, .95]).round(3).to_string())
    print(f"\nshare of cycles whose |move| stays inside a band (this is what a short "
          f"strangle needs):")
    for b in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        print(f"  |move| <= {b:>4.1f}% : {(d['move_pct'].abs() <= b).mean()*100:>5.1f}%"
              f"   mean straddle at entry {d['straddle_pct'].mean():.2f}% of spot")
    print()

    print("SHORT WEEKLY STRANGLE / STRADDLE, settled exactly at expiry — DEV ONLY")
    print(HDR)
    rows = []
    for dist in (1.0, 1.5, 2.0, 2.5, 3.0):
        df, sk = run(dev, bh, dist)
        print(summary(df, f"strangle +-{dist}%"))
        rows.append({"variant": f"strangle_{dist}", "split": "DEV", "n": len(df),
                     "exp_pts": round(float(df['net_pts'].mean()), 3) if len(df) else None,
                     "t": round(tstat(df['net_pts'].to_numpy(float)), 2) if len(df) else None,
                     "skips": str(sk)})
    df, sk = run(dev, bh, 0.0, straddle=True)
    print(summary(df, "straddle ATM"))
    print(f"\nskip accounting on the +-2% variant: {run(dev, bh, 2.0)[1]}")

    print("\nCOST STRESS on the best DEV variant family (strangle +-2%)")
    print(f"{'mult':8}{'exp pts':>10}{'t':>8}")
    for m in (1.0, 1.5, 2.0):
        df, _ = run(dev, bh, 2.0, cost_mult=m)
        print(f"{m:<8.1f}{df['net_pts'].mean():>10.2f}"
              f"{tstat(df['net_pts'].to_numpy(float)):>8.2f}")

    print("\nBY YEAR (strangle +-2%, DEV)")
    df, _ = run(dev, bh, 2.0)
    df["yr"] = pd.to_datetime(df["entry_date"]).dt.year
    print(f"{'year':8}{'n':>5}{'exp pts':>10}{'t':>8}{'breach%':>9}{'worst':>10}")
    for y, g in df.groupby("yr"):
        x = g["net_pts"].to_numpy(float)
        print(f"{y:<8}{len(x):>5}{x.mean():>10.2f}{tstat(x):>8.2f}"
              f"{g['breached'].mean()*100:>9.1f}{x.min():>10.1f}")

    print("\nCONCENTRATION / TAIL (strangle +-2%, DEV)")
    s = df["net_pts"].sort_values()
    print(f"  net {s.sum():.0f} pts   -worst1 {s.iloc[1:].sum():.0f}   "
          f"-worst3 {s.iloc[3:].sum():.0f}   worst5 {list(s.head(5).round(0).astype(int))}")
    print(f"  a single unhedged breach can exceed the total credit of "
          f"{df['credit'].mean()*1:.0f} pts x many cycles; margin for a naked "
          f"strangle is ~2 x 12% of spot")

    os.makedirs("reports", exist_ok=True)
    pd.DataFrame(rows).to_csv("reports/weekly_cycle_dev.csv", index=False)
    print("\nwrote reports/weekly_cycle_dev.csv")


if __name__ == "__main__":
    main()
