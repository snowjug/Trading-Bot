"""
Candidate search — DEVELOPMENT SET ONLY (2020-09-01 .. 2024-12-31).

Finite budget. Every candidate is a stated rule set, tested once here. Survivors go
to validation; nothing is measured on the holdout at this stage.

The rules come from what `edge_discovery` / `edge_tails` actually measured on this
same DEV data:
  * continuation, not reversion
  * the long side is materially stronger than the short (63.8% vs 51.4% in the tails)
  * signal strengthens through the session (57% at 09:45 -> 66% at 14:00)
  * MFE (+0.29 ATR) is ~3.4x the mean EOD outcome (+0.085 ATR), so holding to the
    close discards most of the favourable excursion — take profit instead
"""

import os
import sys
from datetime import date, time as dtime

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.strategy_lab import (
    Ctx, Spec, daily_frame, index_grid, line, money_metrics, simulate,
    split_sessions, tstat,
)


# ───────────────────────── signal primitives ─────────────────────────

def s_from_open(c: Ctx) -> float:
    return c.z(c.spot - c.open_px)


def s_pos_in_sess(c: Ctx) -> float:
    rng = c.sess_hi - c.sess_lo
    return (c.spot - c.sess_lo) / rng * 2 - 1 if rng > 1e-9 else 0.0


def s_from_twap(c: Ctx) -> float:
    return c.z(c.spot - c.twap)


def s_mom12(c: Ctx) -> float:
    j = max(c.i - 12, 0)
    return c.z(c.spot - float(c.path[j]))


def s_or_break(c: Ctx) -> float:
    if not np.isfinite(c.or_hi) or not np.isfinite(c.or_lo):
        return 0.0
    if c.spot > c.or_hi:
        return c.z(c.spot - c.or_hi)
    if c.spot < c.or_lo:
        return c.z(c.spot - c.or_lo)
    return 0.0


def combo(c: Ctx) -> float:
    """Equal-weight blend of the continuation features. Nothing is fitted."""
    return float(np.mean([s_from_open(c), s_pos_in_sess(c) * 0.5,
                          s_from_twap(c), s_mom12(c), s_or_break(c)]))


def make_threshold_signal(fn, thr: float, long_only: bool = False,
                          vix_lo: float = 0.0, vix_hi: float = 99.0):
    def sig(c: Ctx) -> int:
        if not (vix_lo <= c.vix < vix_hi):
            return 0
        v = fn(c)
        if v >= thr:
            return 1
        if v <= -thr and not long_only:
            return -1
        return 0
    return sig


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    by_day = index_grid(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print(f"DEV sessions     : {len(dev)}  {dev[0]} .. {dev[-1]}")
    print(f"VAL sessions     : {len(val)}  {val[0]} .. {val[-1]}   (not used here)")
    print(f"HOLDOUT sessions : {len(hold)} {hold[0]} .. {hold[-1]}  (FROZEN)")

    C = []
    # ── family A: continuation with profit taking, entry-time variants ──
    for nm, frm in (("A1_cont_1100", dtime(11, 0)), ("A2_cont_1300", dtime(13, 0))):
        C.append(Spec(nm, make_threshold_signal(combo, 0.45), 0.25, 0.20,
                      entry_from=frm, notes="combo>=0.45 both sides"))
    # ── family B: long-only, per the measured asymmetry ──
    C.append(Spec("B1_long_only_1100", make_threshold_signal(combo, 0.45, long_only=True),
                  0.25, 0.20, entry_from=dtime(11, 0), notes="long side only"))
    C.append(Spec("B2_long_only_1300", make_threshold_signal(combo, 0.45, long_only=True),
                  0.25, 0.20, entry_from=dtime(13, 0), notes="long side only, late"))
    # ── family C: target / stop geometry on the best entry ──
    for nm, tg, st in (("C1_tgt35_stp20", 0.35, 0.20), ("C2_tgt25_stp15", 0.25, 0.15),
                       ("C3_tgt50_stp25", 0.50, 0.25), ("C4_tgt20_stp20", 0.20, 0.20)):
        C.append(Spec(nm, make_threshold_signal(combo, 0.45), tg, st,
                      entry_from=dtime(11, 0), notes="geometry sweep"))
    # ── family D: trailing instead of a hard target ──
    C.append(Spec("D1_trail", make_threshold_signal(combo, 0.45), 0.60, 0.20,
                  trail_atr=0.20, trail_give_atr=0.12, entry_from=dtime(11, 0),
                  notes="wide target + trail"))
    # ── family E: single-feature baselines, to see if the blend earns its keep ──
    C.append(Spec("E1_from_open_only", make_threshold_signal(s_from_open, 0.60),
                  0.25, 0.20, entry_from=dtime(11, 0), notes="single feature"))
    C.append(Spec("E2_or_break_only", make_threshold_signal(s_or_break, 0.25),
                  0.25, 0.20, entry_from=dtime(11, 0), notes="single feature"))
    # ── family F: VIX-conditioned, from the regime table ──
    C.append(Spec("F1_vix_12_17", make_threshold_signal(combo, 0.45, vix_lo=12, vix_hi=17),
                  0.25, 0.20, entry_from=dtime(11, 0), notes="mid-vol only"))
    # ── family G: selectivity — how much does a harder threshold help? ──
    C.append(Spec("G1_thr_0p75", make_threshold_signal(combo, 0.75), 0.25, 0.20,
                  entry_from=dtime(11, 0), notes="stricter entry"))
    C.append(Spec("G2_thr_0p30", make_threshold_signal(combo, 0.30), 0.25, 0.20,
                  entry_from=dtime(11, 0), notes="looser entry"))
    # ── family H: allow a second trade per day ──
    C.append(Spec("H1_two_per_day", make_threshold_signal(combo, 0.45), 0.25, 0.20,
                  entry_from=dtime(11, 0), max_trades_per_day=2, notes="2 trades/day"))

    print(f"\ncandidate budget: {len(C)}")
    print("=" * 128)
    print("DEV RESULTS")
    print("=" * 128)
    results = {}
    for spec in C:
        skips = {}
        tr = simulate(spec, dev, daily, by_day, skips)
        m = money_metrics(tr, dev)
        results[spec.name] = (spec, tr, m)
        print(line(spec.name, m, tstat(tr)))

    print("\n" + "=" * 128)
    print("RANKED BY NET (DEV)")
    print("=" * 128)
    rows = [(n, r[2]) for n, r in results.items() if r[2].get("trades", 0) > 0]
    rows.sort(key=lambda x: -x[1]["net"])
    print(f"{'candidate':24}{'n':>6}{'win%':>7}{'net':>12}{'exp':>9}{'PF':>7}"
          f"{'maxDD':>10}{'ret/dep':>9}{'trd/day':>9}{'t':>7}")
    for n, m in rows:
        t = tstat(results[n][1])
        print(f"{n:24}{m['trades']:>6}{m['win_rate']:>7.1f}{m['net']:>12,.0f}"
              f"{m['expectancy']:>9,.0f}{str(m['profit_factor']):>7}{m['max_dd']:>10,.0f}"
              f"{m['ret_on_deployed']:>8.2f}%{m['trades_per_day']:>9.2f}{t:>7.2f}")

    best = rows[0][0] if rows else None
    if best:
        spec, tr, m = results[best]
        print(f"\nBEST ON DEV: {best}  ({spec.notes})")
        for k in ("trades", "win_rate", "gross", "costs", "net", "expectancy",
                  "profit_factor", "max_dd", "max_losing_streak", "avg_win", "avg_loss",
                  "capital_deployed", "avg_capital", "max_capital", "ret_on_deployed",
                  "trades_per_day", "pct_sessions_traded", "avg_daily_ret_pct",
                  "pct_days_ge_1pct", "pct_days_ge_2pct", "exit_reasons"):
            print(f"    {k:22s} {m.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
