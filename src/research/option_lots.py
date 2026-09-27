"""
AUTHENTIC INDEX-OPTION LOT SIZE per (session, expiry).

WHY THIS MODULE EXISTS. `data/derived/chain_panel.parquet` carries `lot_size` for only 668
of 1,903 sessions, all from 2024 onward, so every study on a 2022-2023 window had no lot
size and could not state a rupee result. Guessing one is a forbidden substitution.

TWO SOURCES, IN ORDER OF AUTHORITY.

1. `NewBrdLotQty`, the exchange's own published lot, present in the UDiFF layout from
   2024-01-02. Used directly with NO estimation wherever it exists.
2. For the legacy layout (2019 to 2023-12-31), which has no lot column, the lot is derived
   from the exchange's notional turnover with the estimator below.

THE IDENTITY AND ITS BIAS. For an option row the exchange's value column is the NOTIONAL,
not premium turnover — measured, not assumed: dividing by the premium misses the published
lot by a median factor of 236, dividing by the strike lands within 0.45%. So

    implied = value / (strike x contracts)

is right in form. But the notional accumulates against the price the underlying actually
traded at, not the strike, so a row implies `lot x (underlying / strike)`. Measured against
`NewBrdLotQty` on 5,918 liquid UDiFF rows the ratio is bounded in [1.0004, 1.0210] and is
**always at least 1**.

THE ESTIMATOR FOLLOWS FROM THAT SIGN. Because the bias is strictly positive, the MINIMUM
across a contract's liquid rows is its least-biased observation; a median sits in the middle
of the bias distribution. Enough rows let the minimum approach the true floor.

    per (session, expiry): lot = round( min over rows with >= 1000 contracts of implied ),
                           accepted only when at least 20 such rows exist

VALIDATION against the exchange's own `NewBrdLotQty`, on every (session, expiry) pair where
it is published:

    MIN,    >= 20 liquid rows   2,998 pairs   100.00% exact
    MIN,    any liquid rows     5,412 pairs    92.94% exact
    MEDIAN, >= 20 liquid rows   2,998 pairs    91.63% exact
    MEDIAN, any liquid rows     5,412 pairs    70.18% exact

FIVE EARLIER ATTEMPTS FAILED. Recorded so none is tried again:
  - a MONTHLY calendar: the lot changes mid-month (2024-04-26, 2024-12-30), so the tail of
    those months was wrong by 2x and 3x.
  - a SESSION-WIDE median across all expiries: during a transition the old and new lot trade
    at once (2025-12-24: 75.01 on the near expiry, 65.05 on the next) and the median blends
    them into 66.6, which is not a lot size at all.
  - ONE ESTIMATE PER CONTRACT from its "cleanest" session, taking the observation closest to
    an integer: proximity to an integer is not evidence when the bias is multiplicative. It
    chose 93.003 over 75.26 for the expiry of 2019-09-26.
  - restricting to rows near the money: the bias survives — 75.7, 78.1, 50.8.
  - snapping to a legal lot set learned from clean observations: the learned set is itself
    polluted by bias artefacts (26, 51, 52, 54, 66, 67, 76, 77, 81, 93, 104, 107), so 50.98
    snapped to 51. 70% accurate.

"A LOT PER CONTRACT" IS ALSO WRONG. `NewBrdLotQty` itself varies over the life of one
expiry — the contract expiring 2024-05-02 reports 50 on some sessions and 25 on others,
because the change fell mid-contract. The lot is a property of (session, expiry).

Anything unresolved is ABSENT, never carried forward from a neighbouring session or expiry.
Callers must treat a missing key as UNPRICEABLE.
"""

from __future__ import annotations

import glob
import os
import sys
from datetime import date
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

IDXOPT_GLOB = "data/raw/nse/fo_idxopt/idxopt_*.parquet"
CHAIN_PANEL = "data/derived/chain_panel.parquet"
PAIR_CACHE = "data/derived/option_lot_pairs.parquet"
SESSION_CACHE = "data/derived/option_lot_sessions.parquet"

MIN_CONTRACTS = 1000.0     # per-row liquidity floor; the identity is noise below it
MIN_LIQUID_ROWS = 20       # rows needed for the minimum to approach the true floor


def implied_option_lot(value, contracts, strike) -> pd.Series:
    """
    Lot implied by an option row's NOTIONAL value. STRIKE, never premium — dividing by the
    premium is wrong by a median factor of 236.

    NaN where the inputs cannot support the division, never a fallback.
    """
    v = pd.to_numeric(value, errors="coerce")
    c = pd.to_numeric(contracts, errors="coerce")
    k = pd.to_numeric(strike, errors="coerce")
    bad = v.isna() | c.isna() | k.isna() | (c <= 0) | (k <= 0)
    return (v / (k * c)).mask(bad)


def _write_cache(out: pd.DataFrame, cache_path: str, symbol: str) -> None:
    """Replace this symbol's rows in the cache, leaving other symbols alone."""
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    keep = out.copy()
    keep["symbol"] = symbol
    prior = pd.DataFrame()
    if os.path.exists(cache_path):
        prior = pd.read_parquet(cache_path)
        prior = prior[prior["symbol"] != symbol]
    pd.concat([prior, keep], ignore_index=True).to_parquet(cache_path, index=False)


def _pairs_in_file(path: str, symbol: str,
                   min_liquid_rows: int = MIN_LIQUID_ROWS) -> List[dict]:
    """
    Every (session, expiry) lot in one bhavcopy file.

    `source` is "NewBrdLotQty" where the exchange publishes the lot and "derived-min" where
    it is estimated. An expiry with neither a published lot nor `min_liquid_rows` liquid
    rows is omitted rather than estimated from too little.
    """
    d = pd.read_parquet(path)
    if not {"TckrSymb", "StrkPric", "XpryDt", "TradDt"}.issubset(d.columns):
        return []
    d = d[d["TckrSymb"] == symbol]
    if d.empty:
        return []

    if "TtlTrfVal" in d.columns and pd.to_numeric(
            d["TtlTrfVal"], errors="coerce").notna().any():
        value, contracts, era = d["TtlTrfVal"], d["TtlTradgVol"], "UDiFF"
    elif "LegacyValInLakh" in d.columns:
        value = pd.to_numeric(d["LegacyValInLakh"], errors="coerce") * 1e5
        contracts, era = d["LegacyContracts"], "legacy"
    else:
        return []

    official = (pd.to_numeric(d["NewBrdLotQty"], errors="coerce")
                if "NewBrdLotQty" in d.columns
                else pd.Series(np.nan, index=d.index))

    g = pd.DataFrame({
        "imp": implied_option_lot(value, contracts, d["StrkPric"]),
        "c": pd.to_numeric(contracts, errors="coerce"),
        "official": official.where(official > 0),
        "xp": pd.to_datetime(d["XpryDt"], errors="coerce"),
    })
    g = g[(g["c"] >= MIN_CONTRACTS) & np.isfinite(g["imp"]) & g["xp"].notna()]
    if g.empty:
        return []

    sess = pd.Timestamp(d["TradDt"].iloc[0])
    out: List[dict] = []
    for xp, h in g.groupby("xp"):
        pub = h["official"].dropna()
        if len(pub):
            out.append({"date": sess, "expiry": pd.Timestamp(xp),
                        "lot": int(pub.median()), "source": "NewBrdLotQty",
                        "implied_min": float(h["imp"].min()),
                        "liquid_rows": int(len(h)), "era": era})
            continue
        if len(h) < min_liquid_rows:
            continue                      # too little to estimate; stays UNPRICEABLE
        out.append({"date": sess, "expiry": pd.Timestamp(xp),
                    "lot": int(round(float(h["imp"].min()))), "source": "derived-min",
                    "implied_min": float(h["imp"].min()),
                    "liquid_rows": int(len(h)), "era": era})
    return out


def pair_lot_table(symbol: str = "NIFTY", files: Optional[List[str]] = None,
                   use_cache: bool = True,
                   cache_path: str = PAIR_CACHE) -> pd.DataFrame:
    """One authentic lot per (session, expiry): published where possible, else estimated."""
    cols = ["date", "expiry", "lot", "source", "implied_min", "liquid_rows", "era"]
    if use_cache and files is None and os.path.exists(cache_path):
        c = pd.read_parquet(cache_path)
        c = c[c["symbol"] == symbol]
        if not c.empty:
            return c.drop(columns=["symbol"]).reset_index(drop=True)

    rows: List[dict] = []
    for f in sorted(files if files is not None else glob.glob(IDXOPT_GLOB)):
        rows.extend(_pairs_in_file(f, symbol))
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        out = out.sort_values(["date", "expiry"]).reset_index(drop=True)
        if use_cache and files is None:
            _write_cache(out, cache_path, symbol)
    return out


def session_lot_table(symbol: str = "NIFTY", files: Optional[List[str]] = None,
                      use_cache: bool = True,
                      cache_path: str = SESSION_CACHE) -> pd.DataFrame:
    """
    One lot per session: the lot of that session's NEAREST expiry, which is the contract an
    intraday trade actually touches and what `chain_panel` reports.
    """
    cols = ["date", "lot", "source", "expiry", "implied_min", "liquid_rows", "era",
            "n_expiries"]
    if use_cache and files is None and os.path.exists(cache_path):
        c = pd.read_parquet(cache_path)
        c = c[c["symbol"] == symbol]
        if not c.empty:
            return c.drop(columns=["symbol"]).reset_index(drop=True)

    p = pair_lot_table(symbol, files=files, use_cache=use_cache)
    if p.empty:
        return pd.DataFrame(columns=cols)
    p = p.copy()
    p["date"] = pd.to_datetime(p["date"])
    p["expiry"] = pd.to_datetime(p["expiry"])
    rows = []
    for sess, g in p.groupby("date"):
        g = g.sort_values("expiry")
        r = g.iloc[0]
        rows.append({"date": sess, "lot": int(r["lot"]), "source": r["source"],
                     "expiry": r["expiry"], "implied_min": float(r["implied_min"]),
                     "liquid_rows": int(r["liquid_rows"]), "era": r["era"],
                     "n_expiries": int(len(g))})
    out = pd.DataFrame(rows, columns=cols)
    if use_cache and files is None and not out.empty:
        _write_cache(out, cache_path, symbol)
    return out


def lot_map(symbol: str = "NIFTY", files: Optional[List[str]] = None,
            use_cache: bool = True) -> Dict[date, int]:
    """
    Session-date -> authentic lot size. A session the identity could not resolve is ABSENT;
    callers must treat a missing key as UNPRICEABLE and must never substitute a
    neighbouring session's lot.
    """
    t = session_lot_table(symbol, files=files, use_cache=use_cache)
    if t.empty:
        return {}
    return {pd.Timestamp(d).date(): int(v) for d, v in zip(t["date"], t["lot"])}


def validate_estimator(symbol: str = "NIFTY") -> pd.DataFrame:
    """
    Score the DERIVED estimator against the exchange's published lot, on every
    (session, expiry) pair where `NewBrdLotQty` exists.

    This is the only evidence that the legacy-era numbers — where no published lot exists —
    can be trusted, so it re-derives from the turnover rather than reading `lot` back.
    """
    rows = []
    for f in sorted(glob.glob(IDXOPT_GLOB)):
        d = pd.read_parquet(f)
        if "NewBrdLotQty" not in d.columns or "TckrSymb" not in d.columns:
            continue
        d = d[d["TckrSymb"] == symbol]
        if d.empty:
            continue
        g = pd.DataFrame({
            "imp": implied_option_lot(d.get("TtlTrfVal"), d.get("TtlTradgVol"),
                                      d["StrkPric"]),
            "c": pd.to_numeric(d["TtlTradgVol"], errors="coerce"),
            "official": pd.to_numeric(d["NewBrdLotQty"], errors="coerce"),
            "xp": pd.to_datetime(d["XpryDt"], errors="coerce"),
        })
        g = g[(g["c"] >= MIN_CONTRACTS) & np.isfinite(g["imp"])
              & g["official"].gt(0) & g["xp"].notna()]
        if g.empty:
            continue
        sess = pd.Timestamp(d["TradDt"].iloc[0])
        for xp, h in g.groupby("xp"):
            rows.append({"date": sess, "expiry": pd.Timestamp(xp),
                         "derived": int(round(float(h["imp"].min()))),
                         "official": int(h["official"].median()),
                         "liquid_rows": int(len(h))})
    v = pd.DataFrame(rows, columns=["date", "expiry", "derived", "official",
                                    "liquid_rows"])
    if not v.empty:
        v["agrees"] = v["derived"] == v["official"]
        v["enough_rows"] = v["liquid_rows"] >= MIN_LIQUID_ROWS
    return v


def validate_against_chain_panel(symbol: str = "NIFTY") -> pd.DataFrame:
    """Session-level cross-check against the other authentic source already held."""
    t = session_lot_table(symbol)
    if t.empty:
        return pd.DataFrame(columns=["date", "derived", "chain_panel", "source",
                                     "agrees"])
    p = pd.read_parquet(CHAIN_PANEL, columns=["date", "lot_size"])
    p["date"] = pd.to_datetime(p["date"])
    p = p.dropna(subset=["lot_size"])
    p = p[p["lot_size"] > 0]
    if p.empty:
        return pd.DataFrame(columns=["date", "derived", "chain_panel", "source",
                                     "agrees"])
    j = (t[["date", "lot", "source"]].assign(date=pd.to_datetime(t["date"]))
         .merge(p.rename(columns={"lot_size": "chain_panel"}), on="date", how="inner"))
    j["agrees"] = j["lot"].astype(int) == j["chain_panel"].round().astype(int)
    return j.rename(columns={"lot": "derived"})[
        ["date", "derived", "chain_panel", "source", "agrees"]]
