"""
Bots 5 and 6 — real-option execution and P&L model.

WHAT THIS REPLACES
------------------
Both strategies priced every trade with a FLAT premium of 100.0 and a FIXED
0.55 delta:

    opt_pnl = spot_points_moved * 0.55         # synthetic
    entry_premium = 100.0                      # synthetic

That is not option P&L. This module replaces it with AUTHENTIC ATM option prices
taken from Dhan's rolling-option feed (real strike, spot, iv, oi, OHLCV at
5-minute resolution), matching the contract both bots actually trade live:
NIFTY, ATM, weekly expiry, CE on a bullish signal and PE on a bearish one.

WHAT IS AUTHENTIC HERE
----------------------
  * option strike, expiry bucket, option type          - from the feed
  * option price at entry and at exit                  - from the feed
  * intraday spot path used to trigger entry and exit  - from the feed
  * lot size                                           - from the Scrip Master
  * costs                                              - IndianCostModel

WHAT REMAINS UNVERIFIED (stated, not hidden)
--------------------------------------------
  * NO BID/ASK HISTORY. The rolling-option feed returns OHLCV, iv and oi but not
    depth, so fills are modelled at the traded price of the 5-minute bar rather
    than at an executable bid/ask. Real fills would be worse by at least the
    half-spread. This model is therefore an APPROXIMATION and is labelled
    `execution_basis = "TRADED_PRICE_NO_BIDASK"` on every trade.
  * No slippage beyond the cost model's flat allowance.
  * No partial fills, no queue position, no market impact.
  * Expiry is the feed's "near weekly" bucket; exact expiry-date alignment per
    trade is not independently reconciled.

DESIGN RULE: exit TRIGGERS remain exactly as each strategy specifies (spot-based
ATR targets and stops, EOD flat). Only the PRICING changes from synthetic to
real. No parameter, multiple or threshold is altered.
"""

import os
import sys
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any, Dict, List, Optional

import glob
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel
from src.utils.logging import setup_logging

logger = setup_logging("research.bot56_real_options")

ATM_DIR = "data/raw/dhan/rollingoption/symbol=NIFTY/interval=5m/strike=ATM"
GRID_5M_DIR = "data/raw/dhan/option_grid_5m"
EOD_FLAT = dtime(15, 15)          # both strategies specify an intraday MIS exit
EXECUTION_BASIS = "TRADED_PRICE_NO_BIDASK"
SESSION_OPEN = dtime(9, 15)       # NSE regular session
SESSION_LAST_BAR = dtime(15, 35)  # 15:30 close; the feed stamps a final 15:35 bar


@dataclass
class RealOptionTrade:
    """One trade priced from authentic option bars."""
    date: str
    option_type: str
    strike: float
    entry_time: str
    exit_time: str
    entry_spot: float
    exit_spot: float
    entry_option_price: float
    exit_option_price: float
    lot_size: int
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str
    entry_iv: Optional[float] = None
    execution_basis: str = EXECUTION_BASIS


def load_option_grid() -> Optional[Dict[str, pd.DataFrame]]:
    """
    Builds an authentic (datetime, strike) -> price grid per option type.

    WHY A GRID AND NOT THE "ATM" SERIES: the rolling-ATM feed RE-ANCHORS as spot
    moves — a single session contains up to 9 different strikes in one "ATM"
    series. Holding a position across bars on that series silently swaps the
    contract underneath the trade, so it is a synthetic continuous index, NOT a
    tradable instrument. Stitching the ATM/ATM+-1/+-2/+-3 series instead yields a
    real per-strike price history from which one FIXED contract can be followed.

    Timestamps are recomputed from the epoch, because the cached files were
    written before the IST conversion fix and their stored `datetime` column is
    5h30m early.
    """
    out: Dict[str, pd.DataFrame] = {}
    for side in ("ce", "pe"):
        paths = glob.glob(
            f"data/raw/dhan/rollingoption/**/NIFTY_*_{side}_*.parquet", recursive=True
        )
        if not paths:
            logger.warning(f"No authentic {side.upper()} option bars cached.")
            return None
        frames = []
        for path in paths:
            df = pd.read_parquet(path)
            if "timestamp" not in df.columns:
                continue
            df["datetime"] = (
                pd.to_datetime(df["timestamp"], unit="s", utc=True)
                .dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            )
            frames.append(df[["datetime", "strike", "spot", "close", "iv", "oi"]])
        if not frames:
            return None
        grid = (pd.concat(frames)
                  .drop_duplicates(subset=["datetime", "strike"])
                  .sort_values(["datetime", "strike"])
                  .reset_index(drop=True))
        out[side] = grid
    return out



def load_option_grid_5m(directory: str = GRID_5M_DIR) -> Optional[Dict[str, pd.DataFrame]]:
    """
    The DEEP 5-minute option grid: ATM+/-6, CE and PE, from 2020-09.

    WHY THIS EXISTS: the original loader read a 10-session cache, which is why the
    first "real option economics" for these bots rested on n=8 and n=3. Re-probed
    with a valid token on 2026-09-18, `/charts/rollingoption` actually serves
    5-minute bars back to 2020-09 — about six years — one month per request, with a
    hard ATM+/-10 strike ceiling. `scripts/ingest_dhan_option_grid.py` pulls that
    ladder; this function stitches it.

    The same rolling-ATM trap applies and is the reason the whole ladder is pulled:
    the "ATM" label RE-ANCHORS as spot moves, so following it across bars silently
    swaps the contract. Stitching by REAL strike yields a per-contract history from
    which one fixed contract can be held for the life of a trade.

    Timestamps are already naive IST: the client converts from the epoch on read,
    so unlike the legacy cache no re-conversion is applied here.
    """
    root = Path(directory)
    if not root.exists():
        logger.warning(f"No deep option grid under {directory}")
        return None
    out: Dict[str, pd.DataFrame] = {}
    for side in ("ce", "pe"):
        paths = sorted(root.glob(f"strike=*/{side}_*.parquet"))
        if not paths:
            logger.warning(f"No {side.upper()} bars in the deep grid.")
            return None
        frames = []
        for path in paths:
            df = pd.read_parquet(path)
            if "datetime" not in df.columns or df.empty:
                continue
            frames.append(df[["datetime", "strike", "spot", "close", "high", "low",
                              "iv", "oi", "volume"]])
        if not frames:
            return None
        g = (pd.concat(frames)
             .drop_duplicates(subset=["datetime", "strike"])
             .sort_values(["datetime", "strike"])
             .reset_index(drop=True))

        # Restrict to the REGULAR session. The feed also carries Muhurat (Diwali)
        # trading: four sessions (2021-11-04, 2022-10-24, 2023-11-12, 2024-11-01)
        # that run ~18:00-19:15 and contain NO regular-session bars at all. Those
        # bars are authentic, but every rule in these strategies is written around a
        # 09:15 open and a 15:15 flat, so applying them to a one-hour ceremonial
        # session produces a mechanical artefact — "entry at the first bar after
        # 09:15" would pick 18:15 and "exit at the first bar after 15:15" would pick
        # 18:20, a five-minute hold that the strategy never intended.
        # This removes a session type the strategy does not trade; it does not
        # remove losing days from a session type it does.
        t = g["datetime"].dt.time
        g = g[(t >= SESSION_OPEN) & (t <= SESSION_LAST_BAR)].reset_index(drop=True)
        out[side] = g
    return out


def available_option_days(bars: Dict[str, pd.DataFrame]) -> List[Any]:
    return sorted(set(bars["ce"]["datetime"].dt.date) & set(bars["pe"]["datetime"].dt.date))


def simulate_real_option_trades(
    daily_df: pd.DataFrame,
    signals: pd.DataFrame,
    bars: Dict[str, pd.DataFrame],
    target_atr_mult: float,
    stop_atr_mult: float,
    lot_size: int,
    max_trades_per_day: Optional[int] = None,
) -> List[RealOptionTrade]:
    """
    Point-in-time intraday simulation priced on authentic option bars.

    Chronology per session:
      prev-bar ATR and breakout level are known before the open
      -> walk the 5-minute spot path forward
      -> first bar whose spot crosses the level is the ENTRY (option price of
         that same bar)
      -> continue forward until spot hits target/stop, or EOD_FLAT
      -> EXIT at that bar's option price

    No future bar is consulted: the loop only ever moves forward in time.
    """
    d = daily_df.merge(signals[["datetime", "signal"]], on="datetime", how="inner")
    d = d.sort_values("datetime").reset_index(drop=True)

    prev_c = d["close"].shift(1)
    tr = pd.concat(
        [d["high"] - d["low"], (d["high"] - prev_c).abs(), (d["low"] - prev_c).abs()], axis=1
    ).max(axis=1)
    d["atr_14"] = tr.rolling(14).mean()

    day_set = set(available_option_days(bars))

    # Index the grid by session once. The naive form filters the whole frame inside
    # the signal loop; at ~1.5M rows per side over hundreds of signal days that
    # dominates runtime and the simulation does not finish. Grouping changes nothing
    # about the data — it is the same rows, keyed for lookup.
    by_day = {
        side: {k: v for k, v in bars[side].groupby(bars[side]["datetime"].dt.date, sort=False)}
        for side in ("ce", "pe")
    }
    trades: List[RealOptionTrade] = []
    per_day: Dict[Any, int] = {}

    for i in range(1, len(d)):
        row, prev = d.iloc[i], d.iloc[i - 1]
        sig = int(row["signal"])
        if sig == 0:
            continue
        sess = row["datetime"].date()
        if sess not in day_set:
            continue                                   # no authentic option data
        atr = prev["atr_14"]                           # prev-bar ATR: known at entry
        if not np.isfinite(atr) or atr <= 0:
            continue
        if max_trades_per_day is not None and per_day.get(sess, 0) >= max_trades_per_day:
            continue

        is_ce = sig == 1
        side = "ce" if is_ce else "pe"
        level = prev["high"] if is_ce else prev["low"]

        day_grid = by_day[side].get(sess)
        if day_grid is None or day_grid.empty:
            continue

        # Spot path for the session (one row per timestamp; spot is common to all strikes).
        spot_path = (day_grid.groupby("datetime")["spot"].first()
                     .sort_index().reset_index())

        target_pts = target_atr_mult * atr
        stop_pts = stop_atr_mult * atr

        # ---- ENTRY: first bar whose spot crosses the prior-bar breakout level ----
        entry_row = None
        for _, b in spot_path.iterrows():
            if (b["spot"] > level) if is_ce else (b["spot"] < level):
                entry_row = b
                break
        if entry_row is None:
            continue                                   # breakout never triggered

        entry_ts, entry_spot = entry_row["datetime"], float(entry_row["spot"])

        # ---- CONTRACT: fix the ATM strike AT ENTRY and hold THAT contract ----
        at_entry = day_grid[day_grid["datetime"] == entry_ts]
        if at_entry.empty:
            continue
        chosen = at_entry.iloc[(at_entry["strike"] - entry_spot).abs().argsort()].iloc[0]
        strike = float(chosen["strike"])
        entry_price = float(chosen["close"])
        if entry_price <= 0:
            continue

        # Authentic series for that ONE contract, from entry onward.
        leg = (day_grid[(day_grid["strike"] == strike) & (day_grid["datetime"] >= entry_ts)]
               .sort_values("datetime").reset_index(drop=True))
        if len(leg) < 2:
            # The chosen contract is not continuously quoted in the cached grid.
            # Fail closed rather than substituting a different strike mid-trade.
            continue

        # ---- EXIT: spot-based target/stop (as specified) or the MIS flat time ----
        exit_row, reason = leg.iloc[-1], "EOD"
        for k in range(1, len(leg)):
            b = leg.iloc[k]
            move = (b["spot"] - entry_spot) if is_ce else (entry_spot - b["spot"])
            if move <= -stop_pts:
                exit_row, reason = b, "STOP"
                break
            if move >= target_pts:
                exit_row, reason = b, "TARGET"
                break
            if b["datetime"].time() >= EOD_FLAT:
                exit_row, reason = b, "EOD"
                break

        exit_price = float(exit_row["close"])
        gross = (exit_price - entry_price) * lot_size      # long option in both directions
        costs = IndianCostModel.calculate_roundtrip_costs(entry_price, exit_price, lot_size).total_costs

        per_day[sess] = per_day.get(sess, 0) + 1
        trades.append(RealOptionTrade(
            date=str(sess), option_type="CE" if is_ce else "PE", strike=strike,
            entry_time=str(entry_ts.time()), exit_time=str(exit_row["datetime"].time()),
            entry_spot=entry_spot, exit_spot=float(exit_row["spot"]),
            entry_option_price=entry_price, exit_option_price=exit_price,
            lot_size=lot_size, gross_pnl=round(gross, 2), costs=round(costs, 2),
            net_pnl=round(gross - costs, 2), exit_reason=reason,
            entry_iv=float(chosen["iv"]) if pd.notna(chosen.get("iv")) else None,
        ))
    return trades


def summarise_real(trades: List[RealOptionTrade], initial_capital: float = 10000.0) -> Dict[str, Any]:
    """Comparison metrics. Returns an explicit empty summary rather than zeros-as-success."""
    if not trades:
        return {"total_trades": 0, "net_profit": 0.0, "win_rate": 0.0,
                "gross_profit": 0.0, "total_costs": 0.0, "max_drawdown_pct": 0.0,
                "execution_basis": EXECUTION_BASIS, "note": "no trades in the covered window"}
    df = pd.DataFrame([t.__dict__ for t in trades])
    eq = initial_capital + df["net_pnl"].cumsum()
    dd = ((eq - eq.cummax()) / eq.cummax()).min()
    return {
        "total_trades": int(len(df)),
        "net_profit": float(df["net_pnl"].sum()),
        "gross_profit": float(df["gross_pnl"].sum()),
        "total_costs": float(df["costs"].sum()),
        "win_rate": float((df["net_pnl"] > 0).mean() * 100.0),
        "max_drawdown_pct": float(abs(dd) * 100.0) if pd.notna(dd) else 0.0,
        "avg_entry_price": float(df["entry_option_price"].mean()),
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
        "execution_basis": EXECUTION_BASIS,
    }
