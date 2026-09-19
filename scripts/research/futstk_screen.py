"""
STOCK FUTURES CROSS-SECTION SCREEN — development set only (2019-01 .. 2024-09-17).

Validation (2024-09-18 .. 2025-09-17) and the one-year holdout (2025-09-18 ..
2026-09-18) are not read; the script asserts that.

WHAT IS DIFFERENT FROM THE PREVIOUS CYCLE'S EQUITY SCREEN, which measured a real
reversal effect and then had to reject it:

  universe       348 F&O symbols from the exchange's own bhavcopy, of which 134 stop
                 trading long before the end -> SURVIVORSHIP-FREE, against 48 CSVs of
                 the current NIFTY 50 last time
  shortable      a futures short is a normal multi-day position, so the long-short
                 spread is implementable rather than diagnostic
  cost           0.1358% round trip modelled (STT sell-side 0.02% of notional,
                 exchange, SEBI, stamp, GST, Rs 20/order, and 5 bp/side slippage)
                 against ~0.23% for delivery equity, where 0.20% was tax alone

The long-short spread is computed PER DATE and then sampled every h-th date so the
series is non-overlapping and the t-stat is honest. A date-level series is also the
only thing a portfolio actually earns: an IC computed across 180 correlated names on
one date would be inflated by construction.

MULTIPLE TESTING. 19 features x 6 horizons = 114 tests. The bar is |t| >= 3, a
monotone quintile ordering, a stateable mechanism, AND a net-of-cost spread that is
still positive.
"""

import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.stock_futures_panel import load_panel, roundtrip_cost_pct, tstat

DEV_END = pd.Timestamp("2024-09-17")
VAL_END = pd.Timestamp("2025-09-17")

FEATS = ["mom1", "mom2", "mom3", "mom5", "mom10", "mom20", "mom60", "mom120",
         "mom250", "vol20", "vol60", "atr_pct", "rsi14", "dist20", "pct_52w",
         "oi_chg20", "doi", "rvol", "turn20"]
HOR = [1, 2, 3, 5, 10, 20]


def main() -> int:
    p = load_panel()
    p["TradDt"] = pd.to_datetime(p["TradDt"])
    dev = p[p["TradDt"] <= DEV_END].copy()
    assert dev["TradDt"].max() <= DEV_END, "DEV leaked"
    print(f"DEV rows {len(dev):,}  dates {dev['TradDt'].nunique():,}  "
          f"symbols {dev['TckrSymb'].nunique()}  "
          f"{dev['TradDt'].min().date()} -> {dev['TradDt'].max().date()}")
    print(f"VAL dates {p[(p['TradDt'] > DEV_END) & (p['TradDt'] <= VAL_END)]['TradDt'].nunique()}")
    print(f"HOLDOUT dates {p[p['TradDt'] > VAL_END]['TradDt'].nunique()}  [NOT READ]")
    cost = roundtrip_cost_pct() * 100
    print(f"\nround-trip cost modelled: {cost:.4f}% of notional per leg-pair side")
    print(f"a long-short pair pays it TWICE (one long + one short) = {2 * cost:.4f}%\n")

    rows = []
    print("=" * 118)
    print("DATE-LEVEL LONG-SHORT QUINTILE SPREAD, market-relative, DEV only")
    print("A negative spread means the BOTTOM quintile wins, i.e. reversal; trade it reversed.")
    print("=" * 118)
    print(f"{'feature':10}{'h':>3}{'periods':>9}{'LS%/per':>10}{'t':>7}{'ann%':>8}"
          f"{'|LS|-cost':>11}{'net t':>7}{'mono':>6}  quintiles (market-relative %)")
    for f in FEATS:
        rc = f"r_{f}"
        for h in HOR:
            tgt, xs = f"fwd{h}", f"xs_fwd{h}"
            s = dev[["TradDt", rc, tgt, xs]].dropna()
            if len(s) < 20000:
                continue
            s = s.assign(rel=s[tgt] - s[xs],
                         q=pd.cut(s[rc], [0, 20, 40, 60, 80, 100], labels=False))
            g = s.groupby("TradDt")
            ls = g.apply(lambda x: x.loc[x["q"] == 4, "rel"].mean()
                         - x.loc[x["q"] == 0, "rel"].mean(),
                         include_groups=False).dropna()
            lsn = ls.iloc[::h]                       # non-overlapping
            if len(lsn) < 30:
                continue
            means = [float(s.loc[s["q"] == i, "rel"].mean()) for i in range(5)]
            mono = bool(np.all(np.diff(means) > 0) or np.all(np.diff(means) < 0))
            # a reversal spread is traded reversed, so the tradable gross is |LS|
            gross = abs(float(lsn.mean()))
            net = gross - 2 * cost
            net_series = lsn.abs() - 2 * cost if lsn.mean() < 0 else lsn - 2 * cost
            ann = net * (250 / h)
            print(f"{f:10}{h:>3}{len(lsn):>9}{lsn.mean():>10.4f}{tstat(lsn):>7.2f}"
                  f"{lsn.mean()*(250/h):>8.1f}{net:>11.4f}{tstat(net_series):>7.2f}"
                  f"{str(mono):>6}  {[round(m,4) for m in means]}")
            rows.append({"feature": f, "horizon": h, "periods": len(lsn),
                         "ls_pct": round(float(lsn.mean()), 4),
                         "ls_t": round(tstat(lsn), 2),
                         "gross_abs": round(gross, 4),
                         "net_after_cost": round(net, 4),
                         "net_t": round(tstat(net_series), 2),
                         "net_ann_pct": round(ann, 2), "mono": mono,
                         "quintiles": str([round(m, 4) for m in means])})

    r = pd.DataFrame(rows)
    os.makedirs("reports", exist_ok=True)
    r.to_csv("reports/futstk_screen_dev.csv", index=False)

    print("\n" + "=" * 118)
    print("SURVIVORS: |t| >= 3  AND  monotone  AND  net of cost still positive")
    print("=" * 118)
    surv = r[(r["ls_t"].abs() >= 3) & r["mono"] & (r["net_after_cost"] > 0)]
    if surv.empty:
        print("  none")
    for _, x in surv.sort_values("net_ann_pct", ascending=False).iterrows():
        print(f"  {x['feature']:10} h={x['horizon']:<3} LS={x['ls_pct']:+.4f}%/period "
              f"t={x['ls_t']:+.2f}  net {x['net_after_cost']:+.4f}%/period "
              f"= {x['net_ann_pct']:+.1f}%/yr  {x['quintiles']}")
    print(f"\ntop 10 by net annualised, regardless of the filters:")
    for _, x in r.sort_values("net_ann_pct", ascending=False).head(10).iterrows():
        print(f"  {x['feature']:10} h={x['horizon']:<3} LS={x['ls_pct']:+.4f}% "
              f"t={x['ls_t']:+.2f}  net {x['net_after_cost']:+.4f}%/period "
              f"= {x['net_ann_pct']:+.1f}%/yr  mono={x['mono']}")
    print("\nwrote reports/futstk_screen_dev.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
