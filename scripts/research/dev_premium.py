"""
INTRADAY SHORT-PREMIUM DEVELOPMENT — DEV SET ONLY (2020-09-01 .. 2024-09-17).

The case for this family is a measurement, not a hunch: NIFTY's intraday range has
compressed (share of sessions with a 0.35% opening range fell 10.1% in 2022 to
~2% from 2023 on), which is the wrong environment for buying premium and the right
one for selling it with capped risk.

Axes swept, all on DEV: short-strike distance, wing width, entry time, stop
multiple, and structure (four-leg condor against a one-sided vertical). Nothing
here sees validation or the holdout.
"""

import os
import sys
from datetime import time as dtime

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.intraday_premium import IPSpec, ip_metrics, run_intraday_premium
from src.research.lab2 import daily_frame, option_index, session_panels, split_sessions

E = dtime


def build():
    C = []
    # ── axis 1: how far out are the shorts? ──
    for sa in (0.25, 0.35, 0.45, 0.60):
        C.append(IPSpec(f"P_sa{sa:.2f}_w3", "condor", sa, 3, notes=f"shorts {sa} ATR"))
    # ── axis 2: wing width, which sets max risk ──
    for w in (2, 4, 6):
        C.append(IPSpec(f"P_sa0.35_w{w}", "condor", 0.35, w, notes=f"{w}-step wings"))
    # ── axis 3: entry time ──
    for t, lbl in ((E(9, 30), "0930"), (E(10, 15), "1015"), (E(11, 0), "1100"), (E(12, 0), "1200")):
        C.append(IPSpec(f"T_{lbl}", "condor", 0.35, 3, entry_t=t, notes=f"enter {lbl}"))
    # ── axis 4: stop discipline on the spread mark ──
    for sm in (1.8, 2.5, 4.0, 99.0):
        C.append(IPSpec(f"S_stop{sm:g}", "condor", 0.35, 3, stop_mult=sm,
                        notes=f"stop at {sm}x credit" if sm < 99 else "no stop, hold to close"))
    # ── axis 5: one-sided verticals ──
    C.append(IPSpec("L_put_spread", "vertical_put", 0.35, 3, notes="put credit spread only"))
    C.append(IPSpec("L_call_spread", "vertical_call", 0.35, 3, notes="call credit spread only"))
    # ── axis 6: a VIX ceiling, since a vol spike is the structural enemy ──
    for mv in (16.0, 20.0):
        C.append(IPSpec(f"V_vix{mv:g}", "condor", 0.35, 3, max_vix=mv, notes=f"VIX < {mv}"))
    return C


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV {len(dev)} sessions {dev[0]} .. {dev[-1]}   (VAL and HOLDOUT untouched)")

    C = build()
    print(f"intraday short-premium candidates: {len(C)}")
    print("=" * 134)
    print(f"{'candidate':20}{'n':>5}{'win%':>7}{'gross':>10}{'costs':>9}{'net':>10}"
          f"{'exp':>8}{'PF':>7}{'maxDD':>9}{'brch%':>7}{'credit':>8}{'risk':>9}{'t':>7}  notes")
    print("-" * 134)
    res = {}
    for spec in C:
        sk = {}
        tr = run_intraday_premium(spec, dev, daily, panels, opts, skips=sk)
        m = ip_metrics(tr, dev)
        res[spec.name] = (spec, tr, m, sk)
        if m.get("trades", 0) == 0:
            print(f"{spec.name:20}{'NO TRADES':>10}  skips={dict(sorted(sk.items(), key=lambda x:-x[1])[:3])}")
            continue
        print(f"{spec.name:20}{m['trades']:>5}{m['win_rate']:>7.1f}{m['gross']:>10,.0f}"
              f"{m['costs']:>9,.0f}{m['net']:>10,.0f}{m['expectancy']:>8,.0f}"
              f"{str(m['profit_factor']):>7}{m['max_dd']:>9,.0f}{m['breach_pct']:>7.1f}"
              f"{m['avg_credit_pts']:>8.2f}{m['avg_max_risk']:>9,.0f}"
              f"{str(m['tstat']):>7}  {spec.notes}")

    ok = [(n, r) for n, r in res.items() if r[2].get("trades", 0) > 0 and r[2]["net"] > 0]
    ok.sort(key=lambda x: -(x[1][2]["tstat"] or 0))
    print("\n" + "=" * 134)
    print(f"NET-POSITIVE ON DEV: {len(ok)} of {len(C)}")
    print("=" * 134)
    for n, (spec, tr, m, sk) in ok:
        import numpy as np
        a = np.array([t.net for t in tr], float)
        s = np.sort(a)[::-1]
        tot = a.sum()
        print(f"  {n:20} t {str(m['tstat']):>6}  net {m['net']:>9,.0f}  exp {m['expectancy']:>6,.0f}  "
              f"PF {str(m['profit_factor']):>6}  n {m['trades']:>4}  win {m['win_rate']:>5.1f}%  "
              f"breach {m['breach_pct']:>4.1f}%")
        print(f"      worst {m['worst_trade']:>9,.0f}  maxRisk {m['max_risk_worst']:>9,.0f}  "
              f"w/o top2 {tot - s[0] - s[1]:>9,.0f}  median {np.median(a):>8,.0f}  "
              f"streak {m['max_losing_streak']}")
    pd.DataFrame([{"name": n, **r[2]} for n, r in res.items()]).to_csv(
        "reports/dev_premium_results.csv", index=False)
    print("\nwrote reports/dev_premium_results.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
