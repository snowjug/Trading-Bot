"""
CHAIN SCREEN — where, if anywhere, is NIFTY forward return predictable?

DEVELOPMENT SET ONLY (<= 2024-09-17). Validation and the one-year holdout are not
read by this script; it asserts that before doing anything.

This is deliberately run BEFORE any strategy is written. A strategy built on a
feature with no measurable relationship to forward return cannot work, and the
previous studies in this repository spent most of their budget discovering that
one implementation at a time. Here the features are screened first and only the
survivors become candidates.

WHAT IS MEASURED
  - Spearman IC of each panel feature against four forward horizons.
  - The brief's named PCR hypotheses (PCR > 1.3 bearish, PCR < 0.7 bullish) as
    explicit conditional means, not as an assumption.
  - Quintile monotonicity, because a real effect usually orders.

MULTIPLE TESTING. ~45 features x 4 horizons is ~180 tests. At |t| = 2 roughly 9
would pass by chance. The bar applied when reading this output is therefore
|t| >= 3 AND a monotone quintile ordering AND a mechanism that can be stated in
one sentence. Everything else is noise until proven otherwise.
"""

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.chain_panel import load_panel

DEV_END = pd.Timestamp("2024-09-17")
VAL_END = pd.Timestamp("2025-09-17")
HOLDOUT_START = pd.Timestamp("2025-09-18")

HORIZONS = ["fwd_co1", "fwd_oc1", "fwd_cc1", "fwd_cc5"]

SKIP = {
    "spot", "atm", "close", "open", "high", "low", "ce_oi", "pe_oi", "ce_vol",
    "pe_vol", "ce_doi", "pe_doi", "atm_call", "atm_put", "straddle", "ce_wall",
    "pe_wall", "max_pain", "ema9", "ema21", "ema50", "ema200", "hi20", "lo20",
    "lot_size", "n_strikes", "expiry_settle", "atr14",
}


def ic(x: pd.Series, y: pd.Series) -> tuple:
    m = x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
    if m.sum() < 100:
        return np.nan, np.nan, int(m.sum())
    r, _ = stats.spearmanr(x[m], y[m])
    n = int(m.sum())
    t = r * np.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return r, t, n


def quintiles(d: pd.DataFrame, feat: str, tgt: str) -> list:
    m = d[feat].notna() & d[tgt].notna() & np.isfinite(d[feat])
    s = d[m]
    if len(s) < 250:
        return []
    try:
        q = pd.qcut(s[feat], 5, labels=False, duplicates="drop")
    except ValueError:
        return []
    return [round(float(s[tgt][q == i].mean()) * 100, 4) for i in sorted(set(q.dropna()))]


def monotone(v: list) -> bool:
    if len(v) < 4:
        return False
    a = np.array(v)
    return bool(np.all(np.diff(a) > 0) or np.all(np.diff(a) < 0))


def main() -> None:
    p = load_panel()
    p["date"] = pd.to_datetime(p["date"])
    dev = p[p["date"] <= DEV_END].copy()
    assert dev["date"].max() <= DEV_END, "DEV window leaked"
    print(f"DEV sessions {len(dev)}  {dev['date'].min().date()} -> {dev['date'].max().date()}")
    print(f"VAL sessions {((p['date'] > DEV_END) & (p['date'] <= VAL_END)).sum()}")
    print(f"HOLDOUT sessions {(p['date'] >= HOLDOUT_START).sum()}  (NOT READ HERE)\n")

    feats = [c for c in p.columns
             if c not in SKIP and not c.startswith("fwd_")
             and c not in ("date", "near_expiry", "next_expiry")
             and pd.api.types.is_numeric_dtype(p[c])]

    rows = []
    for f in feats:
        for h in HORIZONS:
            r, t, n = ic(dev[f], dev[h])
            if np.isnan(r):
                continue
            q = quintiles(dev, f, h)
            rows.append({"feature": f, "horizon": h, "ic": round(r, 4),
                         "t": round(t, 2), "n": n, "mono": monotone(q),
                         "quintiles_pct": q})
    res = pd.DataFrame(rows).sort_values("t", key=abs, ascending=False)

    print("=" * 108)
    print("TOP 30 BY |t|  (bar for a real effect: |t|>=3 AND monotone AND a stateable mechanism)")
    print("=" * 108)
    print(f"{'feature':22}{'horizon':10}{'IC':>8}{'t':>8}{'n':>7}{'mono':>7}  quintile mean fwd %")
    for _, r in res.head(30).iterrows():
        print(f"{r['feature']:22}{r['horizon']:10}{r['ic']:>8.4f}{r['t']:>8.2f}{r['n']:>7}"
              f"{str(r['mono']):>7}  {r['quintiles_pct']}")

    strong = res[(res["t"].abs() >= 3) & res["mono"]]
    print(f"\nPASSING BOTH FILTERS: {len(strong)}")
    for _, r in strong.iterrows():
        print(f"  {r['feature']:22}{r['horizon']:10} IC={r['ic']:+.4f} t={r['t']:+.2f} "
              f"n={r['n']}  {r['quintiles_pct']}")

    # ── the brief's named PCR hypotheses, stated as tests ──
    print("\n" + "=" * 108)
    print("NAMED HYPOTHESES FROM THE BRIEF (DEV only)")
    print("=" * 108)
    tests = [
        ("PCR_OI > 1.3  -> bullish?", dev["pcr_oi"] > 1.3),
        ("PCR_OI < 0.7  -> bearish?", dev["pcr_oi"] < 0.7),
        ("PCR_OI band > 1.3", dev["pcr_oi_band"] > 1.3),
        ("PCR_OI band < 0.7", dev["pcr_oi_band"] < 0.7),
        ("PCR_VOL > 1.3", dev["pcr_vol"] > 1.3),
        ("PCR_VOL < 0.7", dev["pcr_vol"] < 0.7),
        ("PCR_OI pct >= 90", dev["pcr_oi_pct"] >= 90),
        ("PCR_OI pct <= 10", dev["pcr_oi_pct"] <= 10),
        ("spot above CE wall", dev["ce_wall_gap"] < 0),
        ("spot below PE wall", dev["pe_wall_gap"] > 0),
        ("max pain above spot >0.5%", dev["max_pain_gap"] > 0.5),
        ("max pain below spot <-0.5%", dev["max_pain_gap"] < -0.5),
        ("VRP high (>8)", dev["vrp"] > 8),
        ("VRP low (<0)", dev["vrp"] < 0),
        ("straddle_pct top decile", dev["straddle_pct_pct"] >= 90),
        ("straddle_pct bottom decile", dev["straddle_pct_pct"] <= 10),
        ("expiry day (dte==0)", dev["dte"] == 0),
        ("day before expiry", dev["dte"] == 1),
    ]
    base = dev["fwd_cc1"].mean() * 100
    print(f"{'condition':30}{'n':>6}{'fwd_cc1 %':>12}{'t':>8}{'fwd_co1 %':>12}{'t':>8}"
          f"{'fwd_oc1 %':>12}{'t':>8}")
    print(f"{'(unconditional)':30}{len(dev):>6}{base:>12.4f}{'':>8}"
          f"{dev['fwd_co1'].mean()*100:>12.4f}{'':>8}{dev['fwd_oc1'].mean()*100:>12.4f}")
    out = []
    for label, mask in tests:
        m = mask.fillna(False)
        n = int(m.sum())
        if n < 30:
            print(f"{label:30}{n:>6}   too few")
            continue
        cells, rec = [], {"condition": label, "n": n}
        for h in ("fwd_cc1", "fwd_co1", "fwd_oc1"):
            x = dev.loc[m, h].dropna()
            mu = x.mean() * 100
            t = mu / (x.std(ddof=1) * 100 / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else np.nan
            cells += [f"{mu:>12.4f}", f"{t:>8.2f}"]
            rec[h] = round(mu, 4)
            rec[h + "_t"] = round(float(t), 2)
        out.append(rec)
        print(f"{label:30}{n:>6}" + "".join(cells))

    os.makedirs("reports", exist_ok=True)
    res.to_csv("reports/chain_screen_dev.csv", index=False)
    pd.DataFrame(out).to_csv("reports/chain_hypotheses_dev.csv", index=False)
    print("\nwrote reports/chain_screen_dev.csv, reports/chain_hypotheses_dev.csv")


if __name__ == "__main__":
    main()
