"""
DEV SWEEP — 31 distinct strategy concepts, DEVELOPMENT SET ONLY (2020-09-01 .. 2024-09-17).

The validation set and the six-month holdout are not touched here. Every concept is
a stated rule set from `src.research.concepts`; nothing is tuned inside this script.

Gross is printed beside net on purpose. A concept that is gross-negative has no
signal. A concept that is gross-positive and net-negative has a signal that costs
more than it is worth, which is a different problem with a different remedy.
"""

import os
import sys
from datetime import time as dtime

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.concepts import (
    anchor_pullback, anchor_revert, compression_break, donchian, gap_fade, gap_go,
    liquidity_sweep, mim, orb, orb_fade, orb_retest, pd_break, pd_fade,
    range_expansion, rsi_extreme_revert, session_extreme_fade, structure_break,
    trend_pullback, vix_band_orb,
)
from src.research.lab2 import (
    Spec2, daily_frame, metrics2, option_index, session_panels, simulate2,
    split_sessions, tstat,
)

E = dtime


def concepts():
    """31 materially different concepts. Entry windows are part of the concept."""
    C = []
    A = dict(entry_from=E(9, 30), entry_to=E(14, 30), flat_at=E(15, 15))
    A30 = dict(entry_from=E(9, 45), entry_to=E(14, 30), flat_at=E(15, 15))

    # ── A. opening range breakout ──
    C.append(Spec2("C01_ORB15_rr1.5", "orb", orb("15", 1.5), **A, notes="break OR15, stop other side"))
    C.append(Spec2("C02_ORB15_rr2.0", "orb", orb("15", 2.0), **A, notes="same, 1:2"))
    C.append(Spec2("C03_ORB15_rr3.0", "orb", orb("15", 3.0), **A, notes="same, 1:3"))
    C.append(Spec2("C04_ORB30_rr1.5", "orb", orb("30", 1.5), **A30, notes="30-min range"))
    C.append(Spec2("C05_ORB15_stack", "orb", orb("15", 1.5, need_stack=True), **A,
                   notes="daily EMA stack must agree"))
    C.append(Spec2("C06_ORB15_anchor", "orb", orb("15", 1.5, need_anchor=True), **A,
                   notes="must be the right side of the option-volume anchor"))
    C.append(Spec2("C07_ORB15_wide", "orb", orb("15", 1.5, min_range_pct=0.35), **A,
                   notes="wide opening range only"))
    C.append(Spec2("C08_ORB15_narrow", "orb", orb("15", 2.0, max_range_pct=0.30), **A,
                   notes="narrow opening range only"))
    C.append(Spec2("C09_ORB_retest", "orb", orb_retest("15", 2.0), **A, notes="break then retest"))
    C.append(Spec2("C10_ORB_fade", "revert", orb_fade("15", 1.5), **A, notes="failed breakout"))

    # ── B. previous-day levels ──
    C.append(Spec2("C11_PD_break", "level", pd_break(1.5), **A, notes="prev day high/low break"))
    C.append(Spec2("C12_PD_fade", "revert", pd_fade(1.5), **A, notes="prev day high/low fade"))

    # ── C. gap ──
    C.append(Spec2("C13_gap_go", "gap", gap_go(1.5), **A, notes="gap 0.3-3% continuation"))
    C.append(Spec2("C14_gap_fade", "gap", gap_fade(1.5), **A, notes="gap fade"))

    # ── D. session anchor ──
    C.append(Spec2("C15_anchor_pb_vol", "anchor", anchor_pullback(2.0, "vwap_opt"), **A,
                   notes="pullback to option-volume-weighted anchor"))
    C.append(Spec2("C16_anchor_pb_twap", "anchor", anchor_pullback(2.0, "twap"), **A,
                   notes="pullback to session TWAP"))
    C.append(Spec2("C17_anchor_revert", "revert", anchor_revert(1.0), **A,
                   notes="fade extension from anchor"))

    # ── E. market intraday momentum (Gao/Han/Li/Zhou 2018) ──
    M = dict(entry_from=E(15, 0), entry_to=E(15, 0), flat_at=E(15, 20))
    C.append(Spec2("C18_MIM_first30", "mim", mim(), **M, notes="first 30m sign -> last 30m"))
    C.append(Spec2("C19_MIM_wide", "mim", mim(stop_atr=0.8, tgt_atr=1.5), **M, notes="looser stop"))
    C.append(Spec2("C20_MIM_hivol", "mim", mim(hi_vol_only=True), **M,
                   notes="paper: effect stronger on volatile days"))
    C.append(Spec2("C21_MIM_penult", "mim", mim(use_penultimate=True), **M,
                   notes="14:30-15:00 return instead"))
    C.append(Spec2("C22_MIM_minret", "mim", mim(min_abs_ret=0.15), **M,
                   notes="require a decisive first half-hour"))

    # ── F. trend / channel ──
    C.append(Spec2("C23_donchian20", "trend", donchian(20, 1.5), **A, notes="20-bar channel break"))
    C.append(Spec2("C24_trend_pullback", "trend", trend_pullback(2.0), **A,
                   notes="daily trend + intraday pullback"))

    # ── G. volatility ──
    C.append(Spec2("C25_compression", "vol", compression_break(2.0),
                   entry_from=E(10, 15), entry_to=E(14, 30), flat_at=E(15, 15),
                   notes="quiet first hour then break"))
    C.append(Spec2("C26_range_expansion", "vol", range_expansion(1.5), **A,
                   notes="bar far larger than recent average"))
    C.append(Spec2("C27_vix_band_orb", "vol", vix_band_orb(1.5, 10, 18), **A,
                   notes="ORB only in a mid-VIX band"))

    # ── H. mean reversion ──
    C.append(Spec2("C28_zfade", "revert", session_extreme_fade(1.0), **A, notes="fade 1.6 sigma"))
    C.append(Spec2("C29_rsi_revert", "revert", rsi_extreme_revert(1.0), **A,
                   notes="daily RSI extreme, intraday turn"))

    # ── I. liquidity / structure ──
    C.append(Spec2("C30_sweep", "structure", liquidity_sweep(2.0), **A,
                   notes="range extreme swept then reclaimed"))
    C.append(Spec2("C31_structure_break", "structure", structure_break(2.0, 3), **A,
                   notes="confirmed swing break, k=3 each side"))
    return C


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV      {len(dev):>5} sessions  {dev[0]} .. {dev[-1]}")
    print(f"VAL      {len(val):>5} sessions  {val[0]} .. {val[-1]}   (not used here)")
    print(f"HOLDOUT  {len(hold):>5} sessions  {hold[0]} .. {hold[-1]}  FROZEN")

    C = concepts()
    print(f"\nconcepts: {len(C)}")
    print("=" * 132)
    print(f"{'concept':22}{'n':>6}{'win%':>7}{'gross':>11}{'costs':>10}{'net':>11}"
          f"{'exp':>8}{'PF':>7}{'maxDD':>10}{'trd/d':>7}{'t':>7}  family")
    print("-" * 132)
    rows = []
    for spec in C:
        tr = simulate2(spec, dev, daily, panels, opts, skips={})
        m = metrics2(tr, dev)
        if m.get("trades", 0) == 0:
            print(f"{spec.name:22}{'NO TRADES':>10}   {spec.family}")
            rows.append({"name": spec.name, "family": spec.family, "trades": 0, "net": 0.0})
            continue
        print(f"{spec.name:22}{m['trades']:>6}{m['win_rate']:>7.1f}{m['gross']:>11,.0f}"
              f"{m['costs']:>10,.0f}{m['net']:>11,.0f}{m['expectancy']:>8,.0f}"
              f"{str(m['profit_factor']):>7}{m['max_dd']:>10,.0f}"
              f"{m['trades_per_day']:>7.2f}{m['tstat']:>7.2f}  {spec.family}")
        rows.append({"name": spec.name, "family": spec.family, **m})

    df = pd.DataFrame(rows)
    df.to_csv("reports/dev_sweep_results.csv", index=False)
    pos = df[(df.get("trades", 0) > 0) & (df["net"] > 0)].sort_values("net", ascending=False)
    print("\n" + "=" * 132)
    print(f"GROSS-POSITIVE CONCEPTS (signal exists before costs): "
          f"{int((df.get('gross', pd.Series(dtype=float)) > 0).sum())} of {len(df)}")
    print(f"NET-POSITIVE CONCEPTS: {len(pos)} of {len(df)}")
    print("=" * 132)
    for _, r in pos.iterrows():
        print(f"  {r['name']:22} net {r['net']:>10,.0f}  exp {r['expectancy']:>7,.0f}  "
              f"PF {str(r['profit_factor']):>6}  t {r['tstat']:>6.2f}  n {int(r['trades']):>5}  "
              f"win {r['win_rate']:>5.1f}%  {r['family']}")
    print("\nwrote reports/dev_sweep_results.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
