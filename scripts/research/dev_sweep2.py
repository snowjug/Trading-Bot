"""
DEV SWEEP ROUND 2 — DEVELOPMENT SET ONLY. Validation and holdout untouched.

Round 1 produced exactly one non-trivial result. The opening-range breakout is a
large net loser taken unconditionally (996 trades, -Rs 119,344), and a winner when
it is restricted to sessions whose opening range is already wide (68 trades,
+Rs 47,588, Rs 700 per trade, PF 1.44). Nothing else in 31 concepts came close:
25 of 31 were negative before statutory costs, which means the signal was absent
rather than merely expensive.

So round 2 has one job: find out whether "only trade when the session is already
moving" is a real conditioning effect or a small-sample accident. It sweeps the
threshold, the reward/risk, the strike, the entry window, and applies the same
filter to the other two gross-positive families. It also reports, for every
survivor, how much of the profit is the single best trade — the diagnostic that
killed the previous study's winner.
"""

import os
import sys
from datetime import time as dtime
from typing import List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.concepts import donchian, gap_go, orb
from src.research.lab2 import (
    Ctx2, Setup, Spec2, daily_frame, metrics2, option_index, session_panels,
    simulate2, split_sessions, tstat,
)

E = dtime
A = dict(entry_from=E(9, 30), entry_to=E(14, 30), flat_at=E(15, 15))


def wide_filter(inner, min_or_pct: float):
    """Only act when the 09:15-09:29 range is at least this wide, in % of spot."""
    def sig(c: Ctx2):
        if not np.isfinite(c.or_hi) or not np.isfinite(c.or_lo):
            return None
        if (c.or_hi - c.or_lo) / c.spot * 100 < min_or_pct:
            return None
        return inner(c)
    return sig


def prior_vol_filter(inner, min_ratio: float):
    """Prior session's range against its own 20-day average. Known before the open."""
    def sig(c: Ctx2):
        if not np.isfinite(c.range20) or c.range20 <= 0:
            return None
        if c.prev_range_pct / c.range20 < min_ratio:
            return None
        return inner(c)
    return sig


def concentration(trades) -> str:
    if len(trades) < 3:
        return "n/a"
    n = np.array([t.net for t in trades], float)
    s = np.sort(n)[::-1]
    tot = n.sum()
    if tot <= 0:
        return "net<=0"
    return (f"top1 {s[0]/tot*100:>5.1f}%  top2 {(s[0]+s[1])/tot*100:>5.1f}%  "
            f"w/o top2 {tot-s[0]-s[1]:>9,.0f}  median {np.median(n):>8,.0f}")


def build():
    C = []
    # ── axis 1: how wide must the opening range be? ──
    for th in (0.20, 0.25, 0.30, 0.35, 0.45, 0.55):
        C.append(Spec2(f"W_or{th:.2f}_rr1.5", "orb", wide_filter(orb("15", 1.5), th), **A,
                       notes=f"OR >= {th}% of spot"))
    # ── axis 2: reward/risk at a wide range ──
    for rr in (1.0, 1.5, 2.0, 2.5, 3.0):
        C.append(Spec2(f"R_rr{rr:.1f}_or0.35", "orb", wide_filter(orb("15", rr), 0.35), **A,
                       notes=f"1:{rr} at OR>=0.35%"))
    # ── axis 3: strike. OTM is cheaper and more convex; ITM carries more delta ──
    for off, lbl in ((-1, "itm1"), (0, "atm"), (1, "otm1"), (2, "otm2")):
        C.append(Spec2(f"K_{lbl}_or0.35", "orb", wide_filter(orb("15", 1.5, off=off), 0.35),
                       **A, notes=f"strike {lbl}"))
    # ── axis 4: does the prior session's volatility work as well as the OR width? ──
    for r in (1.0, 1.2, 1.5):
        C.append(Spec2(f"P_prior{r:.1f}_rr1.5", "orb", prior_vol_filter(orb("15", 1.5), r), **A,
                       notes=f"prior range >= {r}x its 20d average"))
    # ── axis 5: both filters together ──
    C.append(Spec2("B_or0.35_prior1.2", "orb",
                   prior_vol_filter(wide_filter(orb("15", 1.5), 0.35), 1.2), **A,
                   notes="wide OR and an already-volatile prior session"))
    # ── axis 6: entry window. Does the edge need the morning? ──
    C.append(Spec2("T_0930_1130", "orb", wide_filter(orb("15", 1.5), 0.35),
                   entry_from=E(9, 30), entry_to=E(11, 30), flat_at=E(15, 15),
                   notes="morning only"))
    C.append(Spec2("T_1130_1430", "orb", wide_filter(orb("15", 1.5), 0.35),
                   entry_from=E(11, 30), entry_to=E(14, 30), flat_at=E(15, 15),
                   notes="afternoon only"))
    # ── axis 7: trend agreement on top of the width filter ──
    C.append(Spec2("S_stack_or0.35", "orb",
                   wide_filter(orb("15", 1.5, need_stack=True), 0.35), **A,
                   notes="wide OR + daily EMA stack"))
    C.append(Spec2("S_anchor_or0.35", "orb",
                   wide_filter(orb("15", 1.5, need_anchor=True), 0.35), **A,
                   notes="wide OR + right side of volume anchor"))
    # ── axis 8: the 30-minute range, which is a wider net by construction ──
    for th in (0.35, 0.45):
        C.append(Spec2(f"O30_or{th:.2f}", "orb", wide_filter(orb("30", 1.5), th),
                       entry_from=E(9, 45), entry_to=E(14, 30), flat_at=E(15, 15),
                       notes=f"30-min range, OR>={th}%"))
    # ── axis 9: the same filter on the other two gross-positive families ──
    C.append(Spec2("F_gap_or0.35", "gap", wide_filter(gap_go(1.5), 0.35), **A,
                   notes="gap continuation, wide OR only"))
    C.append(Spec2("F_donch_or0.35", "trend", wide_filter(donchian(20, 1.5), 0.35), **A,
                   notes="channel break, wide OR only"))
    C.append(Spec2("F_gap_prior1.2", "gap", prior_vol_filter(gap_go(1.5), 1.2), **A,
                   notes="gap continuation, volatile prior session"))
    # ── axis 10: more than one attempt on a qualifying day ──
    C.append(Spec2("N_two_per_day", "orb", wide_filter(orb("15", 1.5), 0.35),
                   max_trades_per_day=2, **A, notes="two attempts allowed"))
    return C


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV {len(dev)} sessions {dev[0]} .. {dev[-1]}   (VAL and HOLDOUT untouched)")

    C = build()
    print(f"candidates round 2: {len(C)}")
    print("=" * 134)
    print(f"{'candidate':22}{'n':>6}{'win%':>7}{'gross':>11}{'costs':>10}{'net':>11}"
          f"{'exp':>8}{'PF':>7}{'maxDD':>10}{'trd/d':>7}{'t':>7}  notes")
    print("-" * 134)
    res = {}
    for spec in C:
        tr = simulate2(spec, dev, daily, panels, opts, skips={})
        m = metrics2(tr, dev)
        res[spec.name] = (spec, tr, m)
        if m.get("trades", 0) == 0:
            print(f"{spec.name:22}{'NO TRADES':>10}   {spec.notes}")
            continue
        print(f"{spec.name:22}{m['trades']:>6}{m['win_rate']:>7.1f}{m['gross']:>11,.0f}"
              f"{m['costs']:>10,.0f}{m['net']:>11,.0f}{m['expectancy']:>8,.0f}"
              f"{str(m['profit_factor']):>7}{m['max_dd']:>10,.0f}"
              f"{m['trades_per_day']:>7.2f}{m['tstat']:>7.2f}  {spec.notes}")

    ok = [(n, r) for n, r in res.items() if r[2].get("trades", 0) > 0 and r[2]["net"] > 0]
    ok.sort(key=lambda x: -x[1][2]["net"])
    print("\n" + "=" * 134)
    print(f"NET-POSITIVE ON DEV: {len(ok)} of {len(C)}   — with concentration")
    print("=" * 134)
    for n, (spec, tr, m) in ok:
        print(f"  {n:22} net {m['net']:>9,.0f}  exp {m['expectancy']:>6,.0f}  "
              f"PF {str(m['profit_factor']):>6}  t {m['tstat']:>6.2f}  n {m['trades']:>4}  "
              f"win {m['win_rate']:>5.1f}%")
        print(f"      {concentration(tr)}")
    pd.DataFrame([{"name": n, **r[2]} for n, r in res.items()]).to_csv(
        "reports/dev_sweep2_results.csv", index=False)
    print("\nwrote reports/dev_sweep2_results.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
