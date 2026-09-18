"""
Bot 1 — run the authentic four-leg condor backtest and its validation battery.

Reports whatever the data says. No parameter is searched, no period is selected.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research.bot1_condor_real import (
    load_bhavcopy_store,
    run_real_condor_backtest,
    summarise_condor,
)


def underlying() -> pd.DataFrame:
    n = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    v = pd.read_csv("data/real_2026/INDEX_INDIAVIX_daily.csv")
    n["datetime"] = pd.to_datetime(n["datetime"])
    v["datetime"] = pd.to_datetime(v["datetime"])
    return n.merge(v[["datetime", "close"]].rename(columns={"close": "vix"}), on="datetime")


def show(tag: str, res: dict) -> dict:
    s = summarise_condor(res["trades"])
    print(f"\n=== {tag} ===")
    print(f"status={res['status']}  signal_lag={res['signal_lag']}")
    if s["total_trades"] == 0:
        print("  NO TRADES.  rejects:", dict(sorted(res["rejects"].items(), key=lambda x: -x[1])))
        return s
    for k in ("total_trades", "net_pnl_per_lot", "gross_pnl_per_lot", "total_costs_per_lot",
              "win_rate", "breach_rate", "avg_credit_points", "avg_max_loss_points",
              "avg_win", "avg_loss", "profit_factor", "max_drawdown_rupees_per_lot",
              "expectancy_per_trade"):
        v = s[k]
        print(f"  {k:32s} {v:>14.2f}" if isinstance(v, float) else f"  {k:32s} {v!s:>14}")
    print("  rejects:", dict(sorted(res["rejects"].items(), key=lambda x: -x[1])[:6]))
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/bot1_real_condor_results.json")
    args = ap.parse_args()

    store = load_bhavcopy_store()
    if store is None:
        print("NO BHAVCOPY STORE — run scripts/ingest_nse_fo_bhavcopy.py first")
        return 1
    print(f"bhavcopy store: {len(store):,} rows, "
          f"{store['TradDt'].nunique()} sessions, {store['XpryDt'].nunique()} expiries")

    d = underlying()
    out: dict = {"coverage": {
        "rows": int(len(store)), "sessions": int(store["TradDt"].nunique()),
        "expiries": int(store["XpryDt"].nunique()),
        "first": str(store["TradDt"].min()), "last": str(store["TradDt"].max()),
    }}

    base = run_real_condor_backtest(d, store, signal_lag=0)
    out["as_specified"] = show("AS SPECIFIED (research timing)", base)
    out["as_specified_trades"] = [
        {**{k: v for k, v in t.__dict__.items() if k != "legs"},
         "legs": [l.__dict__ for l in t.legs]} for t in base["trades"]
    ]

    causal = run_real_condor_backtest(d, store, signal_lag=1)
    out["causal_lag1"] = show("STRICTLY CAUSAL (signal from prior close)", causal)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
