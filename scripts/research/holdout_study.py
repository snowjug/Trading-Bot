"""
HOLDOUT MEASUREMENT — 2026-06-18 .. 2026-09-18. Measured once, frozen.

Measures, on the same conservative execution model:
  * the five bots currently frozen on main (1, 2, 6, 7, 8)
  * the one continuation candidate that survived DEV and VAL
  * the weekly condor, the only structure with a positive multi-year net

Nothing is tuned here. Every rule was fixed before this window was opened.

EXECUTION MODEL, identical for every line: no historical bid/ask exists, so each
side pays max(1 tick, 0.30% of premium) of half-spread plus 2 ticks of slippage,
on top of IndianCostModel statutory charges. That is deliberately harsher than the
0.22% spread observed live on 2026-09-18.

CAPITAL. For a bought option, capital = premium actually outlaid. For a defined-risk
spread, capital at risk = (width - credit) x lot; the broker's SPAN/exposure margin
is NOT obtainable read-only and is reported as UNKNOWN rather than estimated.
"""

import json
import os
import sys
from datetime import date, time as dtime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution import bot_signals as BS
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.strategy_lab import (
    Ctx, Spec, daily_frame, index_grid, money_metrics, simulate, split_sessions, tstat,
)
from scripts.research.candidates_dev import combo, make_threshold_signal
from scripts.research.weekly_premium_lab import WSpec, daily_with_rsi, metrics as wmetrics, run as wrun

ACCOUNTS = (20000.0, 50000.0, 100000.0)


# ── the five frozen bots, driven through the same lab simulator ──
def frozen_bot_signal(which: str, hist: pd.DataFrame):
    """Wraps a frozen bot_signals function into the lab's Ctx interface."""
    def sig(c: Ctx) -> int:
        if which == "BOT6":
            d = BS.bot6_micro_momentum(c.spot, c.vix, hist, c.sess, c.t, c.sess_hi, c.sess_lo)
        elif which == "BOT7":
            d = BS.bot7_displacement(c.spot, c.vix, hist, c.sess, c.t, c.twap,
                                     c.sess_hi, c.sess_lo)
        elif which == "BOT8":
            d = BS.bot8_price_action(c.spot, c.vix, hist, c.sess, c.t,
                                     list(c.path), c.prev_high, c.prev_low)
        else:
            return 0
        return d.direction if d.action == "ENTER" else 0
    return sig


def capital_rows(trades) -> pd.DataFrame:
    return pd.DataFrame([{
        "sess": t.sess, "net": t.net, "capital": t.capital, "gross": t.gross,
        "costs": t.costs,
    } for t in trades])


def scenario_table(trades, name: str) -> List[Dict]:
    """Lots executable at each account size, given the per-trade premium outlay."""
    if not trades:
        return [{"account": a, "lots": 0, "note": "no trades"} for a in ACCOUNTS]
    df = capital_rows(trades)
    per_lot_cap = df["capital"].max()          # worst-case single-lot outlay
    out = []
    for acc in ACCOUNTS:
        # high risk appetite: allow up to 60% of the account in one position
        lots = int((acc * 0.60) // per_lot_cap) if per_lot_cap > 0 else 0
        if lots < 1:
            out.append({"account": acc, "lots": 0,
                        "note": f"NOT EXECUTABLE — one lot needs up to Rs {per_lot_cap:,.0f}"})
            continue
        net = float(df["net"].sum()) * lots
        eq = (df["net"] * lots).cumsum()
        dd = abs(float((eq - eq.cummax()).min()))
        out.append({"account": acc, "lots": lots,
                    "capital_per_trade": round(per_lot_cap * lots, 2),
                    "net": round(net, 2),
                    "return_pct": round(net / acc * 100, 2),
                    "max_dd": round(dd, 2),
                    "dd_pct": round(dd / acc * 100, 2)})
    return out


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    by_day = index_grid(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    print("=" * 128)
    print(f"HOLDOUT  {hold[0]} .. {hold[-1]}   {len(hold)} sessions   MEASURED ONCE")
    print("=" * 128)

    results: Dict[str, Any] = {}

    # ── intraday: frozen bots 6/7/8 + the surviving candidate ──
    intraday = [
        ("BOT6_frozen", Spec("BOT6_frozen", frozen_bot_signal("BOT6", daily), 1.2, 0.6,
                             trail_atr=0.6, trail_give_atr=0.35, entry_from=dtime(9, 30),
                             entry_to=dtime(15, 0), notes="as on main")),
        ("BOT7_frozen", Spec("BOT7_frozen", frozen_bot_signal("BOT7", daily), 1.2, 0.6,
                             trail_atr=0.7, trail_give_atr=0.4, entry_from=dtime(10, 0),
                             entry_to=dtime(15, 0), notes="as on main")),
        ("BOT8_frozen", Spec("BOT8_frozen", frozen_bot_signal("BOT8", daily), 1.0, 0.5,
                             entry_from=dtime(9, 45), entry_to=dtime(15, 0),
                             notes="as on main")),
        ("CAND_cont_thr060", Spec("CAND_cont_thr060", make_threshold_signal(combo, 0.60),
                                  0.50, 0.25, entry_from=dtime(11, 0),
                                  notes="survived DEV+VAL")),
    ]
    print(f"\n{'strategy':22}{'n':>5}{'win%':>7}{'gross':>10}{'costs':>9}{'net':>10}"
          f"{'exp':>8}{'PF':>7}{'maxDD':>9}{'avgCap':>9}{'ret/dep':>9}{'t':>7}")
    print("-" * 128)
    for name, spec in intraday:
        tr = simulate(spec, hold, daily, by_day, {})
        m = money_metrics(tr, hold)
        results[name] = {"metrics": m, "scenarios": scenario_table(tr, name),
                         "type": "LONG_OPTION"}
        if m.get("trades", 0) == 0:
            print(f"{name:22}{0:>5}{'—':>7}{0:>10}{0:>9}{0:>10}{'—':>8}{'—':>7}"
                  f"{0:>9}{0:>9}{'—':>9}{'—':>7}")
            continue
        print(f"{name:22}{m['trades']:>5}{m['win_rate']:>7.1f}{m['gross']:>10,.0f}"
              f"{m['costs']:>9,.0f}{m['net']:>10,.0f}{m['expectancy']:>8,.0f}"
              f"{str(m['profit_factor']):>7}{m['max_dd']:>9,.0f}{m['avg_capital']:>9,.0f}"
              f"{m['ret_on_deployed']:>8.2f}%{tstat(tr):>7.2f}")

    # ── weekly: frozen bots 1/2 + the condor ──
    d2 = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    hsess = sorted({d for d in store["TradDt"].unique() if hold[0] <= d <= hold[-1]})
    wspecs = [
        ("BOT1_frozen_condor", WSpec("BOT1", "condor", 1.8, 4, notes="as on main")),
        ("BOT2_frozen_vertical", WSpec("BOT2", "vertical_auto", 1.3, 12, notes="as on main")),
        ("CAND_condor_2.2sd", WSpec("C22", "condor", 2.2, 4, notes="further shorts")),
    ]
    print(f"\n{'weekly strategy':22}{'n':>5}{'win%':>7}{'gross':>10}{'costs':>9}{'net':>10}"
          f"{'exp':>8}{'breach':>8}{'maxDD':>9}{'avgRisk':>10}{'t':>7}")
    print("-" * 128)
    for name, ws in wspecs:
        sk = {}
        tr = wrun(ws, hsess, d2, store, chains, expiries, sk)
        m = wmetrics(tr, len(hsess))
        br = 0
        for t in tr:
            sc = [l for l in t["legs"] if l["role"] == "short_call"]
            sp = [l for l in t["legs"] if l["role"] == "short_put"]
            if (sc and t["settle"] > sc[0]["strike"]) or (sp and t["settle"] < sp[0]["strike"]):
                br += 1
        results[name] = {"metrics": m, "type": "SPREAD", "breaches": br,
                         "skips": sk, "trades": tr}
        if m.get("trades", 0) == 0:
            print(f"{name:22}{0:>5}  no trades   skips={dict(sorted(sk.items(), key=lambda x:-x[1])[:3])}")
            continue
        print(f"{name:22}{m['trades']:>5}{m['win_rate']:>7.1f}{m['gross']:>10,.0f}"
              f"{m['costs']:>9,.0f}{m['net']:>10,.0f}{m['expectancy']:>8,.0f}"
              f"{br:>4}/{m['trades']:<3}{m['max_dd']:>9,.0f}{m['avg_max_risk']:>10,.0f}"
              f"{m['tstat']:>7.2f}")

    print("\n" + "=" * 128)
    print("CAPITAL SCENARIOS (long-option strategies; 60% of account may sit in one position)")
    print("=" * 128)
    for name, _ in intraday:
        r = results[name]
        if r["metrics"].get("trades", 0) == 0:
            continue
        print(f"\n  {name}")
        for s in r["scenarios"]:
            if s.get("lots", 0) == 0:
                print(f"    Rs {s['account']:>8,.0f}: {s.get('note')}")
            else:
                print(f"    Rs {s['account']:>8,.0f}: {s['lots']} lot(s)  net Rs {s['net']:>9,.0f}"
                      f"  return {s['return_pct']:>7.2f}%  maxDD Rs {s['max_dd']:>8,.0f}"
                      f" ({s['dd_pct']:.2f}%)")

    Path("reports").mkdir(exist_ok=True)
    Path("reports/holdout_study.json").write_text(
        json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "trades"}
                    for k, v in results.items()}, indent=2, default=str), encoding="utf-8")
    print("\nwrote reports/holdout_study.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
