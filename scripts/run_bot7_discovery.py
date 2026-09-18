"""
Bot 7 — execute every candidate in the research ledger and judge it.

Each candidate was specified in `reports/BOT7_RESEARCH_LEDGER.md` before any
result was seen. This script runs them all, applies the same validation battery to
each, and records failures alongside successes. Nothing is tuned afterwards.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research import validation as V
from src.research import bot7_discovery as B7
from src.research.bot1_condor_real import load_bhavcopy_store
from src.research.bot56_real_option_model import load_option_grid_5m

# Every candidate executed counts toward the Bonferroni denominator, including
# the ones that fail and the perturbations run for robustness.
CANDIDATES_SPECIFIED = 5
PERTURBATIONS = 2                    # C2 lookback 5 and 10
VARIANTS_EXAMINED = CANDIDATES_SPECIFIED + PERTURBATIONS


def underlying(start: str = "2020-01-01") -> pd.DataFrame:
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner")
    return d[d["datetime"] >= start].sort_values("datetime").reset_index(drop=True)


def judge(tag: str, pnl: list, dates: list, out: dict, unit: str = "Rs",
          extra: dict | None = None) -> dict:
    """Apply the same battery to every candidate, and say plainly what it shows."""
    n = len(pnl)
    print(f"\n{'=' * 78}\n{tag}\n{'=' * 78}")
    if n < 20:
        print(f"  {n} trades — too few to judge. RECORDED AS INSUFFICIENT.")
        out[tag] = {"trades": n, "verdict": "INSUFFICIENT_SAMPLE"}
        return out[tag]

    a = np.array(pnl, dtype=float)
    t = V.tstat(pnl)
    mt = V.deflated_expectation(VARIANTS_EXAMINED, t, n)
    oos = V.chronological_split(pnl, dates)
    wf = V.walk_forward(pnl, dates, folds=4)
    mc = V.monte_carlo_paths(pnl)
    ctl = V.resample_control(pnl)

    print(f"  trades {n}   net {unit} {a.sum():,.0f}   expectancy {unit} {a.mean():,.2f}"
          f"   win% {(a > 0).mean() * 100:.1f}")
    print(f"  t={t:+.3f}  p_raw={mt.get('p_raw')}  p_bonferroni={mt.get('p_bonferroni')}"
          f"  survives={mt.get('survives_5pct_after_adjustment')}")
    if "is" in oos:
        print(f"  OOS 70/30 @ {oos['split_date']}: IS {oos['is']['mean']:+,.2f} | "
              f"OOS {oos['oos']['mean']:+,.2f} per trade | sign agrees {oos['sign_agreement']}")
    if "folds" in wf:
        print(f"  walk-forward {wf['folds_positive']}/{wf['folds_total']} folds positive  "
              + str([f"{f['start'][:7]}:{f['mean']:+,.0f}" for f in wf["folds"]]))
    print(f"  Monte Carlo P(total<0) {mc.get('prob_final_negative')}  "
          f"median MaxDD {mc.get('max_drawdown_median'):,.0f}")

    # Slippage decides candidates whose edge is small relative to the spread.
    step = max(abs(a.mean()) * 0.0001, 1.0)
    slips = [0.0, 0.25, 0.5, 1.0]
    sl = V.slippage_sensitivity(pnl, [s * 2 * B7.LOT for s in slips],
                                [f"+{s} pt/side" for s in slips])
    print("  slippage:", "  ".join(
        f"{r['label']}={r['net']:,.0f}{'+' if r['still_profitable'] else '-'}" for r in sl))

    profitable = a.sum() > 0
    survives = bool(mt.get("survives_5pct_after_adjustment")) and profitable
    consistent = wf.get("folds_positive", 0) == wf.get("folds_total", 0)
    slip_ok = all(r["still_profitable"] for r in sl)
    verdict = ("SURVIVED" if (survives and consistent and slip_ok)
               else "REJECTED")
    reasons = []
    if not profitable:
        reasons.append("net negative")
    if not mt.get("survives_5pct_after_adjustment"):
        reasons.append("fails multiple-testing adjustment")
    if not consistent:
        reasons.append(f"only {wf.get('folds_positive')}/{wf.get('folds_total')} folds positive")
    if not slip_ok:
        reasons.append("does not survive slippage")
    print(f"  VERDICT: {verdict}" + (f"  ({'; '.join(reasons)})" if reasons else ""))

    out[tag] = {
        "trades": n, "net": float(a.sum()), "expectancy": float(a.mean()),
        "win_rate": float((a > 0).mean() * 100), "tstat": t,
        "multiple_testing": mt, "oos": oos, "walk_forward": wf,
        "monte_carlo": mc, "resample_control": ctl, "slippage": sl,
        "verdict": verdict, "rejection_reasons": reasons,
        **(extra or {}),
    }
    return out[tag]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/bot7_discovery_results.json")
    args = ap.parse_args()

    grid = load_option_grid_5m()
    if grid is None:
        print("deep grid missing"); return 1
    d = underlying()
    print(f"underlying {len(d)} sessions {d['datetime'].min().date()}..{d['datetime'].max().date()}")
    out: dict = {"variants_examined": VARIANTS_EXAMINED,
                 "ledger": "reports/BOT7_RESEARCH_LEDGER.md"}

    # ── C1 ──
    t1 = B7.c1_overnight_gap(d, grid)
    judge("C1_overnight_gap", [x.net_pnl for x in t1], [x.date for x in t1], out,
          extra={"summary": B7.summarise(t1)})

    # ── C2 (specified n=7) plus the two declared perturbations ──
    for n in (7, 5, 10):
        tr = B7.c2_nr_breakout(d, grid, n=n)
        tag = f"C2_nr{n}_breakout" + ("" if n == 7 else "_PERTURBATION")
        judge(tag, [x.net_pnl for x in tr], [x.date for x in tr], out,
              extra={"summary": B7.summarise(tr)})

    # ── C4 ──
    t4 = B7.c4_opening_range(d, grid)
    judge("C4_opening_range", [x.net_pnl for x in t4], [x.date for x in t4], out,
          extra={"summary": B7.summarise(t4)})

    # ── C3 (defined-risk vertical, priced on bhavcopy) ──
    store = load_bhavcopy_store()
    if store is not None:
        t3 = B7.c3_vix_spread(d, store)
        judge("C3_vix_vertical", [x.net_points for x in t3], [x.entry_date for x in t3],
              out, unit="pts",
              extra={"mean_credit_points": float(np.mean([x.credit_points for x in t3])) if t3 else None,
                     "mean_loss_points": float(np.mean([x.loss_points for x in t3])) if t3 else None,
                     "sides": pd.Series([x.side for x in t3]).value_counts().to_dict() if t3 else {}})

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}")

    survived = [k for k, v in out.items() if isinstance(v, dict) and v.get("verdict") == "SURVIVED"]
    print(f"\n{'=' * 78}\nSURVIVING CANDIDATES: {survived or 'NONE'}\n{'=' * 78}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
