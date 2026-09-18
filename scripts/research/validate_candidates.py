"""
VALIDATION — 2025-01-01 .. 2026-06-17. The holdout is still untouched.

Development produced two claims. Validation exists to break them:

  1. TARGET WIDTH dominates. Monotone on DEV across many specs, so it should
     survive if it is a property of option convexity rather than of 2020-2024.
  2. A 0.60 entry threshold is the sweet spot. This one is SUSPECT: DEV showed
     0.45 -> +Rs 39,619, 0.60 -> +Rs 63,714, 0.75 -> -Rs 19,623. A real threshold
     effect should not invert. If 0.60 is a pocket, validation will show it.

A candidate is promoted only if it is positive on BOTH DEV and VAL. Nothing here
is re-tuned; these are the exact specs DEV produced.
"""

import os
import sys
from datetime import time as dtime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.strategy_lab import (
    Spec, daily_frame, index_grid, money_metrics, simulate, split_sessions, tstat,
)
from scripts.research.candidates_dev import combo, make_threshold_signal


def specs():
    return [
        Spec("S_thr0.60_tgt0.50", make_threshold_signal(combo, 0.60), 0.50, 0.25,
             entry_from=dtime(11, 0), notes="DEV best"),
        Spec("S_thr0.60_tgt1.00", make_threshold_signal(combo, 0.60), 1.00, 0.25,
             entry_from=dtime(11, 0), notes="DEV 2nd"),
        Spec("C3_thr0.45_tgt0.50", make_threshold_signal(combo, 0.45), 0.50, 0.25,
             entry_from=dtime(11, 0), notes="round-1 best, looser entry"),
        Spec("W_tgt0.70_stp0.25", make_threshold_signal(combo, 0.45), 0.70, 0.25,
             entry_from=dtime(11, 0), notes="wide target"),
        Spec("W_no_target_stp0.25", make_threshold_signal(combo, 0.45), 99.0, 0.25,
             entry_from=dtime(11, 0), notes="stop only, ride to close"),
        Spec("L_long_tgt0.50", make_threshold_signal(combo, 0.45, long_only=True),
             0.50, 0.25, entry_from=dtime(11, 0), notes="long side only"),
        Spec("K_otm1_tgt0.50", make_threshold_signal(combo, 0.45), 0.50, 0.25,
             entry_from=dtime(11, 0), strike_offset=1, notes="one strike OTM"),
        Spec("S_thr0.75_tgt0.50", make_threshold_signal(combo, 0.75), 0.50, 0.25,
             entry_from=dtime(11, 0), notes="DEV-negative control"),
    ]


def row(name, m, t):
    if m.get("trades", 0) == 0:
        return f"{name:24}{'NO TRADES':>12}"
    return (f"{name:24}{m['trades']:>6}{m['win_rate']:>7.1f}{m['net']:>12,.0f}"
            f"{m['expectancy']:>9,.0f}{str(m['profit_factor']):>7}{m['max_dd']:>10,.0f}"
            f"{m['ret_on_deployed']:>8.2f}%{m['trades_per_day']:>9.2f}{t:>7.2f}")


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    by_day = index_grid(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV {len(dev)} sessions | VAL {len(val)} sessions {val[0]}..{val[-1]} "
          f"| HOLDOUT {len(hold)} FROZEN")

    hdr = (f"{'candidate':24}{'n':>6}{'win%':>7}{'net':>12}{'exp':>9}{'PF':>7}"
           f"{'maxDD':>10}{'ret/dep':>9}{'trd/day':>9}{'t':>7}")
    print("\n" + "=" * 110)
    print("DEV (for reference)")
    print("=" * 110)
    print(hdr)
    dev_res = {}
    for s in specs():
        tr = simulate(s, dev, daily, by_day, {})
        m = money_metrics(tr, dev)
        dev_res[s.name] = m
        print(row(s.name, m, tstat(tr)))

    print("\n" + "=" * 110)
    print("VALIDATION  2025-01-01 .. 2026-06-17   <-- the test")
    print("=" * 110)
    print(hdr)
    val_res = {}
    for s in specs():
        tr = simulate(s, val, daily, by_day, {})
        m = money_metrics(tr, val)
        val_res[s.name] = (m, tr)
        print(row(s.name, m, tstat(tr)))

    print("\n" + "=" * 110)
    print("PROMOTION GATE — positive on DEV *and* VAL")
    print("=" * 110)
    print(f"{'candidate':24}{'DEV net':>12}{'VAL net':>12}{'VAL exp':>10}"
          f"{'VAL PF':>8}{'VAL t':>8}  verdict")
    promoted = []
    for s in specs():
        dm = dev_res[s.name]
        vm, vtr = val_res[s.name]
        dnet = dm.get("net", 0.0)
        vnet = vm.get("net", 0.0)
        ok = dnet > 0 and vnet > 0 and vm.get("trades", 0) >= 25
        verdict = "PROMOTE" if ok else "reject"
        if ok:
            promoted.append(s.name)
        print(f"{s.name:24}{dnet:>12,.0f}{vnet:>12,.0f}"
              f"{vm.get('expectancy', 0):>10,.0f}{str(vm.get('profit_factor')):>8}"
              f"{tstat(vtr):>8.2f}  {verdict}")

    print(f"\nPROMOTED: {promoted or 'NONE'}")
    for n in promoted:
        m, _ = val_res[n]
        print(f"\n--- {n} on VALIDATION ---")
        for k in ("trades", "win_rate", "gross", "costs", "net", "expectancy",
                  "profit_factor", "max_dd", "max_losing_streak", "avg_win", "avg_loss",
                  "avg_capital", "max_capital", "ret_on_deployed", "trades_per_day",
                  "pct_sessions_traded", "avg_daily_ret_pct", "median_daily_ret_pct",
                  "pct_days_ge_1pct", "pct_days_ge_2pct", "pct_days_le_m1pct",
                  "profitable_days", "losing_days", "no_trade_days", "exit_reasons"):
            print(f"    {k:22s} {m.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
