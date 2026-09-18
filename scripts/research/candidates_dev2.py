"""
Candidate search round 2 — DEVELOPMENT SET ONLY.

Round 1 produced one unambiguous, monotone result: target width dominates.

    tgt 0.20 / stp 0.20  ->  -Rs 48,401
    tgt 0.25 / stp 0.15  ->  -Rs 26,834
    tgt 0.25 / stp 0.20  ->  -Rs 12,579
    tgt 0.35 / stp 0.20  ->  +Rs      655
    tgt 0.50 / stp 0.25  ->  +Rs 39,619

That is option convexity doing exactly what it should: a bought option carries
theta and two sides of cost, so a narrow target cannot pay for the position. The
second signal was that selectivity helps — a 0.75 threshold produced the best
per-trade expectancy (+Rs 227) and profit factor (1.259) on 66 trades.

Round 2 therefore pushes both axes and adds the one structural lever untested so
far: STRIKE. An out-of-the-money option costs less capital and carries more
convexity per rupee, which is the natural instrument for a wide-target rule.
"""

import os
import sys
from datetime import time as dtime

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.strategy_lab import (
    Ctx, Spec, daily_frame, index_grid, line, money_metrics, simulate,
    split_sessions, tstat,
)
from scripts.research.candidates_dev import combo, make_threshold_signal


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    by_day = index_grid(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV sessions: {len(dev)}  {dev[0]} .. {dev[-1]}")

    C = []
    # ── axis 1: how far does the target-width effect run? ──
    for tg in (0.70, 1.00, 1.50):
        C.append(Spec(f"W_tgt{tg:.2f}_stp0.25", make_threshold_signal(combo, 0.45),
                      tg, 0.25, entry_from=dtime(11, 0), notes="width sweep"))
    # ── axis 2: no target at all — pure convexity, stop only, run to the close ──
    C.append(Spec("W_no_target_stp0.25", make_threshold_signal(combo, 0.45),
                  99.0, 0.25, entry_from=dtime(11, 0), notes="stop only, ride to EOD"))
    C.append(Spec("W_no_target_stp0.35", make_threshold_signal(combo, 0.45),
                  99.0, 0.35, entry_from=dtime(11, 0), notes="stop only, wider stop"))
    # ── axis 3: width x selectivity ──
    for thr in (0.60, 0.75):
        C.append(Spec(f"S_thr{thr:.2f}_tgt0.50", make_threshold_signal(combo, thr),
                      0.50, 0.25, entry_from=dtime(11, 0), notes="width + selectivity"))
        C.append(Spec(f"S_thr{thr:.2f}_tgt1.00", make_threshold_signal(combo, thr),
                      1.00, 0.25, entry_from=dtime(11, 0), notes="width + selectivity"))
    # ── axis 4: STRIKE — OTM is cheaper and more convex per rupee ──
    for off in (1, 2):
        C.append(Spec(f"K_otm{off}_tgt0.50", make_threshold_signal(combo, 0.45),
                      0.50, 0.25, entry_from=dtime(11, 0), strike_offset=off,
                      notes=f"ATM+{off} OTM"))
        C.append(Spec(f"K_otm{off}_tgt1.00", make_threshold_signal(combo, 0.45),
                      1.00, 0.25, entry_from=dtime(11, 0), strike_offset=off,
                      notes=f"ATM+{off} OTM, wide"))
    # ── axis 5: earlier entry now that the target is wide (more time to travel) ──
    C.append(Spec("T_0945_tgt0.50", make_threshold_signal(combo, 0.45), 0.50, 0.25,
                  entry_from=dtime(9, 45), notes="early entry, wide target"))
    C.append(Spec("T_1015_tgt1.00", make_threshold_signal(combo, 0.45), 1.00, 0.25,
                  entry_from=dtime(10, 15), notes="early entry, very wide"))
    # ── axis 6: long-only at the winning geometry ──
    C.append(Spec("L_long_tgt0.50", make_threshold_signal(combo, 0.45, long_only=True),
                  0.50, 0.25, entry_from=dtime(11, 0), notes="long side only"))
    # ── axis 7: wide target plus a trail, so a big move is not fully given back ──
    C.append(Spec("R_trail_wide", make_threshold_signal(combo, 0.45), 1.50, 0.25,
                  trail_atr=0.45, trail_give_atr=0.25, entry_from=dtime(11, 0),
                  notes="wide target + generous trail"))

    print(f"candidate budget round 2: {len(C)}")
    print("=" * 128)
    res = {}
    for spec in C:
        tr = simulate(spec, dev, daily, by_day, {})
        m = money_metrics(tr, dev)
        res[spec.name] = (spec, tr, m)
        print(line(spec.name, m, tstat(tr)))

    print("\n" + "=" * 128)
    print("RANKED BY NET (DEV round 2)")
    print("=" * 128)
    rows = [(n, r[2]) for n, r in res.items() if r[2].get("trades", 0) > 0]
    rows.sort(key=lambda x: -x[1]["net"])
    print(f"{'candidate':24}{'n':>6}{'win%':>7}{'net':>12}{'exp':>9}{'PF':>7}"
          f"{'maxDD':>10}{'ret/dep':>9}{'avgCap':>9}{'trd/day':>9}{'t':>7}")
    for n, m in rows:
        print(f"{n:24}{m['trades']:>6}{m['win_rate']:>7.1f}{m['net']:>12,.0f}"
              f"{m['expectancy']:>9,.0f}{str(m['profit_factor']):>7}{m['max_dd']:>10,.0f}"
              f"{m['ret_on_deployed']:>8.2f}%{m['avg_capital']:>9,.0f}"
              f"{m['trades_per_day']:>9.2f}{tstat(res[n][1]):>7.2f}")

    for n, m in rows[:3]:
        print(f"\n--- {n} ({res[n][0].notes}) ---")
        for k in ("trades", "win_rate", "gross", "costs", "net", "expectancy",
                  "profit_factor", "max_dd", "max_losing_streak", "avg_win", "avg_loss",
                  "avg_capital", "max_capital", "ret_on_deployed", "trades_per_day",
                  "pct_sessions_traded", "avg_daily_ret_pct", "pct_days_ge_1pct",
                  "pct_days_ge_2pct", "exit_reasons"):
            print(f"    {k:22s} {m.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
