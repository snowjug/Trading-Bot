"""
Tails, asymmetry and signal combination on the DEV set.

A weak information coefficient does not by itself decide whether a LONG OPTION
strategy works. A bought option has a capped loss and an uncapped gain, so what
matters is the shape of the forward distribution in the extreme buckets — the
MFE/MAE asymmetry — not the mean of the whole sample.

DEV/VALIDATION ONLY. Nothing after 2026-06-17 is read.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

OBS = "data/derived/edge_obs_dev.parquet"


def tail_table(df: pd.DataFrame, feat: str, target: str = "fwd_eod") -> pd.DataFrame:
    """Extreme buckets only — where a selective strategy would actually trade."""
    sub = df[[feat, target, "mfe", "mae", "atr"]].dropna().copy()
    qs = sub[feat].quantile([0.05, 0.10, 0.20, 0.80, 0.90, 0.95])
    out = []
    for label, mask in [
        ("bottom 5%", sub[feat] <= qs[0.05]),
        ("bottom 10%", sub[feat] <= qs[0.10]),
        ("bottom 20%", sub[feat] <= qs[0.20]),
        ("top 20%", sub[feat] >= qs[0.80]),
        ("top 10%", sub[feat] >= qs[0.90]),
        ("top 5%", sub[feat] >= qs[0.95]),
    ]:
        s = sub[mask]
        if len(s) < 100:
            continue
        # a LONG trade in the direction of the tail
        sign = -1.0 if "bottom" in label else 1.0
        directional = s[target] * sign
        mfe_dir = (s["mfe"] if sign > 0 else -s["mae"])
        mae_dir = (s["mae"] if sign > 0 else -s["mfe"])
        out.append({
            "bucket": label, "n": len(s),
            "fwd_mean": round(float(directional.mean()), 4),
            "fwd_med": round(float(directional.median()), 4),
            "hit%": round(float((directional > 0).mean() * 100), 1),
            "MFE": round(float(mfe_dir.mean()), 4),
            "MAE": round(float(mae_dir.mean()), 4),
            "MFE/|MAE|": round(float(mfe_dir.mean() / abs(mae_dir.mean())), 2)
            if mae_dir.mean() != 0 else np.nan,
        })
    return pd.DataFrame(out)


def combo_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    A simple additive score over z-scored continuation features.

    Deliberately NOT a fitted model: equal weights on features that already showed
    the same sign, so there is nothing to overfit. If the combination beats its
    parts, the signal is broad rather than an artefact of one feature.
    """
    d = df.copy()
    parts = ["from_open", "pos_in_sess", "from_twap", "mom12", "or_break_up"]
    for p in parts:
        mu, sd = d[p].mean(), d[p].std()
        d[f"z_{p}"] = (d[p] - mu) / (sd if sd else 1)
    # pos_in_sess is 0..1 not centred on zero; recentre so "high" means "near high"
    d["z_pos_in_sess"] = (d["pos_in_sess"] - 0.5) / 0.5
    d["combo"] = d[[f"z_{p}" for p in parts]].mean(axis=1)
    return d


def main() -> int:
    df = pd.read_parquet(OBS)
    print(f"dev observations: {len(df):,}  sessions {df.sess.min()} .. {df.sess.max()}")

    print("\n" + "=" * 86)
    print("TAIL BEHAVIOUR — directional long trade taken in the tail's own direction")
    print("(units: ATR of the prior session)")
    print("=" * 86)
    for f in ("from_open", "pos_in_sess", "from_twap", "mom12"):
        print(f"\n--- {f} ---")
        print(tail_table(df, f).to_string(index=False))

    d = combo_score(df)
    print("\n" + "=" * 86)
    print("COMBINED CONTINUATION SCORE (equal-weight z, no fitting)")
    print("=" * 86)
    print(tail_table(d, "combo").to_string(index=False))

    print("\n" + "=" * 86)
    print("COMBINED SCORE BY DECISION TIME (top/bottom 10% only)")
    print("=" * 86)
    rows = []
    for t, g in d.groupby("time"):
        s = g[["combo", "fwd_eod", "mfe", "mae"]].dropna()
        if len(s) < 100:
            continue
        hi = s[s["combo"] >= s["combo"].quantile(0.90)]
        lo = s[s["combo"] <= s["combo"].quantile(0.10)]
        rows.append({
            "time": t, "n_hi": len(hi), "hi_fwd": round(float(hi["fwd_eod"].mean()), 4),
            "hi_hit%": round(float((hi["fwd_eod"] > 0).mean() * 100), 1),
            "n_lo": len(lo), "lo_fwd": round(float(-lo["fwd_eod"].mean()), 4),
            "lo_hit%": round(float((lo["fwd_eod"] < 0).mean() * 100), 1),
        })
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n" + "=" * 86)
    print("REGIME CONDITIONING — combined score top/bottom 10%, split by prior VIX")
    print("=" * 86)
    d2 = d.dropna(subset=["combo", "fwd_eod"]).copy()
    d2["vix_bucket"] = pd.cut(d2["vix"], [0, 12, 14, 17, 100],
                              labels=["<12", "12-14", "14-17", ">17"])
    rows = []
    for b, g in d2.groupby("vix_bucket", observed=True):
        hi = g[g["combo"] >= g["combo"].quantile(0.90)]
        lo = g[g["combo"] <= g["combo"].quantile(0.10)]
        if len(hi) < 50:
            continue
        rows.append({
            "vix": b, "n": len(g),
            "hi_fwd": round(float(hi["fwd_eod"].mean()), 4),
            "hi_hit%": round(float((hi["fwd_eod"] > 0).mean() * 100), 1),
            "lo_fwd": round(float(-lo["fwd_eod"].mean()), 4),
            "lo_hit%": round(float((lo["fwd_eod"] < 0).mean() * 100), 1),
        })
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n" + "=" * 86)
    print("HOW BIG IS THE MOVE? distribution of |fwd_eod| in the extreme buckets")
    print("=" * 86)
    s = d.dropna(subset=["combo", "fwd_eod"])
    ext = s[(s["combo"] >= s["combo"].quantile(0.90)) | (s["combo"] <= s["combo"].quantile(0.10))]
    dirn = np.where(ext["combo"] > 0, 1, -1)
    move = ext["fwd_eod"] * dirn
    for q in (0.1, 0.25, 0.5, 0.75, 0.9):
        print(f"   p{int(q*100):>2}: {move.quantile(q):+.3f} ATR")
    print(f"   mean {move.mean():+.4f} ATR   >0: {float((move>0).mean()*100):.1f}%")
    atr_med = float(s["atr"].median())
    print(f"   median prior ATR = {atr_med:.0f} NIFTY points")
    print(f"   mean move in points = {move.mean()*atr_med:+.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
