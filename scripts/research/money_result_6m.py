"""
MONEY RESULT — the frozen five-bot system over the six-month holdout, at each
capital level, with the full daily distribution.

Sizing rule, fixed before the numbers were looked at: the account is split into
equal sleeves across the bots that can actually execute at that account size, each
sleeve takes whole lots only, and no more than 60% of the account is at risk in a
single position. A bot whose one-lot requirement exceeds its sleeve is reported
NOT EXECUTABLE rather than sized fractionally.

Capital at risk: premium outlaid for a bought option, (width - credit) x lot for a
defined-risk spread. Broker SPAN/exposure margin is UNKNOWN and is not estimated.
Daily percentages are against the account.
"""

import json
import os
import sys
from datetime import time as dtime
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution import bot_signals as BS
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.lab2 import (
    Spec2, daily_frame, option_index, session_panels, simulate2, split_sessions,
)
from scripts.research.holdout_6m import frozen
from scripts.research.weekly_premium_lab import WSpec, daily_with_rsi
from scripts.research.weekly_premium_lab import run as wrun

E = dtime
ACCOUNTS = (20000.0, 50000.0, 100000.0)


def daily_series(rows: List[Dict], sessions) -> pd.Series:
    """Index spans the holdout sessions AND every date a trade settles on, so a
    weekly leg that settles on a date absent from the 5-minute grid is not lost."""
    idx = sorted(set(sessions) | {r["sess"] for r in rows})
    s = pd.Series(0.0, index=pd.Index(idx))
    for r in rows:
        s.loc[r["sess"]] += r["net"]
    return s


def dist(per_day: pd.Series, account: float) -> Dict:
    rp = per_day / account * 100
    eq = per_day.cumsum()
    dd = abs(float((eq - eq.cummax()).min()))
    streak = mx = 0
    for x in per_day:
        if x < 0:
            streak += 1; mx = max(mx, streak)
        elif x > 0:
            streak = 0
    traded = per_day[per_day != 0]
    return {
        "net": round(float(per_day.sum()), 2),
        "return_pct": round(float(per_day.sum()) / account * 100, 2),
        "max_dd": round(dd, 2), "max_dd_pct": round(dd / account * 100, 2),
        "max_losing_day_streak": int(mx),
        "sessions": int(len(per_day)),
        "traded_days": int(len(traded)),
        "profitable_days": int((per_day > 0).sum()),
        "losing_days": int((per_day < 0).sum()),
        "pct_days_profitable_all": round(float((per_day > 0).mean() * 100), 1),
        "pct_days_profitable_of_traded": round(
            float((traded > 0).mean() * 100), 1) if len(traded) else 0.0,
        "avg_daily_pct": round(float(rp.mean()), 4),
        "median_daily_pct": round(float(rp.median()), 4),
        "best_day": round(float(per_day.max()), 2),
        "worst_day": round(float(per_day.min()), 2),
        "pct_days_ge_0p25": round(float((rp >= 0.25).mean() * 100), 1),
        "pct_days_ge_0p5": round(float((rp >= 0.5).mean() * 100), 1),
        "pct_days_ge_1": round(float((rp >= 1).mean() * 100), 1),
        "pct_days_ge_2": round(float((rp >= 2).mean() * 100), 1),
        "pct_days_le_m0p5": round(float((rp <= -0.5).mean() * 100), 1),
        "pct_days_le_m1": round(float((rp <= -1).mean() * 100), 1),
        "pct_days_le_m2": round(float((rp <= -2).mean() * 100), 1),
    }


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))

    # ── per-bot trade rows and one-lot capital requirement ──
    bots: Dict[str, Dict] = {}
    for name, spec in (
        ("BOT6", Spec2("BOT6", "f", frozen("BOT6", daily), entry_from=E(9, 30),
                       entry_to=E(15, 0), flat_at=E(15, 10))),
        ("BOT7", Spec2("BOT7", "f", frozen("BOT7", daily), entry_from=E(10, 0),
                       entry_to=E(15, 0), flat_at=E(15, 10))),
        ("BOT8", Spec2("BOT8", "f", frozen("BOT8", daily), entry_from=E(9, 45),
                       entry_to=E(15, 0), flat_at=E(15, 10))),
    ):
        tr = simulate2(spec, hold, daily, panels, opts, skips={})
        bots[name] = {"rows": [{"sess": t.sess, "net": t.net} for t in tr],
                      "per_lot": max((t.capital for t in tr), default=0.0),
                      "n": len(tr), "kind": "long option"}

    d2 = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    hsess = sorted({d for d in store["TradDt"].unique() if hold[0] <= d <= hold[-1]})
    for name, ws in (("BOT1", WSpec("B1", "condor", 1.8, 4)),
                     ("BOT2", WSpec("B2", "vertical_auto", 1.3, 12))):
        tr = wrun(ws, hsess, d2, store, chains, expiries, {})
        bots[name] = {"rows": [{"sess": pd.Timestamp(t["expiry"]).date(), "net": t["net"]}
                               for t in tr],
                      "per_lot": max((t["max_risk"] for t in tr), default=0.0),
                      "n": len(tr), "kind": "defined-risk spread"}

    print("=" * 112)
    print(f"SIX-MONTH HOLDOUT MONEY RESULT   {hold[0]} .. {hold[-1]}   {len(hold)} sessions")
    print("=" * 112)
    print(f"\n{'bot':8}{'kind':22}{'trades':>8}{'one lot needs':>16}{'net/lot':>12}")
    print("-" * 112)
    for n, b in bots.items():
        net1 = sum(r["net"] for r in b["rows"])
        print(f"{n:8}{b['kind']:22}{b['n']:>8}{b['per_lot']:>16,.0f}{net1:>12,.0f}")

    out = {}
    for acc in ACCOUNTS:
        live = {n: b for n, b in bots.items() if b["n"] > 0}
        sleeve = acc / max(len(live), 1)
        alloc, notes = {}, []
        for n, b in live.items():
            lots = int(min(sleeve, acc * 0.60) // b["per_lot"]) if b["per_lot"] > 0 else 0
            if lots < 1:
                notes.append(f"{n}: NOT EXECUTABLE — one lot needs Rs {b['per_lot']:,.0f}, "
                             f"sleeve is Rs {sleeve:,.0f}")
            else:
                alloc[n] = lots
        combined = pd.Series(0.0, index=pd.Index(sorted(hold)))
        per_bot = {}
        for n, lots in alloc.items():
            s = daily_series([{"sess": r["sess"], "net": r["net"] * lots}
                              for r in bots[n]["rows"]], hold)
            per_bot[n] = dist(s, acc)
            combined = combined.add(s, fill_value=0.0)
        d = dist(combined, acc) if alloc else None

        # The equal-sleeve rule can leave a small account with nothing to run.
        # Report what a single bot taking the whole account would have done, so the
        # answer is not an artefact of the sizing rule.
        single = {}
        for n, b in live.items():
            lots = int((acc * 0.60) // b["per_lot"]) if b["per_lot"] > 0 else 0
            if lots < 1:
                single[n] = {"lots": 0, "note": f"one lot needs Rs {b['per_lot']:,.0f}"}
                continue
            s = daily_series([{"sess": r["sess"], "net": r["net"] * lots}
                              for r in bots[n]["rows"]], hold)
            single[n] = {"lots": lots, **dist(s, acc)}
        out[str(int(acc))] = {"allocation": alloc, "not_executable": notes,
                              "portfolio": d, "per_bot": per_bot,
                              "single_bot_whole_account": single}

        print("\n" + "=" * 112)
        print(f"ACCOUNT Rs {acc:,.0f}   sleeve Rs {sleeve:,.0f} per bot")
        print("=" * 112)
        for nt in notes:
            print(f"  {nt}")
        print(f"  allocation: {alloc if alloc else 'NOTHING EXECUTABLE under equal sleeves'}")
        print("  single bot taking the whole account (<=60% at risk):")
        for n, v in single.items():
            if v.get("lots", 0) < 1:
                print(f"    {n:6} NOT EXECUTABLE — {v['note']}")
            else:
                print(f"    {n:6} {v['lots']} lot(s)  net Rs {v['net']:>9,.0f}  "
                      f"return {v['return_pct']:>7.2f}%  maxDD {v['max_dd_pct']:>6.2f}%  "
                      f"profitable days {v['pct_days_profitable_all']}% (traded "
                      f"{v['pct_days_profitable_of_traded']}%)  >=1% {v['pct_days_ge_1']}%  "
                      f">=2% {v['pct_days_ge_2']}%")
        if not alloc:
            continue
        print(f"  NET P&L            Rs {d['net']:,.2f}")
        print(f"  RETURN             {d['return_pct']:.2f}%")
        print(f"  MAX DRAWDOWN       Rs {d['max_dd']:,.2f}  ({d['max_dd_pct']:.2f}%)")
        print(f"  PROFITABLE DAYS    {d['profitable_days']} of {d['sessions']} sessions "
              f"= {d['pct_days_profitable_all']}%   "
              f"(of {d['traded_days']} traded days: {d['pct_days_profitable_of_traded']}%)")
        print(f"  % DAYS >= +1%      {d['pct_days_ge_1']}%")
        print(f"  % DAYS >= +2%      {d['pct_days_ge_2']}%")
        print(f"  % DAYS <= -1%      {d['pct_days_le_m1']}%")
        print(f"  avg daily {d['avg_daily_pct']:.4f}%   median daily {d['median_daily_pct']:.4f}%")
        print(f"  best day Rs {d['best_day']:,.0f}   worst day Rs {d['worst_day']:,.0f}   "
              f"longest losing-day streak {d['max_losing_day_streak']}")
        print(f"  per bot: " + "  ".join(
            f"{n} Rs {v['net']:,.0f}" for n, v in per_bot.items()))

    with open("reports/money_result_6m.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nwrote reports/money_result_6m.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
