"""
VALIDATION — 2024-09-18 .. 2026-03-17 (371 sessions). The 6-month holdout stays shut.

Development ran ~75 variants across 31 concepts and three rounds. Its t-statistics
peaked near 1.8, which after that many looks is not evidence of anything. This is
the test.

Six candidates are carried forward unchanged, chosen on development t and on
concentration, with one deliberate family-diversity entry (channel break) so the
result is not six views of a single rule.

Development's claims, which validation exists to break:

  1. Conditioning on an already-wide opening range turns a large loser into a
     winner. Unconditional ORB lost Rs 119,344 over 996 trades; at OR >= 0.25%
     it made Rs 80,243 over 143.
  2. Wider reward/risk pays, monotonically to about 1:2.5, because a bought
     option is convex and must outrun theta plus two sides of spread.
  3. Extra attempts per day dilute rather than help, so only the first qualifying
     break is taken.

Cost sensitivity runs here, not after the holdout. A candidate that only clears
at base cost is not a candidate.
"""

import os
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.concepts import donchian, orb
from src.research.lab2 import (
    Spec2, daily_frame, metrics2, option_index, session_panels, simulate2, split_sessions,
)
from scripts.research.dev_sweep2 import concentration, wide_filter

E = dtime
A = dict(entry_from=E(9, 30), entry_to=E(14, 30), flat_at=E(15, 15))


def promoted():
    return [
        Spec2("V1_or0.25_rr1.5", "orb", wide_filter(orb("15", 1.5), 0.25), **A,
              notes="DEV t=1.70, n=143, best concentration"),
        Spec2("V2_or0.35_rr2.5", "orb", wide_filter(orb("15", 2.5), 0.35), **A,
              notes="DEV t=1.79, n=68, highest expectancy"),
        Spec2("V3_or0.30_rr2.5", "orb", wide_filter(orb("15", 2.5), 0.30), **A,
              notes="DEV t=1.65, n=102"),
        Spec2("V4_or0.25_rr2.5", "orb", wide_filter(orb("15", 2.5), 0.25), **A,
              notes="DEV t=1.53, n=143"),
        Spec2("V5_or0.30_rr1.5", "orb", wide_filter(orb("15", 1.5), 0.30), **A,
              notes="DEV t=1.49, n=102"),
        Spec2("V6_donch_or0.35", "trend", wide_filter(donchian(20, 1.5), 0.35), **A,
              notes="family diversity: channel break, same filter"),
    ]


def row(name, m, extra=""):
    if m.get("trades", 0) == 0:
        return f"{name:22}{'NO TRADES':>10}"
    return (f"{name:22}{m['trades']:>6}{m['win_rate']:>7.1f}{m['gross']:>11,.0f}"
            f"{m['costs']:>9,.0f}{m['net']:>11,.0f}{m['expectancy']:>8,.0f}"
            f"{str(m['profit_factor']):>7}{m['max_dd']:>10,.0f}{m['tstat']:>7.2f}{extra}")


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV {len(dev)} | VAL {len(val)} {val[0]}..{val[-1]} | HOLDOUT {len(hold)} FROZEN")

    C = promoted()
    hdr = (f"{'candidate':22}{'n':>6}{'win%':>7}{'gross':>11}{'costs':>9}{'net':>11}"
           f"{'exp':>8}{'PF':>7}{'maxDD':>10}{'t':>7}")

    print("\n" + "=" * 118)
    print("DEV (reference)")
    print("=" * 118 + "\n" + hdr)
    devres = {}
    for s in C:
        tr = simulate2(s, dev, daily, panels, opts, skips={})
        m = metrics2(tr, dev)
        devres[s.name] = m
        print(row(s.name, m))

    print("\n" + "=" * 118)
    print("VALIDATION  2024-09-18 .. 2026-03-17   <-- the test")
    print("=" * 118 + "\n" + hdr)
    valres = {}
    for s in C:
        tr = simulate2(s, val, daily, panels, opts, skips={})
        m = metrics2(tr, val)
        valres[s.name] = (m, tr)
        print(row(s.name, m))

    print("\n" + "=" * 118)
    print("COST SENSITIVITY ON VALIDATION — net at 1.0x / 1.5x / 2.0x the whole cost package")
    print("=" * 118)
    print(f"{'candidate':22}{'1.0x':>12}{'1.5x':>12}{'2.0x':>12}   survives 2x?")
    cost_ok = {}
    for s in C:
        nets = []
        for mult in (1.0, 1.5, 2.0):
            tr = simulate2(s, val, daily, panels, opts, cost_mult=mult, skips={})
            m = metrics2(tr, val)
            nets.append(m.get("net", 0.0))
        cost_ok[s.name] = nets[2] > 0
        print(f"{s.name:22}{nets[0]:>12,.0f}{nets[1]:>12,.0f}{nets[2]:>12,.0f}"
              f"   {'YES' if nets[2] > 0 else 'no'}")

    print("\n" + "=" * 118)
    print("PROMOTION GATE — positive on DEV and VAL, >= 20 VAL trades, survives 2x cost")
    print("=" * 118)
    print(f"{'candidate':22}{'DEV net':>12}{'VAL net':>12}{'VAL n':>7}{'VAL t':>8}"
          f"{'VAL PF':>8}  verdict")
    passed = []
    for s in C:
        dm, (vm, vtr) = devres[s.name], valres[s.name]
        dnet, vnet, vn = dm.get("net", 0.0), vm.get("net", 0.0), vm.get("trades", 0)
        ok = dnet > 0 and vnet > 0 and vn >= 20 and cost_ok[s.name]
        if ok:
            passed.append(s.name)
        print(f"{s.name:22}{dnet:>12,.0f}{vnet:>12,.0f}{vn:>7}"
              f"{vm.get('tstat', float('nan')):>8.2f}{str(vm.get('profit_factor')):>8}"
              f"  {'PROMOTE' if ok else 'reject'}")

    print(f"\nPROMOTED: {passed or 'NONE'}")
    for n in passed:
        m, tr = valres[n]
        print(f"\n--- {n} on VALIDATION ---")
        print(f"    concentration: {concentration(tr)}")
        for k in ("trades", "win_rate", "gross", "costs", "net", "expectancy", "avg_win",
                  "avg_loss", "payoff", "profit_factor", "realized_rr", "max_dd",
                  "max_losing_streak", "capital_deployed", "max_capital_used",
                  "avg_capital", "ret_on_deployed", "trades_per_day",
                  "pct_sessions_traded", "avg_daily_pct", "median_daily_pct",
                  "pct_days_profitable", "pct_days_ge_1", "pct_days_ge_2",
                  "best_day", "worst_day", "exit_reasons"):
            print(f"    {k:22s} {m.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
