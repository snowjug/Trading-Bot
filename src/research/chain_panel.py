"""
CHAIN PANEL — daily point-in-time state of the NIFTY option chain.

WHY THIS EXISTS. Every study in this repository so far has fed its signals from
the spot path, daily OHLC and India VIX. The option chain itself — open interest,
the change in open interest, traded option volume, and the ATM straddle — has
never been used, even though the brief names PCR, OI and IV explicitly. The
consolidated F&O bhavcopy carries `OpnIntrst`, `ChngInOpnIntrst` and
`TtlTradgVol` for **every** NIFTY strike and expiry on all 1,904 sessions from
2019-01 to 2026-09, at 100% coverage. This module turns that into one row per
session.

CAUSALITY. Every column on row t is computed from the bhavcopy published for
session t, which is end-of-day data for session t. A signal may therefore use row
t to decide a trade entered at the CLOSE of t or later — never earlier. The
forward-return columns (`fwd_*`) are targets for measurement only; no signal
function is permitted to read them, and `feature_columns()` excludes them.

SPOT. `UndrlygPric` is populated on only 27.4% of rows, so spot comes from the
index history parquet (NIFTY50 daily close), which was independently cross-checked
against the repository's own index files to 0.0008 points over 422 overlapping
sessions.

LOT SIZE. `NewBrdLotQty` is only present from 2024 onward. It is carried through
as-is and is NEVER back-filled or guessed; anything that needs rupees before 2024
must say so and stop. Points-based measurement has no such limit.
"""

from __future__ import annotations

import os
import sys
from typing import List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

BHAV = "data/raw/nse/fo_bhavcopy/.consolidated_1904_1789736982937725100.parquet"
INDEX = "data/raw/nse/index_history/nse_index_daily.parquet"
PANEL_CACHE = "data/derived/chain_panel.parquet"

STRIKE_STEP = 50.0
BAND_PCT = 0.05          # strikes within +-5% of spot count as "near the money"


def _load_bhav() -> pd.DataFrame:
    d = pd.read_parquet(BHAV, columns=[
        "TradDt", "XpryDt", "StrkPric", "OptnTp", "ClsPric", "SttlmPric",
        "OpnIntrst", "ChngInOpnIntrst", "TtlTradgVol", "NewBrdLotQty",
    ])
    d["TradDt"] = pd.to_datetime(d["TradDt"])
    d["XpryDt"] = pd.to_datetime(d["XpryDt"])
    return d


def _index_daily() -> pd.DataFrame:
    raw = pd.read_parquet(INDEX)
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="left").sort_values("datetime").reset_index(drop=True)
    return d


def _max_pain(strikes: np.ndarray, ce_oi: np.ndarray, pe_oi: np.ndarray) -> float:
    """
    Strike at which the total intrinsic value owed to option holders is smallest.
    Computed by cumulative sums rather than a double loop: for a settlement at
    K_j, calls pay sum_{k<j} OI_k (K_j - K_k) and puts pay sum_{k>j} OI_k (K_k - K_j).
    """
    if len(strikes) < 3:
        return float("nan")
    o = np.argsort(strikes)
    k, c, p = strikes[o], ce_oi[o], pe_oi[o]
    c_oi = np.cumsum(c)
    c_koi = np.cumsum(c * k)
    call_pay = c_oi * k - c_koi                       # inclusive of j, term j is zero
    p_oi = np.cumsum(p[::-1])[::-1]
    p_koi = np.cumsum((p * k)[::-1])[::-1]
    put_pay = p_koi - p_oi * k
    return float(k[np.argmin(call_pay + put_pay)])


def build_panel(verbose: bool = True) -> pd.DataFrame:
    bh = _load_bhav()
    idx = _index_daily()
    spot_map = dict(zip(idx["datetime"], idx["close"]))

    bh["spot"] = bh["TradDt"].map(spot_map)
    bh = bh[bh["spot"].notna()].copy()
    bh["dte"] = (bh["XpryDt"] - bh["TradDt"]).dt.days

    # nearest non-expired expiry per session (dte >= 0), and the one after it
    ex = (bh[bh["dte"] >= 0].groupby(["TradDt", "XpryDt"])["dte"].first()
          .reset_index().sort_values(["TradDt", "dte"]))
    near = ex.groupby("TradDt").nth(0).set_index("TradDt")["XpryDt"]
    nxt = ex.groupby("TradDt").nth(1).set_index("TradDt")["XpryDt"]

    bh["near_x"] = bh["TradDt"].map(near)
    rows: List[dict] = []
    nearset = bh[bh["XpryDt"] == bh["near_x"]]

    for dt, g in nearset.groupby("TradDt", sort=True):
        spot = float(g["spot"].iloc[0])
        atm = round(spot / STRIKE_STEP) * STRIKE_STEP
        band = g[(g["StrkPric"] >= spot * (1 - BAND_PCT)) &
                 (g["StrkPric"] <= spot * (1 + BAND_PCT))]
        ce, pe = g[g["OptnTp"] == "CE"], g[g["OptnTp"] == "PE"]
        bce, bpe = band[band["OptnTp"] == "CE"], band[band["OptnTp"] == "PE"]

        ce_oi, pe_oi = float(ce["OpnIntrst"].sum()), float(pe["OpnIntrst"].sum())
        bce_oi, bpe_oi = float(bce["OpnIntrst"].sum()), float(bpe["OpnIntrst"].sum())
        ce_v, pe_v = float(ce["TtlTradgVol"].sum()), float(pe["TtlTradgVol"].sum())
        ce_d, pe_d = float(ce["ChngInOpnIntrst"].sum()), float(pe["ChngInOpnIntrst"].sum())

        # ATM straddle. On a NON-expiry session ClsPric equals SttlmPric for any
        # strike that traded, and SttlmPric is the better number for one that did
        # not (2026-09-16 26050PE: close 1794.15 stale, settlement 2807.06). On an
        # EXPIRY session the bhavcopy writes the UNDERLYING's final settlement
        # value into SttlmPric for every contract — 23118.6 on every row of
        # 2026-09-15 — so only ClsPric may be used there. Reading SttlmPric on
        # expiry day priced the ATM straddle at 2x spot; that is what this guard
        # exists to prevent.
        is_expiry = int(g["dte"].iloc[0]) == 0

        def _at(side: str, k: float) -> float:
            r = g[(g["OptnTp"] == side) & (g["StrkPric"] == k)]
            if r.empty:
                return float("nan")
            row = r.iloc[0]
            cls = float(row["ClsPric"])
            if is_expiry:
                return cls
            if float(row["TtlTradgVol"]) > 0 and cls > 0:
                return cls
            s = float(row["SttlmPric"])
            return s if s > 0 else cls

        c_atm, p_atm = _at("CE", atm), _at("PE", atm)
        # On expiry sessions SttlmPric is the underlying's final settlement value.
        # Captured here because it is the only authentic expiry print available.
        settle = float(g["SttlmPric"].mode().iloc[0]) if is_expiry and len(g) else np.nan

        # OI walls, restricted to the band so a stale far strike cannot win
        ce_wall = float(bce.loc[bce["OpnIntrst"].idxmax(), "StrkPric"]) if len(bce) else np.nan
        pe_wall = float(bpe.loc[bpe["OpnIntrst"].idxmax(), "StrkPric"]) if len(bpe) else np.nan

        merged = (g.pivot_table(index="StrkPric", columns="OptnTp",
                                values="OpnIntrst", aggfunc="sum")
                  .reindex(columns=["CE", "PE"]).fillna(0.0))
        mp = _max_pain(merged.index.to_numpy(float),
                       merged["CE"].to_numpy(float), merged["PE"].to_numpy(float))

        lot = g["NewBrdLotQty"].dropna()
        rows.append({
            "date": dt, "spot": spot, "atm": atm,
            "near_expiry": g["XpryDt"].iloc[0], "dte": int(g["dte"].iloc[0]),
            "next_expiry": nxt.get(dt, pd.NaT),
            "ce_oi": ce_oi, "pe_oi": pe_oi,
            "pcr_oi": pe_oi / ce_oi if ce_oi > 0 else np.nan,
            "pcr_oi_band": bpe_oi / bce_oi if bce_oi > 0 else np.nan,
            "pcr_vol": pe_v / ce_v if ce_v > 0 else np.nan,
            "ce_doi": ce_d, "pe_doi": pe_d,
            "doi_ratio": pe_d / abs(ce_d) if abs(ce_d) > 0 else np.nan,
            "ce_vol": ce_v, "pe_vol": pe_v,
            "atm_call": c_atm, "atm_put": p_atm,
            "straddle": c_atm + p_atm,
            "straddle_pct": (c_atm + p_atm) / spot * 100,
            "ce_wall": ce_wall, "pe_wall": pe_wall,
            "ce_wall_gap": (ce_wall - spot) / spot * 100,
            "pe_wall_gap": (pe_wall - spot) / spot * 100,
            "max_pain": mp, "max_pain_gap": (mp - spot) / spot * 100,
            "expiry_settle": settle,
            "lot_size": float(lot.mode().iloc[0]) if len(lot) else np.nan,
            "n_strikes": int(g["StrkPric"].nunique()),
        })

    p = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    p = p.merge(idx.rename(columns={"datetime": "date"}), on="date", how="left")

    # ── index-derived state, all trailing ──
    c = p["close"]
    p["ret"] = c.pct_change() * 100
    p["gap"] = (p["open"] - c.shift(1)) / c.shift(1) * 100
    p["oc"] = (p["close"] - p["open"]) / p["open"] * 100
    prev = c.shift(1)
    tr = pd.concat([p["high"] - p["low"], (p["high"] - prev).abs(),
                    (p["low"] - prev).abs()], axis=1).max(axis=1)
    p["atr14"] = tr.rolling(14).mean()
    p["rv10"] = p["ret"].rolling(10).std() * np.sqrt(252)
    p["rv20"] = p["ret"].rolling(20).std() * np.sqrt(252)
    p["vrp"] = p["vix"] - p["rv20"]
    p["vix_pct250"] = p["vix"].rolling(250).rank(pct=True) * 100
    p["straddle_pct_ma20"] = p["straddle_pct"].rolling(20).mean()
    p["ema9"] = c.ewm(span=9, adjust=False).mean()
    p["ema21"] = c.ewm(span=21, adjust=False).mean()
    p["ema50"] = c.ewm(span=50, adjust=False).mean()
    p["ema200"] = c.ewm(span=200, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    p["rsi14"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    p["dist_ema21"] = (c - p["ema21"]) / p["ema21"] * 100
    p["dist_ema50"] = (c - p["ema50"]) / p["ema50"] * 100
    p["mom5"] = c.pct_change(5) * 100
    p["mom10"] = c.pct_change(10) * 100
    p["mom20"] = c.pct_change(20) * 100
    p["hi20"] = p["high"].rolling(20).max()
    p["lo20"] = p["low"].rolling(20).min()
    p["range_pct"] = (p["high"] - p["low"]) / c * 100
    p["range20"] = p["range_pct"].rolling(20).mean()
    p["dow"] = p["date"].dt.dayofweek

    # percentile ranks of chain state, trailing window only
    for col in ("pcr_oi", "pcr_oi_band", "pcr_vol", "straddle_pct", "vrp"):
        p[f"{col}_z"] = ((p[col] - p[col].rolling(250).mean())
                         / p[col].rolling(250).std())
        p[f"{col}_pct"] = p[col].rolling(250).rank(pct=True) * 100
    for col in ("pcr_oi", "pcr_oi_band", "pcr_vol", "straddle_pct"):
        p[f"d_{col}"] = p[col].diff()

    # ── forward returns: TARGETS, never inputs ──
    p["fwd_cc1"] = c.shift(-1) / c - 1                       # close -> next close
    p["fwd_co1"] = p["open"].shift(-1) / c - 1               # close -> next open
    p["fwd_oc1"] = p["close"].shift(-1) / p["open"].shift(-1) - 1
    p["fwd_cc3"] = c.shift(-3) / c - 1
    p["fwd_cc5"] = c.shift(-5) / c - 1
    p["fwd_hi5"] = p["high"].shift(-5).rolling(5).max().shift(-0) / c - 1
    p["fwd_absret1"] = (c.shift(-1) / c - 1).abs()
    return p


def feature_columns(p: pd.DataFrame) -> List[str]:
    """Everything a signal is allowed to read. Forward columns are excluded here."""
    drop = {"date", "near_expiry", "next_expiry"}
    return [c for c in p.columns if not c.startswith("fwd_") and c not in drop]


def load_panel(rebuild: bool = False) -> pd.DataFrame:
    if not rebuild and os.path.exists(PANEL_CACHE):
        return pd.read_parquet(PANEL_CACHE)
    p = build_panel()
    os.makedirs(os.path.dirname(PANEL_CACHE), exist_ok=True)
    p.to_parquet(PANEL_CACHE, index=False)
    return p


if __name__ == "__main__":
    p = build_panel()
    os.makedirs(os.path.dirname(PANEL_CACHE), exist_ok=True)
    p.to_parquet(PANEL_CACHE, index=False)
    print(f"panel {p.shape}  {p['date'].min().date()} -> {p['date'].max().date()}")
    print(p[["date", "spot", "dte", "pcr_oi", "pcr_oi_band", "pcr_vol", "straddle_pct",
             "max_pain_gap", "ce_wall_gap", "pe_wall_gap", "lot_size"]].tail(8).to_string())
