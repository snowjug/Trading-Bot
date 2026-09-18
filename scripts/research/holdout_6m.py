"""
SIX-MONTH HOLDOUT — 2026-03-18 .. 2026-09-18. Measured once, frozen.

Nothing in this window was used to choose anything. The candidate search closed
before it was opened, and it closed with no promotion: no candidate cleared the
gate of "positive on development and on validation, with a usable sample, still
positive at twice the cost".

What is measured here:
  * the five bots currently frozen on main (1, 2, 6, 7, 8), because the money
    question is asked about them;
  * the best development candidates from each family, so the holdout figure for a
    rejected idea is on the record rather than asserted.

Capital scenarios use whole lots only. For a bought option, capital is the premium
actually outlaid. For a defined-risk spread, capital at risk is
(width - credit) x lot. Broker SPAN/exposure margin is NOT obtainable read-only
and is reported UNKNOWN rather than estimated. Daily percentages are taken against
the account, never against notional.
"""

import json
import os
import pickle
import sys
from datetime import time as dtime
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution import bot_signals as BS
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.concepts import donchian, orb
from src.research.dte0_condor import ZSpec, run_dte0, z_metrics
from src.research.lab2 import (
    Ctx2, Setup, Spec2, daily_frame, metrics2, option_index, session_panels,
    simulate2, split_sessions,
)
from scripts.research.dev_sweep2 import wide_filter
from scripts.research.weekly_premium_lab import WSpec, daily_with_rsi
from scripts.research.weekly_premium_lab import metrics as wmetrics
from scripts.research.weekly_premium_lab import run as wrun

ACCOUNTS = (20000.0, 50000.0, 100000.0)
E = dtime
A = dict(entry_from=E(9, 30), entry_to=E(14, 30), flat_at=E(15, 15))


def frozen(which: str, hist: pd.DataFrame):
    """The bots on main, wrapped into lab2's level interface with their own geometry."""
    def sig(c: Ctx2):
        sess_hi, sess_lo = c.sess_hi, c.sess_lo
        if which == "BOT6":
            d = BS.bot6_micro_momentum(c.spot, c.vix, hist, c.sess, c.t, sess_hi, sess_lo)
            tgt, stp = 1.2, 0.6
        elif which == "BOT7":
            d = BS.bot7_displacement(c.spot, c.vix, hist, c.sess, c.t, c.twap, sess_hi, sess_lo)
            tgt, stp = 1.2, 0.6
        elif which == "BOT8":
            d = BS.bot8_price_action(c.spot, c.vix, hist, c.sess, c.t, list(c.path),
                                     c.prev_high, c.prev_low)
            tgt, stp = 1.0, 0.5
        else:
            return None
        if d.action != "ENTER" or d.direction == 0:
            return None
        k = d.direction
        return Setup(direction=k, stop=c.spot - k * stp * c.atr,
                     target=c.spot + k * tgt * c.atr, tag=which)
    return sig


def scenarios(per_trade_capital: float, nets: pd.Series, label: str) -> List[Dict]:
    out = []
    for acc in ACCOUNTS:
        lots = int((acc * 0.60) // per_trade_capital) if per_trade_capital > 0 else 0
        if lots < 1:
            out.append({"account": acc, "lots": 0,
                        "note": f"NOT EXECUTABLE AT Rs {acc:,.0f} — one lot needs "
                                f"Rs {per_trade_capital:,.0f} (>60% of account)"})
            continue
        n = nets * lots
        eq = n.cumsum()
        dd = abs(float((eq - eq.cummax()).min()))
        out.append({"account": acc, "lots": lots,
                    "capital_per_trade": round(per_trade_capital * lots, 2),
                    "net": round(float(n.sum()), 2),
                    "return_pct": round(float(n.sum()) / acc * 100, 2),
                    "max_dd": round(dd, 2),
                    "dd_pct": round(dd / acc * 100, 2)})
    return out


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    dte = pickle.load(open("data/derived/session_dte.pkl", "rb"))
    print("=" * 128)
    print(f"SIX-MONTH HOLDOUT  {hold[0]} .. {hold[-1]}   {len(hold)} sessions   MEASURED ONCE")
    print("=" * 128)

    results: Dict[str, dict] = {}

    # ── intraday: frozen bots 6/7/8 plus the best rejected candidates ──
    intraday = [
        ("BOT6_frozen", Spec2("BOT6", "frozen", frozen("BOT6", daily),
                              entry_from=E(9, 30), entry_to=E(15, 0), flat_at=E(15, 10))),
        ("BOT7_frozen", Spec2("BOT7", "frozen", frozen("BOT7", daily),
                              entry_from=E(10, 0), entry_to=E(15, 0), flat_at=E(15, 10))),
        ("BOT8_frozen", Spec2("BOT8", "frozen", frozen("BOT8", daily),
                              entry_from=E(9, 45), entry_to=E(15, 0), flat_at=E(15, 10))),
        ("CAND_orb0.25_rr1.5", Spec2("C_orb", "orb", wide_filter(orb("15", 1.5), 0.25), **A)),
        ("CAND_orb0.35_rr2.5", Spec2("C_orb2", "orb", wide_filter(orb("15", 2.5), 0.35), **A)),
        ("CAND_donch_or0.35", Spec2("C_don", "trend", wide_filter(donchian(20, 1.5), 0.35), **A)),
    ]
    print(f"\n{'strategy':22}{'n':>5}{'win%':>7}{'gross':>10}{'costs':>9}{'net':>10}"
          f"{'exp':>8}{'PF':>7}{'maxDD':>9}{'avgCap':>9}{'ret/dep':>9}{'t':>7}")
    print("-" * 128)
    for name, spec in intraday:
        tr = simulate2(spec, hold, daily, panels, opts, skips={})
        m = metrics2(tr, hold)
        results[name] = {"type": "LONG_OPTION", "metrics": m}
        if not m.get("trades"):
            print(f"{name:22}{0:>5}{'—':>7}{0:>10}{0:>9}{0:>10}{'—':>8}{'—':>7}{0:>9}{0:>9}{'—':>9}{'—':>7}")
            results[name]["scenarios"] = [{"account": a, "lots": 0, "note": "no trades"} for a in ACCOUNTS]
            continue
        df = pd.DataFrame([t.__dict__ for t in tr])
        per = float(df["capital"].max())
        nets = df.groupby("sess")["net"].sum()
        results[name]["scenarios"] = scenarios(per, nets, name)
        print(f"{name:22}{m['trades']:>5}{m['win_rate']:>7.1f}{m['gross']:>10,.0f}"
              f"{m['costs']:>9,.0f}{m['net']:>10,.0f}{m['expectancy']:>8,.0f}"
              f"{str(m['profit_factor']):>7}{m['max_dd']:>9,.0f}{m['avg_capital']:>9,.0f}"
              f"{m['ret_on_deployed']:>8.2f}%{str(m['tstat']):>7}")

    # ── weekly: frozen bots 1 and 2 ──
    d2 = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    hsess = sorted({d for d in store["TradDt"].unique() if hold[0] <= d <= hold[-1]})
    print(f"\n{'weekly strategy':22}{'n':>5}{'win%':>7}{'gross':>10}{'costs':>9}{'net':>10}"
          f"{'exp':>8}{'breach':>9}{'maxDD':>9}{'avgRisk':>10}{'t':>7}")
    print("-" * 128)
    for name, ws in (("BOT1_frozen_condor", WSpec("B1", "condor", 1.8, 4)),
                     ("BOT2_frozen_vertical", WSpec("B2", "vertical_auto", 1.3, 12))):
        tr = wrun(ws, hsess, d2, store, chains, expiries, {})
        m = wmetrics(tr, len(hsess))
        br = 0
        for t in tr:
            sc = [l for l in t["legs"] if l["role"] == "short_call"]
            sp = [l for l in t["legs"] if l["role"] == "short_put"]
            if (sc and t["settle"] > sc[0]["strike"]) or (sp and t["settle"] < sp[0]["strike"]):
                br += 1
        results[name] = {"type": "SPREAD", "metrics": m, "breaches": br}
        if not m.get("trades"):
            print(f"{name:22}  no trades"); continue
        df = pd.DataFrame(tr)
        results[name]["scenarios"] = scenarios(float(df["max_risk"].max()),
                                               df.groupby("sess")["net"].sum(), name)
        print(f"{name:22}{m['trades']:>5}{m['win_rate']:>7.1f}{m['gross']:>10,.0f}"
              f"{m['costs']:>9,.0f}{m['net']:>10,.0f}{m['expectancy']:>8,.0f}"
              f"{br:>4}/{m['trades']:<4}{m['max_dd']:>9,.0f}{m['avg_max_risk']:>10,.0f}"
              f"{m['tstat']:>7.2f}")

    # ── zero-DTE condor, the corrected version ──
    ic = dict(zip(daily["sess"], daily["close"].astype(float)))
    h0 = [s for s in hold if dte.get(s) == 0]
    settle = {s: chains.settlement(s, ic) for s in h0}
    tr = run_dte0(ZSpec("Z", 0.35, 3), h0, daily, panels, opts, settle, skips={})
    m = z_metrics(tr, h0)
    results["CAND_dte0_condor"] = {"type": "SPREAD", "metrics": m}
    print(f"\n{'CAND_dte0_condor':22}{m.get('trades', 0):>5}"
          f"{m.get('win_rate', 0):>7}{m.get('gross', 0):>10,.0f}{m.get('costs', 0):>9,.0f}"
          f"{m.get('net', 0):>10,.0f}{m.get('expectancy', 0):>8,.0f}"
          f"{m.get('breach_pct', 0):>8}%{m.get('max_dd', 0):>9,.0f}"
          f"{m.get('avg_max_risk', 0):>10,.0f}{str(m.get('tstat')):>7}   "
          f"({len(h0)} expiry sessions)")
    if tr:
        df = pd.DataFrame([{k: v for k, v in t.__dict__.items() if k != "legs"} for t in tr])
        results["CAND_dte0_condor"]["scenarios"] = scenarios(
            float(df["max_risk"].max()), df.groupby("sess")["net"].sum(), "dte0")

    print("\n" + "=" * 128)
    print("CAPITAL SCENARIOS — whole lots only, max 60% of the account at risk in one position")
    print("=" * 128)
    for name, r in results.items():
        if not r.get("metrics", {}).get("trades"):
            continue
        print(f"\n  {name}")
        for s in r.get("scenarios", []):
            if s.get("lots", 0) == 0:
                print(f"    Rs {s['account']:>8,.0f}: {s.get('note')}")
            else:
                print(f"    Rs {s['account']:>8,.0f}: {s['lots']} lot(s)  "
                      f"net Rs {s['net']:>9,.0f}  return {s['return_pct']:>7.2f}%  "
                      f"maxDD Rs {s['max_dd']:>8,.0f} ({s['dd_pct']:.2f}%)")

    Path("reports").mkdir(exist_ok=True)
    Path("reports/holdout_6m.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("\nwrote reports/holdout_6m.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
