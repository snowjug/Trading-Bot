"""
FUTURES PANEL — near-month index futures from the authentic NSE bhavcopy.

WHY THIS EXISTS. Three studies in this repository recorded that no futures prices
were available and closed by naming futures as the missing instrument that would
make the measured overnight drift tradable. The prices were always in the same file
the option store came from; they were discarded by an intake filter. This module
reads them.

ROLL RULE, stated because a continuous futures series is a construction and not a
fact. For each session the NEAR-MONTH contract is the listed contract with the
smallest expiry that has not yet passed (`XpryDt >= TradDt`). A pair of consecutive
sessions is used only when BOTH sessions resolve to the SAME expiry; the session on
which the near month changes is excluded and counted. Nothing is spliced, and no
synthetic continuous price is ever created — every number traces to one contract's
own print.

WHAT IS AUTHENTIC HERE
  OpnPric / ClsPric / SttlmPric / OpnIntrst    exchange prints, per contract
  TtlTradgVol                                  CONTRACTS in both eras (verified by
                                               the turnover identity; see below)
  NewBrdLotQty                                 published from 2024 only
  derived lot size                             TtlTrfVal / (ClsPric x TtlTradgVol),
                                               which recovers the published value to
                                               within 1% on 97.9% of 8,884 UDiFF
                                               rows, so it is a derivation from
                                               exchange turnover rather than a guess

WHAT IS NOT AUTHENTIC AND IS NEVER MANUFACTURED HERE
  intraday futures prices      Dhan serves them only for CURRENTLY LISTED contracts
                               and only in ~90-day windows; expired contract ids are
                               not in the scrip master, so a long intraday futures
                               history cannot be built. It is UNTESTABLE, not absent.
  a spot-derived futures proxy  forbidden. index + basis is used only as a DIAGNOSTIC
                               decomposition, never as an execution price.

THE FINDING THIS MODULE WAS BUILT TO TEST, and its answer. The index's close-to-open
gap is NOT the futures' close-to-open gap, because the futures premium builds through
the session and collapses at the open:

    NIFTY, 1,808 same-contract pairs 2019-2026
      INDEX   close -> next open    +16.68 pts
      FUTURES close -> next open     +2.25 pts
      shortfall                     -14.42 pts
      genuine carry decay (1 day, 6%/yr)  only -2.99 pts
      basis at close +39.38 -> basis at open +29.63

About 86% of the index's overnight gap is basis being reset, which a futures holder
never receives. The basis-by-DTE profile is clean carry (11.0 pts at <=3 DTE rising
to 85.3 at 30-60 DTE), which is what validates the decomposition.
"""

from __future__ import annotations

import glob
import os
import sys
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

FUT_GLOB = "data/raw/nse/fo_futures/fut_*.parquet"
CACHE = "data/derived/futidx_all.parquet"
INDEX = "data/raw/nse/index_history/nse_index_daily.parquet"

INDEX_SYMBOL = {"NIFTY": "NIFTY50"}          # bhavcopy symbol -> index-history symbol

# Statutory friction on an INDEX FUTURES round trip, as fractions of notional unless
# stated. STT on futures is levied on the SELL side only and was raised to 0.02% in
# October 2024; the earlier rate was 0.0125%. Both are carried so a historical trade
# is charged the rate that applied to it.
STT_SELL_FUT = {"pre_2024_10": 0.000125, "post_2024_10": 0.0002}
EXCH_TXN_FUT = 0.0000173        # NSE futures transaction charge, per side
SEBI_RATE = 0.000001            # per side
STAMP_BUY_FUT = 0.00002         # buy side only
GST_RATE = 0.18                 # on brokerage + exchange + SEBI
BROKERAGE_PER_ORDER = 20.0      # rupees, flat
FUT_TICK = 0.05


def load_futures(rebuild: bool = False) -> pd.DataFrame:
    if not rebuild and os.path.exists(CACHE):
        d = pd.read_parquet(CACHE)
    else:
        fs = sorted(glob.glob(FUT_GLOB))
        if not fs:
            raise SystemExit(f"no futures files at {FUT_GLOB} — run "
                             f"scripts/ingest_nse_fo_full.py first")
        d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
        if "InstrmClass" not in d.columns:
            raise SystemExit("futures files predate the unified InstrmClass column — "
                             "delete them and re-run the ingester")
        d = d[d["InstrmClass"] == "FUTIDX"].copy()
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        d.to_parquet(CACHE, index=False)
    d["TradDt"] = pd.to_datetime(d["TradDt"])
    d["XpryDt"] = pd.to_datetime(d["XpryDt"])
    return d


def near_month(d: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """One row per session: the nearest unexpired listed contract."""
    g = d[(d["TckrSymb"] == symbol) & (d["XpryDt"] >= d["TradDt"])]
    g = g.sort_values(["TradDt", "XpryDt"])
    n = g.groupby("TradDt").first().reset_index()
    n = n[(n["ClsPric"] > 0) & (n["OpnPric"] > 0)]
    return n.sort_values("TradDt").reset_index(drop=True)


def derived_lot(row: pd.Series) -> float:
    """
    Lot size from the exchange's own turnover, usable in BOTH eras.
    Returns NaN rather than a guess when the inputs are absent.
    """
    if pd.notna(row.get("NewBrdLotQty")) and float(row.get("NewBrdLotQty") or 0) > 0:
        return float(row["NewBrdLotQty"])
    turn = row.get("TtlTrfVal")
    vol = row.get("TtlTradgVol")
    if pd.isna(turn) or pd.isna(vol):
        turn, vol = row.get("LegacyValInLakh"), row.get("LegacyContracts")
        if pd.isna(turn) or pd.isna(vol) or float(vol) <= 0:
            return float("nan")
        turn = float(turn) * 1e5
    if float(vol) <= 0 or float(row["ClsPric"]) <= 0:
        return float("nan")
    return float(turn) / (float(row["ClsPric"]) * float(vol))


def lot_calendar(d: pd.DataFrame, symbol: str, min_contracts: float = 1000.0
                 ) -> pd.DataFrame:
    """
    Authentic lot size per (symbol, month), derived from turnover on LIQUID contracts
    and rounded to an integer. Illiquid contracts are excluded because the identity
    is noisy when the denominator is tiny.
    """
    g = d[d["TckrSymb"] == symbol].copy()
    vol = g["TtlTradgVol"].fillna(g.get("LegacyContracts"))
    g = g[(vol > min_contracts) & (g["ClsPric"] > 0)]
    if g.empty:
        return pd.DataFrame(columns=["month", "lot", "n"])
    g["implied"] = g.apply(derived_lot, axis=1)
    g = g[np.isfinite(g["implied"])]
    g["month"] = g["TradDt"].dt.to_period("M")
    out = (g.groupby("month")["implied"]
           .agg(lot=lambda s: float(np.round(s.median())), n="size")
           .reset_index())
    return out


def overnight_pairs(d: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    close(t) -> open(t+1) on the SAME contract, plus the same session's open -> close.
    Roll sessions are excluded and the count is returned in `attrs["rolls_excluded"]`.
    """
    n = near_month(d, symbol)
    n["next_open"] = n["OpnPric"].shift(-1)
    n["next_xp"] = n["XpryDt"].shift(-1)
    n["next_sess"] = n["TradDt"].shift(-1)
    ok = n[(n["next_xp"] == n["XpryDt"]) & n["next_open"].notna()].copy()
    ok["on_pts"] = ok["next_open"] - ok["ClsPric"]
    ok["on_pct"] = ok["on_pts"] / ok["ClsPric"] * 100
    ok["id_pts"] = ok["ClsPric"] - ok["OpnPric"]
    ok["id_pct"] = ok["id_pts"] / ok["OpnPric"] * 100
    ok["dte"] = (ok["XpryDt"] - ok["TradDt"]).dt.days
    ok["lot"] = ok.apply(derived_lot, axis=1)
    ok.attrs["rolls_excluded"] = int(len(n) - len(ok))
    return ok.reset_index(drop=True)


def basis_frame(d: pd.DataFrame, symbol: str = "NIFTY") -> pd.DataFrame:
    """
    Futures minus index, at the close and at the open. DIAGNOSTIC ONLY — this is how
    the overnight gap is decomposed, never how a price is manufactured.
    """
    isym = INDEX_SYMBOL.get(symbol)
    if isym is None:
        raise ValueError(f"no index history mapped for {symbol}")
    raw = pd.read_parquet(INDEX)
    ix = (raw[raw["symbol"] == isym][["datetime", "open", "close"]]
          .rename(columns={"datetime": "TradDt", "open": "idx_open",
                           "close": "idx_close"}))
    ok = overnight_pairs(d, symbol).merge(ix, on="TradDt", how="inner")
    ok["next_idx_open"] = ok["idx_open"].shift(-1)
    ok = ok[ok["next_idx_open"].notna()].copy()
    ok["basis_close"] = ok["ClsPric"] - ok["idx_close"]
    ok["basis_open"] = ok["OpnPric"] - ok["idx_open"]
    ok["idx_on_pts"] = ok["next_idx_open"] - ok["idx_close"]
    ok["basis_change"] = ok["basis_open"].shift(-1) - ok["basis_close"]
    return ok


def futures_roundtrip_cost_points(price: float, lot: float,
                                  when: Optional[date] = None,
                                  slip_ticks: float = 2.0,
                                  mult: float = 1.0) -> float:
    """
    Round-trip friction in INDEX POINTS per unit, for one lot.

    STT dominates and is charged on the sell side of notional, so it converts to
    `rate x price` points directly. Brokerage is per ORDER, so it shrinks per point as
    the lot grows — which is why it is divided by the lot rather than assumed away.
    """
    rate = STT_SELL_FUT["post_2024_10"]
    if when is not None and when < date(2024, 10, 1):
        rate = STT_SELL_FUT["pre_2024_10"]
    stt = rate * price
    exch = EXCH_TXN_FUT * price * 2
    sebi = SEBI_RATE * price * 2
    stamp = STAMP_BUY_FUT * price
    brok = BROKERAGE_PER_ORDER * 2 / max(lot, 1.0)
    gst = GST_RATE * (brok + exch + sebi)
    slip = slip_ticks * FUT_TICK * 2
    return (stt + exch + sebi + stamp + brok + gst + slip) * mult


def tstat(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")
