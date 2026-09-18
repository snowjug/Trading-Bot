"""
Where does intraday directional edge actually live?

Everything measured so far says the binding constraint is SIGNAL ACCURACY, not
costs: Bot 6's spot call was right 43.4% of the time against a 33.3% break-even,
and Bot 5, C4 and the opening-range work all failed the same way. Guessing another
strategy would repeat that. This measures the raw predictive content of a set of
causal features FIRST, so strategy construction starts from what the data supports.

DEV/VALIDATION ONLY. Everything here is computed strictly before 2026-06-18; the
three-month holdout is never touched.

CAUSALITY. At decision bar i of session d, a feature may read only:
  * completed daily sessions strictly before d
  * intraday bars of session d up to and including i
Forward returns are computed after the fact purely as the TARGET, never as input.
"""

import os
import sys
from datetime import date, time as dtime
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m

HOLDOUT_START = pd.Timestamp("2026-06-18").date()
DECISION_TIMES = [dtime(9, 45), dtime(10, 15), dtime(11, 0), dtime(12, 0),
                  dtime(13, 0), dtime(14, 0)]


def daily_frame() -> pd.DataFrame:
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    c = d["close"]
    prev = c.shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev).abs(),
                    (d["low"] - prev).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    d["ema9"] = c.ewm(span=9, adjust=False).mean()
    d["ema21"] = c.ewm(span=21, adjust=False).mean()
    d["ema50"] = c.ewm(span=50, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi14"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    d["range"] = d["high"] - d["low"]
    d["range_pctile"] = d["range"].rolling(20).rank(pct=True)
    d["vix_chg"] = d["vix"].diff()
    d["vix_z"] = (d["vix"] - d["vix"].rolling(60).mean()) / d["vix"].rolling(60).std()
    d["ret1"] = c.pct_change()
    d["ret5"] = c.pct_change(5)
    d["sess"] = d["datetime"].dt.date
    return d


def build_observations(grid: Dict[str, pd.DataFrame], daily: pd.DataFrame) -> pd.DataFrame:
    """One row per (session, decision time) with causal features and forward targets."""
    by_day = {k: v for k, v in grid["ce"].groupby(grid["ce"]["datetime"].dt.date, sort=False)}
    dpos = {d: i for i, d in enumerate(daily["sess"])}
    rows: List[Dict] = []

    for sess, day in by_day.items():
        if sess >= HOLDOUT_START or sess not in dpos:
            continue
        i = dpos[sess]
        if i < 60:
            continue
        prior = daily.iloc[i - 1]          # strictly completed
        if not np.isfinite(prior["atr14"]) or prior["atr14"] <= 0:
            continue

        sp = day.groupby("datetime")["spot"].first().sort_index()
        sp = sp[(sp.index.time >= dtime(9, 15)) & (sp.index.time <= dtime(15, 20))]
        if len(sp) < 50:
            continue
        vals = sp.values.astype(float)
        times = [t.time() for t in sp.index]
        atr = float(prior["atr14"])
        open_px = float(vals[0])
        prev_close = float(prior["close"])
        prev_high, prev_low = float(prior["high"]), float(prior["low"])

        # opening range: first 30 minutes, complete by 09:45
        or_mask = [t <= dtime(9, 45) for t in times]
        or_hi = float(np.max(vals[or_mask])) if any(or_mask) else np.nan
        or_lo = float(np.min(vals[or_mask])) if any(or_mask) else np.nan

        eod = float(vals[-1])
        for dt_ in DECISION_TIMES:
            idx = next((k for k, t in enumerate(times) if t >= dt_), None)
            if idx is None or idx < 3 or idx >= len(vals) - 6:
                continue
            px = float(vals[idx])
            hist_slice = vals[:idx + 1]
            twap = float(np.mean(hist_slice))
            s_hi, s_lo = float(np.max(hist_slice)), float(np.min(hist_slice))

            fwd_eod = (eod - px) / atr
            j30 = min(idx + 6, len(vals) - 1)
            j60 = min(idx + 12, len(vals) - 1)
            fwd30 = (float(vals[j30]) - px) / atr
            fwd60 = (float(vals[j60]) - px) / atr
            tail = vals[idx:]
            mfe = (float(np.max(tail)) - px) / atr
            mae = (float(np.min(tail)) - px) / atr

            rows.append({
                "sess": sess, "time": dt_.strftime("%H:%M"), "atr": atr,
                # ── causal features ──
                "gap": (open_px - prev_close) / atr,
                "from_open": (px - open_px) / atr,
                "from_twap": (px - twap) / atr,
                "from_prev_high": (px - prev_high) / atr,
                "from_prev_low": (px - prev_low) / atr,
                "sess_range": (s_hi - s_lo) / atr,
                "pos_in_sess": (px - s_lo) / max(s_hi - s_lo, 1e-9),
                "or_break_up": (px - or_hi) / atr if np.isfinite(or_hi) else np.nan,
                "or_break_dn": (or_lo - px) / atr if np.isfinite(or_lo) else np.nan,
                "mom6": (px - float(vals[max(idx - 6, 0)])) / atr,
                "mom12": (px - float(vals[max(idx - 12, 0)])) / atr,
                "ema_stack": (1 if prior["ema9"] > prior["ema21"] > prior["ema50"]
                              else (-1 if prior["ema9"] < prior["ema21"] < prior["ema50"] else 0)),
                "rsi": float(prior["rsi14"]),
                "vix": float(prior["vix"]),
                "vix_z": float(prior["vix_z"]) if np.isfinite(prior["vix_z"]) else 0.0,
                "prev_range_pct": float(prior["range_pctile"]) if np.isfinite(prior["range_pctile"]) else 0.5,
                "prev_ret1": float(prior["ret1"]) * 100,
                "prev_ret5": float(prior["ret5"]) * 100,
                # ── targets (never inputs) ──
                "fwd_eod": fwd_eod, "fwd30": fwd30, "fwd60": fwd60,
                "mfe": mfe, "mae": mae,
            })
    return pd.DataFrame(rows)


def ic_report(df: pd.DataFrame, feats: List[str], targets: List[str]) -> pd.DataFrame:
    """Spearman information coefficient per feature, per target, per decision time."""
    out = []
    for f in feats:
        row = {"feature": f}
        for t in targets:
            sub = df[[f, t]].dropna()
            row[t] = round(float(sub[f].corr(sub[t], method="spearman")), 4) if len(sub) > 200 else np.nan
        row["n"] = int(df[f].notna().sum())
        out.append(row)
    return pd.DataFrame(out)


def decile_edge(df: pd.DataFrame, feat: str, target: str = "fwd_eod", q: int = 10) -> pd.DataFrame:
    sub = df[[feat, target]].dropna()
    if len(sub) < 500:
        return pd.DataFrame()
    sub = sub.copy()
    sub["bucket"] = pd.qcut(sub[feat], q, labels=False, duplicates="drop")
    g = sub.groupby("bucket")[target].agg(["count", "mean", "median"])
    g["hit_rate"] = sub.groupby("bucket")[target].apply(lambda x: float((x > 0).mean()))
    return g.round(4)


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    print("building causal observation set (dev/validation only, pre-2026-06-18)...")
    obs = build_observations(grid, daily)
    print(f"observations: {len(obs):,} across {obs['sess'].nunique()} sessions "
          f"{obs['sess'].min()} .. {obs['sess'].max()}")

    feats = ["gap", "from_open", "from_twap", "from_prev_high", "from_prev_low",
             "sess_range", "pos_in_sess", "or_break_up", "or_break_dn",
             "mom6", "mom12", "ema_stack", "rsi", "vix", "vix_z",
             "prev_range_pct", "prev_ret1", "prev_ret5"]
    targets = ["fwd_eod", "fwd30", "fwd60"]

    print("\n" + "=" * 78)
    print("INFORMATION COEFFICIENT (Spearman) — all decision times pooled")
    print("=" * 78)
    r = ic_report(obs, feats, targets).sort_values("fwd_eod", key=abs, ascending=False)
    print(r.to_string(index=False))

    print("\n" + "=" * 78)
    print("IC BY DECISION TIME (target: fwd_eod)")
    print("=" * 78)
    tbl = {}
    for t, g in obs.groupby("time"):
        tbl[t] = {f: (round(float(g[[f, "fwd_eod"]].dropna()[f].corr(
            g[[f, "fwd_eod"]].dropna()["fwd_eod"], method="spearman")), 3)
            if g[f].notna().sum() > 200 else np.nan) for f in feats}
    print(pd.DataFrame(tbl).to_string())

    top = r.head(5)["feature"].tolist()
    for f in top:
        print(f"\n--- DECILES: {f} vs fwd_eod (ATR units) ---")
        d = decile_edge(obs, f)
        if not d.empty:
            print(d.to_string())

    obs.to_parquet("data/derived/edge_obs_dev.parquet", index=False)
    print(f"\nwrote data/derived/edge_obs_dev.parquet ({len(obs):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
