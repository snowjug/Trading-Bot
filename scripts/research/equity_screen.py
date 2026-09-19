"""
EQUITY CROSS-SECTION SCREEN — development set only (2015-01 .. 2024-09-17).

WHAT IS MEASURED. For each ranked feature, the forward return of the top and
bottom quintile MINUS the equal-weight universe mean for the same date. The
subtraction matters more here than anywhere else in this study: the universe is
the set of names that survived to 2026 (see `src/research/equity_panel.py`), so
the absolute return of any long basket is inflated. A bias that lifts every name
equally cancels in the market-relative number; only bias in the RANKING survives,
and that is what is being screened for.

WHAT IS TRADABLE. Indian retail cannot hold a multi-day short in cash equity, and
this repository has no single-stock futures data, so the bottom quintile is
diagnostic only. A tradable candidate is LONG-ONLY and therefore carries full
market beta; the market-relative column is the only place its alpha appears.

MULTIPLE TESTING. 20 features x 4 horizons x 2 tails = 160 tests. |t| >= 3 plus a
monotone quintile ordering plus a stateable mechanism is the bar.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.equity_panel import load_panel

DEV_END = pd.Timestamp("2024-09-17")
VAL_END = pd.Timestamp("2025-09-17")

FEATS = ["mom1", "mom2", "mom3", "mom5", "mom10", "mom20", "mom60", "mom120",
         "mom250", "vol20", "vol60", "atr_pct", "rsi14", "pct_52w", "near_hi",
         "rvol", "dist20", "dist50", "gap", "range_pct"]
HOR = [1, 5, 10, 20]


def t_of(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")


def main() -> None:
    p = load_panel()
    p["datetime"] = pd.to_datetime(p["datetime"])
    dev = p[p["datetime"] <= DEV_END].copy()
    assert dev["datetime"].max() <= DEV_END, "DEV leaked"
    print(f"DEV rows {len(dev):,}  dates {dev['datetime'].nunique():,}  "
          f"{dev['datetime'].min().date()} -> {dev['datetime'].max().date()}")
    print(f"VAL dates {p[(p['datetime'] > DEV_END) & (p['datetime'] <= VAL_END)]['datetime'].nunique()}")
    print(f"HOLDOUT dates {p[p['datetime'] > VAL_END]['datetime'].nunique()}  [NOT READ HERE]\n")

    rows = []
    for f in FEATS:
        rc = f"r_{f}"
        for h in HOR:
            tgt, xs = f"fwd{h}", f"xs_mean_fwd{h}"
            s = dev[[rc, tgt, xs]].dropna()
            if len(s) < 5000:
                continue
            rel = (s[tgt] - s[xs]) * 100
            q = pd.cut(s[rc], [0, 20, 40, 60, 80, 100], labels=False)
            means = [float(rel[q == i].mean()) for i in range(5)]
            top, bot = rel[q == 4], rel[q == 0]
            # per-date spread, so the t-stat is not inflated by cross-sectional
            # correlation within a date
            byd = s.assign(rel=rel, q=q).groupby("datetime" if "datetime" in s else s.index)
            rows.append({
                "feature": f, "horizon": h, "n": len(s),
                "q1": round(means[0], 4), "q2": round(means[1], 4),
                "q3": round(means[2], 4), "q4": round(means[3], 4),
                "q5": round(means[4], 4),
                "spread": round(means[4] - means[0], 4),
                "t_top": round(t_of(top.to_numpy()), 2),
                "t_bot": round(t_of(bot.to_numpy()), 2),
                "mono": bool(np.all(np.diff(means) > 0) or np.all(np.diff(means) < 0)),
            })
    res = pd.DataFrame(rows)

    # Proper t-stats on the DATE-level long-short spread series, which is what a
    # portfolio actually earns and which is not inflated by 45 correlated names.
    print("=" * 112)
    print("DATE-LEVEL LONG-SHORT QUINTILE SPREAD (market-relative), DEV only")
    print("=" * 112)
    print(f"{'feature':10}{'h':>3}{'n dates':>9}{'LS/period%':>12}{'t':>8}"
          f"{'ann%':>8}{'LONG-only rel%':>16}{'t':>8}{'mono':>6}  quintiles")
    out = []
    for f in FEATS:
        rc = f"r_{f}"
        for h in HOR:
            tgt, xs = f"fwd{h}", f"xs_mean_fwd{h}"
            s = dev[["datetime", rc, tgt, xs]].dropna()
            if len(s) < 5000:
                continue
            s = s.assign(rel=(s[tgt] - s[xs]) * 100,
                         q=pd.cut(s[rc], [0, 20, 40, 60, 80, 100], labels=False))
            g = s.groupby("datetime")
            ls = (g.apply(lambda x: x.loc[x["q"] == 4, "rel"].mean()
                          - x.loc[x["q"] == 0, "rel"].mean(), include_groups=False)
                  .dropna())
            lo = g.apply(lambda x: x.loc[x["q"] == 4, "rel"].mean(),
                         include_groups=False).dropna()
            # overlapping h-day windows: sample every h-th date so the series is
            # non-overlapping and the t-stat is honest
            lsn, lon = ls.iloc[::h], lo.iloc[::h]
            r = res[(res["feature"] == f) & (res["horizon"] == h)].iloc[0]
            qs = [r["q1"], r["q2"], r["q3"], r["q4"], r["q5"]]
            ann = lsn.mean() * (250 / h)
            print(f"{f:10}{h:>3}{len(lsn):>9}{lsn.mean():>12.4f}{t_of(lsn.to_numpy()):>8.2f}"
                  f"{ann:>8.1f}{lon.mean():>16.4f}{t_of(lon.to_numpy()):>8.2f}"
                  f"{str(r['mono']):>6}  {qs}")
            out.append({"feature": f, "horizon": h, "n_periods": len(lsn),
                        "ls_mean": round(float(lsn.mean()), 4),
                        "ls_t": round(t_of(lsn.to_numpy()), 2),
                        "ls_ann": round(float(ann), 2),
                        "long_rel": round(float(lon.mean()), 4),
                        "long_t": round(t_of(lon.to_numpy()), 2),
                        "mono": bool(r["mono"]), "quintiles": str(qs)})

    o = pd.DataFrame(out)
    os.makedirs("reports", exist_ok=True)
    o.to_csv("reports/equity_screen_dev.csv", index=False)
    strong = o[(o["ls_t"].abs() >= 3) & o["mono"]]
    print(f"\nPASSING |t|>=3 AND monotone: {len(strong)}")
    for _, r in strong.sort_values("ls_t", key=abs, ascending=False).iterrows():
        print(f"  {r['feature']:10} h={r['horizon']:<3} LS={r['ls_mean']:+.4f}%/period "
              f"t={r['ls_t']:+.2f} ann={r['ls_ann']:+.1f}%  long-only rel "
              f"{r['long_rel']:+.4f}% t={r['long_t']:+.2f}")
    print("\nwrote reports/equity_screen_dev.csv")


if __name__ == "__main__":
    main()
