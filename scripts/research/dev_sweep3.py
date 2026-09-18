"""
DEV SWEEP ROUND 3 — DEVELOPMENT SET ONLY. Last development round before validation.

Round 2 produced two independent, monotone axes rather than a single lucky cell:

    opening-range threshold   0.20 -> +40,496 | 0.25 -> +80,243 | 0.30 -> +63,169
                              0.35 -> +47,588 | 0.45 -> +22,099 | 0.55 -> +23,980
    reward/risk at OR>=0.35   1.0  -> +22,635 | 1.5  -> +47,588 | 2.0  -> +58,678
                              2.5  -> +81,409 | 3.0  -> +78,310

25 of 29 variants were net-positive, morning and afternoon both worked, and the
strike barely mattered. That is the signature of a conditioning effect rather than
an overfit cell.

Round 3 crosses the two axes ONCE and adds the one thing the study still lacks:
trade frequency. The best round-2 variant fires 0.14 times per session, which is
too rare to measure properly on a 125-session holdout. This round tests whether
allowing two or three attempts on a qualifying day keeps the edge.

After this round the development phase is CLOSED. Whatever leads goes to
validation unchanged.
"""

import os
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.concepts import orb
from src.research.lab2 import (
    Spec2, daily_frame, metrics2, option_index, session_panels, simulate2, split_sessions,
)
from scripts.research.dev_sweep2 import concentration, wide_filter

E = dtime
A = dict(entry_from=E(9, 30), entry_to=E(14, 30), flat_at=E(15, 15))


def build():
    C = []
    # ── the cross: threshold x reward/risk ──
    for th in (0.25, 0.30, 0.35):
        for rr in (1.5, 2.0, 2.5):
            C.append(Spec2(f"X_or{th:.2f}_rr{rr:.1f}", "orb",
                           wide_filter(orb("15", rr), th), **A,
                           notes=f"OR>={th}%  1:{rr}"))
    # ── frequency: more attempts on a qualifying day ──
    for n in (2, 3):
        for th in (0.25, 0.30):
            C.append(Spec2(f"N{n}_or{th:.2f}_rr2.5", "orb",
                           wide_filter(orb("15", 2.5), th), max_trades_per_day=n, **A,
                           notes=f"{n} attempts, OR>={th}%"))
    # ── a looser threshold only makes sense with more attempts; test it honestly ──
    C.append(Spec2("N3_or0.20_rr2.5", "orb", wide_filter(orb("15", 2.5), 0.20),
                   max_trades_per_day=3, **A, notes="3 attempts, OR>=0.20%"))
    # ── widen the entry window so later breaks are reachable ──
    C.append(Spec2("W_late_or0.25_rr2.5", "orb", wide_filter(orb("15", 2.5), 0.25),
                   max_trades_per_day=2, entry_from=E(9, 30), entry_to=E(15, 0),
                   flat_at=E(15, 20), notes="2 attempts, entry to 15:00"))
    return C


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV {len(dev)} sessions {dev[0]} .. {dev[-1]}   (VAL and HOLDOUT untouched)")

    C = build()
    print(f"candidates round 3: {len(C)}\n" + "=" * 128)
    print(f"{'candidate':24}{'n':>6}{'win%':>7}{'net':>11}{'exp':>8}{'PF':>7}"
          f"{'maxDD':>10}{'trd/d':>7}{'t':>7}{'avgCap':>9}  notes")
    print("-" * 128)
    res = {}
    for spec in C:
        tr = simulate2(spec, dev, daily, panels, opts, skips={})
        m = metrics2(tr, dev)
        res[spec.name] = (spec, tr, m)
        if m.get("trades", 0) == 0:
            print(f"{spec.name:24}{'NO TRADES':>10}"); continue
        print(f"{spec.name:24}{m['trades']:>6}{m['win_rate']:>7.1f}{m['net']:>11,.0f}"
              f"{m['expectancy']:>8,.0f}{str(m['profit_factor']):>7}{m['max_dd']:>10,.0f}"
              f"{m['trades_per_day']:>7.2f}{m['tstat']:>7.2f}{m['avg_capital']:>9,.0f}"
              f"  {spec.notes}")

    ok = [(n, r) for n, r in res.items() if r[2].get("trades", 0) > 0 and r[2]["net"] > 0]
    ok.sort(key=lambda x: -x[1][2]["tstat"])
    print("\n" + "=" * 128)
    print("RANKED BY t (DEV) — with concentration and payoff shape")
    print("=" * 128)
    for n, (spec, tr, m) in ok:
        print(f"  {n:24} t {m['tstat']:>5.2f}  net {m['net']:>9,.0f}  exp {m['expectancy']:>6,.0f}  "
              f"PF {str(m['profit_factor']):>6}  n {m['trades']:>4}  win {m['win_rate']:>5.1f}%  "
              f"payoff {str(m['payoff']):>5}")
        print(f"      {concentration(tr)}")
        print(f"      days: profitable {m['pct_days_profitable']}%  >=1% {m['pct_days_ge_1']}%  "
              f"traded {m['pct_sessions_traded']}%  exits {m['exit_reasons']}")
    pd.DataFrame([{"name": n, **r[2]} for n, r in res.items()]).to_csv(
        "reports/dev_sweep3_results.csv", index=False)
    print("\nwrote reports/dev_sweep3_results.csv")
    print("\nDEVELOPMENT PHASE CLOSED. Leads go to validation unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
