"""
FUTURES OVERNIGHT STUDY — does the measured overnight drift survive in the tradable
delta-1 instrument?

This is the question the previous cycle closed on. Its final paragraph named futures
as the instrument that would convert a measured ~15 point/night index drift into money,
and recorded that no futures data existed. The data existed; it was dropped at intake.

Everything here is priced on authentic NSE bhavcopy prints for one contract at a time.
Roll sessions are excluded and counted. Costs use the statutory futures schedule with
the pre/post October-2024 STT change applied by trade date.

Reproduce:
    python scripts/research/futures_overnight_study.py
"""

import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.futures_panel import (
    basis_frame, futures_roundtrip_cost_points, load_futures, lot_calendar,
    overnight_pairs, tstat,
)

SPLITS = [("DEV", date(2019, 1, 1), date(2024, 9, 17)),
          ("VAL", date(2024, 9, 18), date(2025, 9, 17)),
          ("HOLDOUT", date(2025, 9, 18), date(2026, 9, 18))]


def main() -> int:
    d = load_futures()
    print(f"FUTIDX rows {len(d):,}  sessions {d['TradDt'].nunique():,}  "
          f"{d['TradDt'].min().date()} -> {d['TradDt'].max().date()}  "
          f"eras {d['LayoutEra'].value_counts().to_dict()}")

    rows = []
    for sym in ("NIFTY", "BANKNIFTY"):
        ok = overnight_pairs(d, sym)
        ok["yr"] = ok["TradDt"].dt.year
        print("\n" + "=" * 98)
        print(f"{sym} near-month futures — {len(ok):,} same-contract pairs "
              f"({ok.attrs['rolls_excluded']} roll sessions excluded)")
        print("=" * 98)
        print(f"  OVERNIGHT close->next open : {ok['on_pct'].mean():+.4f}% = "
              f"{ok['on_pts'].mean():+7.2f} pts  t={tstat(ok['on_pct']):+6.2f}  "
              f"win={(ok['on_pts'] > 0).mean() * 100:5.1f}%  median {ok['on_pts'].median():+7.2f}")
        print(f"  INTRADAY  open->close      : {ok['id_pct'].mean():+.4f}% = "
              f"{ok['id_pts'].mean():+7.2f} pts  t={tstat(ok['id_pct']):+6.2f}  "
              f"win={(ok['id_pts'] > 0).mean() * 100:5.1f}%")

        px, lot = float(ok["ClsPric"].mean()), float(ok["lot"].median())
        cost = futures_roundtrip_cost_points(px, lot, when=date(2026, 1, 1))
        cost_old = futures_roundtrip_cost_points(px, lot, when=date(2023, 1, 1))
        print(f"  round-trip cost at price {px:,.0f} lot {lot:.0f}: "
              f"{cost:.2f} pts (post-Oct-2024 STT) / {cost_old:.2f} pts (before)")
        print(f"  NET overnight expectancy   : {ok['on_pts'].mean() - cost:+7.2f} pts")

        print(f"\n  {'year':6}{'n':>5}{'ON %':>10}{'ON pts':>9}{'t':>7}{'win%':>7}"
              f"{'ID %':>10}{'t':>7}")
        for y, g in ok.groupby("yr"):
            print(f"  {y:<6}{len(g):>5}{g['on_pct'].mean():>10.4f}{g['on_pts'].mean():>9.2f}"
                  f"{tstat(g['on_pct']):>7.2f}{(g['on_pts'] > 0).mean() * 100:>7.1f}"
                  f"{g['id_pct'].mean():>10.4f}{tstat(g['id_pct']):>7.2f}")

        for lbl, a, b in SPLITS:
            s = ok[(ok["TradDt"].dt.date >= a) & (ok["TradDt"].dt.date <= b)]
            if len(s) < 5:
                continue
            print(f"  {lbl:8} n={len(s):>4} ON={s['on_pct'].mean():+.4f}% "
                  f"({s['on_pts'].mean():+7.2f} pts) t={tstat(s['on_pct']):+6.2f} "
                  f"win={(s['on_pts'] > 0).mean() * 100:5.1f}%   "
                  f"ID={s['id_pct'].mean():+.4f}% t={tstat(s['id_pct']):+6.2f}")
            rows.append({"symbol": sym, "split": lbl, "n": len(s),
                         "on_pct": round(float(s["on_pct"].mean()), 4),
                         "on_pts": round(float(s["on_pts"].mean()), 2),
                         "on_t": round(tstat(s["on_pct"]), 2),
                         "on_win": round(float((s["on_pts"] > 0).mean() * 100), 1),
                         "id_pct": round(float(s["id_pct"].mean()), 4),
                         "id_t": round(tstat(s["id_pct"]), 2),
                         "cost_pts": round(cost, 2)})

        srt = np.sort(ok["on_pts"].to_numpy(float))
        print(f"\n  CONCENTRATION: total {srt.sum():+,.0f} pts over {len(srt):,} nights")
        for k in (1, 5, 10, 20):
            print(f"    minus best {k:>2}: {srt[:-k].sum():+,.0f} pts")
        print(f"    p1 {np.percentile(srt, 1):+,.0f}   p99 {np.percentile(srt, 99):+,.0f}")

        for m in (1.0, 1.5, 2.0):
            c = futures_roundtrip_cost_points(px, lot, date(2026, 1, 1), mult=m)
            print(f"    cost x{m}: net {ok['on_pts'].mean() - c:+7.2f} pts")

    print("\n" + "=" * 98)
    print("BASIS DECOMPOSITION — why the index gap is not the futures gap (NIFTY)")
    print("=" * 98)
    b = basis_frame(d, "NIFTY")
    print(f"  n={len(b):,}")
    print(f"  INDEX   close -> next open : {b['idx_on_pts'].mean():+7.2f} pts "
          f"({b['idx_on_pts'].mean() / b['idx_close'].mean() * 100:+.4f}%)")
    print(f"  FUTURES close -> next open : {b['on_pts'].mean():+7.2f} pts "
          f"({b['on_pts'].mean() / b['ClsPric'].mean() * 100:+.4f}%)")
    short = b["on_pts"].mean() - b["idx_on_pts"].mean()
    carry = b["idx_close"].mean() * 0.06 / 365
    print(f"  shortfall                  : {short:+7.2f} pts")
    print(f"  genuine carry decay (6%/yr): {-carry:+7.2f} pts")
    print(f"  unexplained by carry       : {short + carry:+7.2f} pts "
          f"= {abs(short + carry) / abs(b['idx_on_pts'].mean()) * 100:.0f}% of the index gap")
    print(f"  basis at close {b['basis_close'].mean():+7.2f}  at open "
          f"{b['basis_open'].mean():+7.2f}")
    b["bucket"] = pd.cut(b["dte"], [-1, 3, 7, 14, 21, 30, 60])
    print("\n  basis at close by days-to-expiry (clean carry validates the measurement):")
    print(b.groupby("bucket", observed=True)["basis_close"]
          .agg(["mean", "median", "count"]).round(2).to_string())

    print("\n" + "=" * 98)
    print("AUTHENTIC LOT-SIZE CALENDAR, derived from exchange turnover")
    print("=" * 98)
    cal_all = []
    for sym in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"):
        c = lot_calendar(d, sym)
        if c.empty:
            continue
        c["symbol"] = sym
        cal_all.append(c)
        changes = c[c["lot"].diff().fillna(0) != 0]
        print(f"  {sym:12} {len(c)} months, lot values {sorted(c['lot'].unique())}")
        print(f"    changes at: " + ", ".join(f"{r['month']}->{r['lot']:.0f}"
                                              for _, r in changes.iterrows()))
    os.makedirs("reports", exist_ok=True)
    if cal_all:
        cc = pd.concat(cal_all, ignore_index=True)
        cc.to_csv("data/catalog/lot_size_calendar.csv", index=False)
        print(f"\n  wrote data/catalog/lot_size_calendar.csv ({len(cc)} rows)")
    pd.DataFrame(rows).to_csv("reports/futures_overnight_study.csv", index=False)
    print("  wrote reports/futures_overnight_study.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
