"""
EQUITY PANEL — daily cross-section of the NSE large-cap names held in this repo.

WHY. Every strategy ever tested here has traded one instrument: NIFTY, through its
options. The repository also holds 50 single-stock daily histories from 2015 that
no study has ever read. A cross-sectional strategy is a different mechanism with a
different cost structure: friction is paid once per multi-day holding period
instead of once per session, which is the specific reason intraday NIFTY option
buying failed (a round trip cost ~1.05% of a ~Rs 7,000 premium).

SURVIVORSHIP — STATED BEFORE ANY RESULT. The 50 price files are the CURRENT NIFTY
50 constituents. `data/universe_history/nifty50_membership_history.csv` shows at
least 20 names entered or left the index since 2015, and the ones that LEFT (DLF,
NMDC, CAIRN, PNB, BHEL, IDEA, ACC, BANKBARODA, LUPIN, ...) have no price files at
all. So the universe is the set of names that survived to 2026. This biases any
long-only or momentum result UPWARD and cannot be repaired from the data present.

Two partial mitigations are applied and neither is a fix:
  1. A name is excluded before its documented index-entry date, so the panel does
     not hold a stock during the run-up that got it promoted.
  2. Every candidate is also measured LONG-SHORT and market-neutral against the
     equal-weight universe mean, because a bias that lifts all names equally
     cancels in a spread while a bias in the ranking does not.
Any surviving result is reported with the bias attached, never without.

PRICES. The CSVs are adjusted for splits and bonuses (ADANIENT opens at 70.07 on
2015-01-01). Returns are therefore total-return-like except for dividends, which
are missing; that understates long returns slightly.

CAUSALITY. Every feature on row t uses closes up to and including t. A signal on
row t is executed at the close of t at the earliest, and `feature_columns()`
excludes every forward column.
"""

from __future__ import annotations

import glob
import os
import sys
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

RAW = "data/raw"
MEMBERSHIP = "data/universe_history/nifty50_membership_history.csv"
CACHE = "data/derived/equity_panel.parquet"

EXCLUDE = {"INDEX_BANKNIFTY", "INDEX_INDIA_VIX", "INDEX_NIFTY50", "INDEX_NIFTY_IT"}


def _entry_dates() -> Dict[str, pd.Timestamp]:
    """First documented index-entry date per symbol, if any."""
    if not os.path.exists(MEMBERSHIP):
        return {}
    m = pd.read_csv(MEMBERSHIP)
    m["date"] = pd.to_datetime(m["date"])
    out: Dict[str, pd.Timestamp] = {}
    for s, g in m[m["symbol_added"].notna()].groupby("symbol_added"):
        out[str(s)] = g["date"].min()
    return out


def build_panel() -> pd.DataFrame:
    entry = _entry_dates()
    frames: List[pd.DataFrame] = []
    for path in sorted(glob.glob(os.path.join(RAW, "*_daily.csv"))):
        sym = os.path.basename(path).replace("_daily.csv", "")
        if sym in EXCLUDE:
            continue
        d = pd.read_csv(path)
        d["datetime"] = pd.to_datetime(d["datetime"])
        d = d.sort_values("datetime").reset_index(drop=True)
        d["symbol"] = sym
        if sym in entry:
            d = d[d["datetime"] >= entry[sym]]
        frames.append(d)
    p = pd.concat(frames, ignore_index=True)

    idx = pd.read_csv(os.path.join(RAW, "INDEX_NIFTY50_daily.csv"))
    idx["datetime"] = pd.to_datetime(idx["datetime"])
    idx = idx.sort_values("datetime")
    idx["idx_ret"] = idx["close"].pct_change() * 100
    idx["idx_ret5"] = idx["close"].pct_change(5) * 100
    idx["idx_ema50"] = idx["close"].ewm(span=50, adjust=False).mean()
    idx["idx_above50"] = (idx["close"] > idx["idx_ema50"]).astype(int)

    out: List[pd.DataFrame] = []
    for sym, g in p.groupby("symbol", sort=False):
        g = g.sort_values("datetime").copy()
        c = g["close"]
        g["ret"] = c.pct_change() * 100
        g["oc"] = (g["close"] - g["open"]) / g["open"] * 100
        g["co"] = (g["open"] - c.shift(1)) / c.shift(1) * 100      # overnight
        for n in (1, 2, 3, 5, 10, 20, 60, 120, 250):
            g[f"mom{n}"] = c.pct_change(n) * 100
        g["vol20"] = g["ret"].rolling(20).std()
        g["vol60"] = g["ret"].rolling(60).std()
        prev = c.shift(1)
        tr = pd.concat([g["high"] - g["low"], (g["high"] - prev).abs(),
                        (g["low"] - prev).abs()], axis=1).max(axis=1)
        g["atr14"] = tr.rolling(14).mean()
        g["atr_pct"] = g["atr14"] / c * 100
        g["ema20"] = c.ewm(span=20, adjust=False).mean()
        g["ema50"] = c.ewm(span=50, adjust=False).mean()
        g["ema200"] = c.ewm(span=200, adjust=False).mean()
        g["dist20"] = (c - g["ema20"]) / g["ema20"] * 100
        g["dist50"] = (c - g["ema50"]) / g["ema50"] * 100
        delta = c.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        g["rsi14"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
        g["hi250"] = c.rolling(250).max()
        g["lo250"] = c.rolling(250).min()
        g["pct_52w"] = (c - g["lo250"]) / (g["hi250"] - g["lo250"]) * 100
        g["near_hi"] = c / g["hi250"] * 100
        g["dv"] = c * g["volume"]
        g["dv20"] = g["dv"].rolling(20).mean()
        g["rvol"] = g["dv"] / g["dv20"]
        g["gap"] = g["co"]
        g["range_pct"] = (g["high"] - g["low"]) / c * 100
        # forward returns — TARGETS ONLY
        for n in (1, 2, 3, 5, 10, 20):
            g[f"fwd{n}"] = c.shift(-n) / c - 1
        g["fwd_open1"] = g["open"].shift(-1) / c - 1
        # execution reference: next session's open, the earliest tradable price
        # after a close-of-day decision
        g["next_open"] = g["open"].shift(-1)
        g["next_close"] = c.shift(-1)
        out.append(g)
    p = pd.concat(out, ignore_index=True)
    p = p.merge(idx[["datetime", "idx_ret", "idx_ret5", "idx_above50"]],
                on="datetime", how="left")

    # cross-sectional ranks, computed per date across names present that date
    feats = ["mom1", "mom2", "mom3", "mom5", "mom10", "mom20", "mom60", "mom120",
             "mom250", "vol20", "vol60", "atr_pct", "rsi14", "pct_52w", "near_hi",
             "rvol", "dist20", "dist50", "gap", "range_pct"]
    p = p.sort_values(["datetime", "symbol"]).reset_index(drop=True)
    gb = p.groupby("datetime")
    for f in feats:
        p[f"r_{f}"] = gb[f].rank(pct=True) * 100
    p["n_names"] = gb["symbol"].transform("size")
    p["xs_mean_fwd1"] = gb["fwd1"].transform("mean")
    p["xs_mean_fwd5"] = gb["fwd5"].transform("mean")
    p["xs_mean_fwd10"] = gb["fwd10"].transform("mean")
    p["xs_mean_fwd20"] = gb["fwd20"].transform("mean")
    return p


def feature_columns(p: pd.DataFrame) -> List[str]:
    return [c for c in p.columns
            if not c.startswith(("fwd", "xs_mean_", "next_"))
            and c not in ("datetime", "symbol")]


def load_panel(rebuild: bool = False) -> pd.DataFrame:
    if not rebuild and os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    p = build_panel()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    p.to_parquet(CACHE, index=False)
    return p


if __name__ == "__main__":
    p = build_panel()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    p.to_parquet(CACHE, index=False)
    print(f"panel {p.shape}  {p['datetime'].min().date()} -> {p['datetime'].max().date()}")
    print(f"symbols {p['symbol'].nunique()}  names per date: "
          f"min {p['n_names'].min()} median {int(p['n_names'].median())} max {p['n_names'].max()}")
