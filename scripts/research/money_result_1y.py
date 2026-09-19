"""
ONE-YEAR HOLDOUT MONEY RESULT — 2025-09-18 .. 2026-09-18.

Two things are measured here and they must not be confused:

  1. THE FROZEN FIVE-BOT SYSTEM as it stands on `main`, at each capital level.
     This is the answer to "what would the money have been", and it is the
     headline of `reports/FINAL_ONE_YEAR_MONEY_STUDY.md`.

  2. THE BEST CANDIDATES FROM THIS RUN'S SEARCH, measured on the holdout once,
     for DISCLOSURE ONLY. None of them passed the validation gate in
     `scripts/research/overnight_validate.py`, so none is promoted, and the
     holdout number cannot be used to promote them after the fact. It is reported
     because the brief requires every result preserved, and because a reader is
     entitled to know whether the rejection was right.

SIZING, fixed before the numbers were seen (identical rule to the 6-month study):
the account splits into equal sleeves across the bots that can execute at that
size, whole lots only, no more than 60% of the account at risk in one position. A
bot whose one-lot requirement exceeds its sleeve is reported NOT EXECUTABLE, never
sized fractionally.

CAPITAL AT RISK: premium outlaid for a bought option; (width - credit) x lot for a
defined-risk spread; 12% of spot per naked short leg as a conservative stand-in
for SPAN+exposure, flagged wherever it applies.
"""

import json
import os
import sys
from datetime import date, time as dtime
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.lab2 import Spec2, daily_frame, option_index, session_panels, simulate2
from src.research.overnight import (
    HOLDOUT_END, HOLDOUT_START, Leg, OSpec, load_data, metrics, simulate_overnight, tstat,
)
from scripts.research.holdout_6m import frozen
from scripts.research.weekly_premium_lab import WSpec, daily_with_rsi
from scripts.research.weekly_premium_lab import run as wrun

E = dtime
ACCOUNTS = (20000.0, 50000.0, 100000.0)


def daily_series(rows: List[Dict], sessions) -> pd.Series:
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
        "sessions": int(len(per_day)), "traded_days": int(len(traded)),
        "profitable_days": int((per_day > 0).sum()),
        "losing_days": int((per_day < 0).sum()),
        "pct_days_profitable_all": round(float((per_day > 0).mean() * 100), 1),
        "pct_days_profitable_of_traded": round(float((traded > 0).mean() * 100), 1)
                                         if len(traded) else 0.0,
        "avg_daily_pct": round(float(rp.mean()), 4),
        "median_daily_pct": round(float(rp.median()), 4),
        "best_day": round(float(per_day.max()), 2),
        "worst_day": round(float(per_day.min()), 2),
        "pct_days_ge_0p5": round(float((rp >= 0.5).mean() * 100), 1),
        "pct_days_ge_1": round(float((rp >= 1).mean() * 100), 1),
        "pct_days_ge_2": round(float((rp >= 2).mean() * 100), 1),
        "pct_days_le_m0p5": round(float((rp <= -0.5).mean() * 100), 1),
        "pct_days_le_m1": round(float((rp <= -1).mean() * 100), 1),
        "pct_days_le_m2": round(float((rp <= -2).mean() * 100), 1),
    }


def one_year(sessions: List[date]) -> List[date]:
    return [s for s in sessions if HOLDOUT_START <= s <= HOLDOUT_END]


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    hold = one_year(available_option_days(grid))
    assert hold and hold[0] >= HOLDOUT_START and hold[-1] <= HOLDOUT_END

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
                      "n": len(tr), "kind": "long option",
                      "nets": [t.net for t in tr]}

    d2 = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    hsess = sorted({d for d in store["TradDt"].unique()
                    if HOLDOUT_START <= d <= HOLDOUT_END})
    for name, ws in (("BOT1", WSpec("B1", "condor", 1.8, 4)),
                     ("BOT2", WSpec("B2", "vertical_auto", 1.3, 12))):
        tr = wrun(ws, hsess, d2, store, chains, expiries, {})
        bots[name] = {"rows": [{"sess": pd.Timestamp(t["expiry"]).date(), "net": t["net"]}
                               for t in tr],
                      "per_lot": max((t["max_risk"] for t in tr), default=0.0),
                      "n": len(tr), "kind": "defined-risk spread",
                      "nets": [t["net"] for t in tr]}

    print("=" * 112)
    print(f"ONE-YEAR HOLDOUT   {hold[0]} .. {hold[-1]}   {len(hold)} sessions "
          f"(weekly legs settle on {len(hsess)} bhavcopy sessions)")
    print("=" * 112)
    print(f"\n{'bot':8}{'kind':22}{'trades':>8}{'one lot needs':>16}{'net/lot':>12}"
          f"{'win%':>8}{'t':>8}")
    print("-" * 112)
    for n, b in bots.items():
        net1 = sum(r["net"] for r in b["rows"])
        x = np.array(b["nets"], float)
        wr = (x > 0).mean() * 100 if len(x) else 0.0
        print(f"{n:8}{b['kind']:22}{b['n']:>8}{b['per_lot']:>16,.0f}{net1:>12,.0f}"
              f"{wr:>8.1f}{tstat(x) if len(x) > 1 else float('nan'):>8.2f}")

    out: Dict[str, Dict] = {"window": {"start": str(hold[0]), "end": str(hold[-1]),
                                       "sessions": len(hold)}, "accounts": {}}
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

        single = {}
        for n, b in live.items():
            lots = int((acc * 0.60) // b["per_lot"]) if b["per_lot"] > 0 else 0
            if lots < 1:
                single[n] = {"lots": 0, "note": f"one lot needs Rs {b['per_lot']:,.0f}"}
                continue
            s = daily_series([{"sess": r["sess"], "net": r["net"] * lots}
                              for r in bots[n]["rows"]], hold)
            single[n] = {"lots": lots, **dist(s, acc)}
        out["accounts"][str(int(acc))] = {
            "allocation": alloc, "not_executable": notes, "portfolio": d,
            "per_bot": per_bot, "single_bot_whole_account": single}

        print("\n" + "=" * 112)
        print(f"ACCOUNT Rs {acc:,.0f}   sleeve Rs {sleeve:,.0f} per bot")
        print("=" * 112)
        for nt in notes:
            print(f"  {nt}")
        print(f"  allocation: {alloc if alloc else 'NOTHING EXECUTABLE under equal sleeves'}")
        if d:
            print(f"  NET P&L         Rs {d['net']:,.2f}")
            print(f"  RETURN          {d['return_pct']:.2f}%")
            print(f"  MAX DRAWDOWN    Rs {d['max_dd']:,.2f}  ({d['max_dd_pct']:.2f}%)")
            print(f"  PROFITABLE DAYS {d['profitable_days']}/{d['sessions']} = "
                  f"{d['pct_days_profitable_all']}%  (of traded: "
                  f"{d['pct_days_profitable_of_traded']}%)")
            print(f"  %DAYS >=+0.5% {d['pct_days_ge_0p5']}   >=+1% {d['pct_days_ge_1']}   "
                  f">=+2% {d['pct_days_ge_2']}   <=-1% {d['pct_days_le_m1']}")
            print(f"  avg daily {d['avg_daily_pct']:.4f}%  median {d['median_daily_pct']:.4f}%"
                  f"  best Rs {d['best_day']:,.0f}  worst Rs {d['worst_day']:,.0f}")
            print("  per bot: " + "  ".join(f"{n} Rs {v['net']:,.0f}"
                                            for n, v in per_bot.items()))
        print("  single bot taking the whole account (<=60% at risk):")
        for n, v in single.items():
            if v.get("lots", 0) < 1:
                print(f"    {n:6} NOT EXECUTABLE — {v['note']}")
            else:
                print(f"    {n:6} {v['lots']} lot(s)  net Rs {v['net']:>10,.0f}  "
                      f"return {v['return_pct']:>8.2f}%  maxDD {v['max_dd_pct']:>6.2f}%  "
                      f"prof days {v['pct_days_profitable_all']}%  "
                      f">=1% {v['pct_days_ge_1']}%  >=2% {v['pct_days_ge_2']}%")

    # ── DISCLOSURE ONLY: this run's rejected candidates, on the holdout, once ──
    print("\n" + "=" * 112)
    print("DISCLOSURE — candidates REJECTED at validation, measured on the holdout once.")
    print("None is promoted. These numbers may not be used to promote them.")
    print("=" * 112)
    od = load_data()
    ohold = [s for s in od.sessions if HOLDOUT_START <= s <= HOLDOUT_END]
    F_PCR = lambda r: r["pcr_oi"] > 1.1                    # noqa: E731
    F_PCT = lambda r: r["pcr_oi_pct"] > 70                 # noqa: E731
    cands = [
        OSpec("ODC1_LC-1_PCR", "long_call", [Leg("CE", +1, -1)], filter_fn=F_PCR),
        OSpec("ODC2_LC+0_PCR", "long_call", [Leg("CE", +1, 0)], filter_fn=F_PCR),
        OSpec("ODC3_PS+2w400_PCR", "put_spread",
              [Leg("PE", -1, 2), Leg("PE", +1, -6)], filter_fn=F_PCR),
        OSpec("ODC4_SYNTH_PCR", "synthetic",
              [Leg("CE", +1, 0), Leg("PE", -1, 0)], filter_fn=F_PCR),
        OSpec("ODC5_naked+2_PCR", "naked_put", [Leg("PE", -1, 2)], filter_fn=F_PCR),
        OSpec("ODC6_LC-1_PCRpct", "long_call", [Leg("CE", +1, -1)], filter_fn=F_PCT),
        OSpec("REF_LC-1", "long_call", [Leg("CE", +1, -1)]),
        OSpec("REF_PS+2w400", "put_spread", [Leg("PE", -1, 2), Leg("PE", +1, -6)]),
        OSpec("REF_naked+2", "naked_put", [Leg("PE", -1, 2)]),
        OSpec("CTRL_CS_short", "control", [Leg("CE", -1, 0), Leg("CE", +1, 6)]),
    ]
    print(f"{'candidate':20}{'n':>5}{'exp pts':>10}{'t':>7}{'win%':>7}{'net Rs':>11}"
          f"{'maxDD':>10}{'cap':>10}{'PF':>7}")
    disc = []
    for spec in cands:
        nights = simulate_overnight(spec, ohold, od)
        m = metrics(nights, len(ohold))
        if m.get("trades", 0) == 0:
            print(f"{spec.name:20}{'NO TRADES':>15}"); continue
        print(f"{spec.name:20}{m['trades']:>5}{m['expectancy_pts']:>10.2f}{m['tstat']:>7.2f}"
              f"{m['win_rate']:>7.1f}{m['net']:>11,.0f}{m['max_dd']:>10,.0f}"
              f"{m['max_capital_used']:>10,.0f}{str(m['profit_factor']):>7}")
        disc.append({"name": spec.name, **{k: v for k, v in m.items() if k != "exit_reasons"}})
    out["disclosure_rejected_candidates"] = disc

    os.makedirs("reports", exist_ok=True)
    with open("reports/money_result_1y.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nwrote reports/money_result_1y.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
