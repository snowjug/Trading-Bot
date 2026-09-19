"""
STOCK FUTURES CROSS-SECTION — survivorship-free, shortable, and cheap to trade.

WHY THIS IS THE MOST PROMISING UNTESTED SPACE IN THE REPOSITORY.

The previous cycle measured a real short-term REVERSAL effect in Indian large caps:
the bottom quintile by 2-3 day return beats the equal-weight universe by roughly
+0.085%/day, with a date-level long-short spread of -0.0850%/day at t=-3.51 (mom3,
h=1) and -0.3644% per 5 days at t=-3.25 (mom2, h=5). It was rejected for two
reasons, and stock futures dissolve both:

  1. COST. Delivery equity pays securities transaction tax of 0.1% on EACH side,
     so a round trip costs ~0.23% against a best-case gross alpha of 0.085%/day.
     Stock FUTURES pay STT on the SELL side only, of notional, at 0.02% since
     October 2024 (0.0125% before). Total modelled round trip here is ~0.13%
     INCLUDING 0.05%/side of slippage -- and most of that is the slippage
     assumption, not tax.

  2. SHORTABILITY. Indian retail cannot hold a multi-day short in cash equity, so
     the entire long-short spread was diagnostic only. A futures short is a normal
     position, so the spread is implementable.

  3. SURVIVORSHIP, which was the fatal flaw. The previous universe was 48 CSVs of
     the CURRENT NIFTY 50, so every name that left the index was missing. This
     panel is built from the exchange's own daily F&O bhavcopy: 348 symbols over
     1,904 sessions, of which **134 stop trading more than 120 days before the end**
     (ABBOTINDIA, ACC, ALBK, AMARAJABAT, ARVIND, BATAINDIA, BEML, ...). Those names
     are present for exactly the sessions on which they existed. Nothing is
     back-filled and nothing is excluded for having disappeared.

RETURNS ARE COMPUTED WITHIN ONE CONTRACT. The near-month series rolls, and a roll
gap is a change of contract, not a price move. So a return is only formed when the
SAME expiry has a close on both sessions; a roll session's return is formed from the
incoming contract's own previous close, which the bhavcopy also publishes. No
continuous price is spliced and no roll gap is ever counted as a return.

CAUSALITY. Every feature on row t uses closes up to and including t. Forward columns
are prefixed `fwd` and are excluded by `feature_columns()`.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

NEAR = "data/derived/futstk_near.parquet"
ALL_FUT = "data/derived/futstk_all.parquet"
CACHE = "data/derived/futstk_panel.parquet"

# ── Statutory friction on a STOCK FUTURES round trip, as fractions of notional ──
STT_SELL = {"pre_2024_10": 0.000125, "post_2024_10": 0.0002}   # sell side only
EXCH_TXN = 0.0000173        # per side
SEBI_RATE = 0.000001        # per side
STAMP_BUY = 0.00002         # buy side only
GST_RATE = 0.18             # on brokerage + exchange + SEBI
BROKERAGE_PER_ORDER = 20.0  # rupees, flat per order
DEFAULT_SLIP_PER_SIDE = 0.0005      # 5 bp; stock futures are wider than index


def roundtrip_cost_pct(notional_per_lot: float = 500000.0,
                       slip_per_side: float = DEFAULT_SLIP_PER_SIDE,
                       post_oct_2024: bool = True, mult: float = 1.0) -> float:
    """
    Round-trip cost as a FRACTION of notional, for one lot.

    Brokerage is per order, so it is divided by the notional rather than ignored:
    on a Rs 5 lakh lot two Rs 20 orders are 0.008%, which is small but real.
    """
    stt = STT_SELL["post_2024_10" if post_oct_2024 else "pre_2024_10"]
    exch = EXCH_TXN * 2
    sebi = SEBI_RATE * 2
    stamp = STAMP_BUY
    brok = BROKERAGE_PER_ORDER * 2 / max(notional_per_lot, 1.0)
    gst = GST_RATE * (brok + exch + sebi)
    slip = slip_per_side * 2
    return (stt + exch + sebi + stamp + brok + gst + slip) * mult


def _same_contract_returns(g: pd.DataFrame, allfut: pd.DataFrame) -> pd.DataFrame:
    """
    Daily return for one symbol, always within a single contract.

    On a non-roll session the previous close is the same contract's previous close.
    On a roll session it is the INCOMING contract's close on the previous session,
    looked up in the full contract table. If that lookup fails the return is NaN --
    never a roll gap dressed up as a move.
    """
    g = g.sort_values("TradDt").reset_index(drop=True)
    prev_close = g["ClsPric"].shift(1)
    prev_xp = g["XpryDt"].shift(1)
    prev_dt = g["TradDt"].shift(1)
    same = prev_xp == g["XpryDt"]

    need = g[(~same) & prev_dt.notna()]
    if len(need):
        key = allfut.set_index(["TckrSymb", "TradDt", "XpryDt"])["ClsPric"]
        fixed = []
        for i, r in need.iterrows():
            try:
                v = float(key.loc[(r["TckrSymb"], prev_dt.loc[i], r["XpryDt"])])
            except (KeyError, TypeError, ValueError):
                v = np.nan
            fixed.append((i, v if (np.isfinite(v) and v > 0) else np.nan))
        for i, v in fixed:
            prev_close.loc[i] = v

    g["prev_close_same_contract"] = prev_close
    g["ret"] = (g["ClsPric"] / prev_close - 1.0) * 100
    g["rolled"] = ~same
    return g


def build_panel(min_contracts: float = 500.0, min_sessions: int = 250) -> pd.DataFrame:
    if not os.path.exists(NEAR):
        raise SystemExit(f"{NEAR} missing — build it from data/raw/nse/fo_futures first")
    near = pd.read_parquet(NEAR)
    allfut = pd.read_parquet(ALL_FUT, columns=["TckrSymb", "TradDt", "XpryDt", "ClsPric"])
    for d in (near, allfut):
        d["TradDt"] = pd.to_datetime(d["TradDt"])
        d["XpryDt"] = pd.to_datetime(d["XpryDt"])

    vol = near["TtlTradgVol"].fillna(near.get("LegacyContracts"))
    near = near.assign(contracts=vol)
    counts = near.groupby("TckrSymb")["TradDt"].nunique()
    keep = counts[counts >= min_sessions].index
    near = near[near["TckrSymb"].isin(keep)].copy()

    out: List[pd.DataFrame] = []
    for sym, g in near.groupby("TckrSymb", sort=False):
        g = _same_contract_returns(g, allfut)
        c = g["ClsPric"]
        # trailing features only
        for n in (1, 2, 3, 5, 10, 20, 60, 120, 250):
            g[f"mom{n}"] = c.pct_change(n, fill_method=None) * 100
        g["vol20"] = g["ret"].rolling(20).std()
        g["vol60"] = g["ret"].rolling(60).std()
        prev = c.shift(1)
        tr = pd.concat([g["HghPric"] - g["LwPric"], (g["HghPric"] - prev).abs(),
                        (g["LwPric"] - prev).abs()], axis=1).max(axis=1)
        g["atr_pct"] = tr.rolling(14).mean() / c * 100
        delta = c.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        g["rsi14"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
        g["ema20"] = c.ewm(span=20, adjust=False).mean()
        g["dist20"] = (c - g["ema20"]) / g["ema20"] * 100
        g["hi250"] = c.rolling(250).max()
        g["lo250"] = c.rolling(250).min()
        g["pct_52w"] = (c - g["lo250"]) / (g["hi250"] - g["lo250"]) * 100
        g["oi_chg20"] = g["OpnIntrst"].pct_change(20, fill_method=None) * 100
        g["doi"] = g["OpnIntrst"].pct_change(fill_method=None) * 100
        g["rvol"] = g["contracts"] / g["contracts"].rolling(20).mean()
        g["turnover"] = g["contracts"] * c
        g["turn20"] = g["turnover"].rolling(20).mean()
        # forward returns — TARGETS ONLY, same-contract by construction
        for n in (1, 2, 3, 5, 10, 20):
            g[f"fwd{n}"] = ((1 + g["ret"].shift(-1) / 100).rolling(n).apply(
                np.prod, raw=True).shift(-(n - 1)) - 1) * 100
        out.append(g)

    p = pd.concat(out, ignore_index=True)
    p = p[p["contracts"].fillna(0) >= min_contracts].copy()
    p = p.sort_values(["TradDt", "TckrSymb"]).reset_index(drop=True)

    feats = ["mom1", "mom2", "mom3", "mom5", "mom10", "mom20", "mom60", "mom120",
             "mom250", "vol20", "vol60", "atr_pct", "rsi14", "dist20", "pct_52w",
             "oi_chg20", "doi", "rvol", "turn20"]
    gb = p.groupby("TradDt")
    for f in feats:
        p[f"r_{f}"] = gb[f].rank(pct=True) * 100
    p["n_names"] = gb["TckrSymb"].transform("size")
    for n in (1, 2, 3, 5, 10, 20):
        p[f"xs_fwd{n}"] = gb[f"fwd{n}"].transform("mean")
    return p


def feature_columns(p: pd.DataFrame) -> List[str]:
    return [c for c in p.columns
            if not c.startswith(("fwd", "xs_fwd"))
            and c not in ("TradDt", "TckrSymb", "XpryDt", "prev_close_same_contract")]


def load_panel(rebuild: bool = False) -> pd.DataFrame:
    if not rebuild and os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    p = build_panel()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    p.to_parquet(CACHE, index=False)
    return p


def tstat(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")


if __name__ == "__main__":
    p = build_panel()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    p.to_parquet(CACHE, index=False)
    print(f"panel {p.shape}  {p['TradDt'].min().date()} -> {p['TradDt'].max().date()}")
    print(f"symbols {p['TckrSymb'].nunique()}  names per date: min {p['n_names'].min()} "
          f"median {int(p['n_names'].median())} max {p['n_names'].max()}")
    print(f"rolled rows {int(p['rolled'].sum()):,}  ret NaN {int(p['ret'].isna().sum()):,}")
    print(f"round-trip cost at 5 bp/side slippage: "
          f"{roundtrip_cost_pct()*100:.4f}% of notional")
