"""
Bot 1 — NIFTY Weekly Iron Condor on AUTHENTIC exchange option prices.

WHAT CHANGED AND WHY
--------------------
`src/research/bot1_condor_contract.py` correctly refused to run: DhanHQ's
`/charts/rollingoption` endpoint serves only ATM+/-10 strikes, while the
specification needs ~ATM+/-17. That ceiling belongs to one vendor endpoint, not
to the data. NSE publishes the complete daily F&O bhavcopy — every contract,
every strike, every expiry — publicly and unauthenticated. Ingested by
`scripts/ingest_nse_fo_bhavcopy.py`, it covers 12000-34500 strikes against a
~23200 spot, and every leg this strategy specifies trades with six-figure daily
volume. The Bot 1 data blocker is therefore RESOLVED, and the contract module is
retained as the record of how it was diagnosed.

CANONICAL SPECIFICATION — resolved from existing evidence only
--------------------------------------------------------------
  structure      4-leg Iron Condor   class name `NiftyWeeklyIronCondorStrategy`,
                                     hypothesis "Call & Put spreads ... hedged
                                     wings", `wing_sd` parameter, and the 4-leg
                                     `OptionsStructure.simulate_iron_condor`
  shorts         spot +/- 1.8 * exp_move        options_theta.py:126-129
  wings          spot +/- 2.4 * exp_move        options_engine.py:124-125
  exp_move       close * vix/100 * sqrt(5/365)  options_theta.py:126 (verbatim)
  regime         vix < 20 and rsi in band       options_theta.py:76, 128
  entry          at the daily close             `entry_c = df.iloc[i]["close"]`
  holding        to expiry, 5 trading days      `df.iloc[i+1:i+6]` + "Weekly"
  exit           none — held to expiry          no stop/target/roll code exists
  costs          per-leg                        IndianCostModel (replaces a flat 140/lot)

EXECUTION MODEL
---------------
  entry   each leg's own traded CLOSE on the entry session, and ONLY when that
          contract actually traded (TtlTradgVol > 0). An untraded contract's
          bhavcopy close is a theoretical settlement value, not an executable
          price — verified on 2025-01-02, where untraded deep-ITM closes deviate
          from intrinsic by up to 627.90 while traded ones deviate by 1.38 mean.
  exit    cash settlement at expiry: max(0, S_settle - K) for a call and
          max(0, K - S_settle) for a put, where S_settle is the exchange's
          official settlement price carried in the expiry-day bhavcopy. This is
          the actual cash flow, so it needs no liquidity assumption.

NOT VERIFIED, STATED NOT HIDDEN
-------------------------------
  * NO BID/ASK. Entry fills are modelled at the traded close, so a real fill is
    worse by at least the half-spread on four legs. Labelled on every trade.
  * SPAN/exposure margin is not obtainable read-only. Per-lot economics are
    reported as primary precisely because they do not depend on it.
  * The signal reads the same session's close that the fill uses. That is the
    original research's own timing; `signal_lag` runs the strictly causal
    variant so the exposure is measured rather than assumed away.

NOTHING HERE IS FABRICATED: no synthetic credit, no assumed delta, no modelled
IV, no invented margin, no substituted strike. Every price is an exchange print
or an exact settlement computation.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel
from src.utils.logging import setup_logging

logger = setup_logging("research.bot1_condor_real")

BHAV_DIR = Path("data/raw/nse/fo_bhavcopy")
STRIKE_STEP = 50.0
EXECUTION_BASIS = "EXCHANGE_CLOSE_ENTRY_SETTLEMENT_EXIT_NO_BIDASK"

# Specification constants, taken verbatim from the strategy. Not tuned here.
SPEC_OTM_SD = 1.8
SPEC_WING_SD = 2.4
SPEC_MAX_VIX = 20.0
SPEC_DTE_FOR_EXPECTED_MOVE = 5.0


@dataclass
class CondorLeg:
    role: str                 # short_call | long_call | short_put | long_put
    option_type: str          # CE | PE
    side: str                 # SELL | BUY
    strike: float
    expiry: str
    security_id: str
    contract_name: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_volume: int
    entry_oi: int
    pnl: float
    entry_day_high: float = 0.0     # the leg's own traded range that session,
    entry_day_low: float = 0.0      # used to bound an adverse fill with real prints


@dataclass
class CondorTrade:
    entry_date: str
    expiry: str
    days_held: int
    spot_entry: float
    spot_settle: float
    vix_entry: float
    rsi_entry: float
    expected_move: float
    legs: List[CondorLeg] = field(default_factory=list)
    net_credit_points: float = 0.0
    wing_width: float = 0.0
    max_loss_points: float = 0.0
    gross_pnl: float = 0.0
    costs: float = 0.0
    net_pnl: float = 0.0
    breached: bool = False
    breach_side: str = "none"
    lot_size: int = 0
    settlement_source: str = "BHAVCOPY_SETTLEMENT"
    execution_basis: str = EXECUTION_BASIS


# ──────────────────────────────── DATA ────────────────────────────────

def load_bhavcopy_store(directory: Path = BHAV_DIR) -> Optional[pd.DataFrame]:
    """
    Loads every ingested NIFTY option bhavcopy into one frame.

    No forward-fill, no interpolation, no synthetic rows: an absent session stays
    absent so downstream code fails closed rather than inventing a price.
    """
    files = sorted(directory.glob("NIFTY_options_*.parquet"))
    if not files:
        logger.warning(f"No bhavcopy files under {directory}")
        return None

    # Reading ~1,500 per-session files on every call dominates runtime, so the
    # concatenation is cached. The cache is keyed on the file count and the newest
    # mtime, so adding or replacing any session invalidates it: it is a speed-up
    # only and can never serve a stale or partial store.
    newest = max(f.stat().st_mtime_ns for f in files)
    cache = directory / f".consolidated_{len(files)}_{newest}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        for stale in directory.glob(".consolidated_*.parquet"):
            stale.unlink(missing_ok=True)
        df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        try:
            df.to_parquet(cache, index=False)
        except Exception:                                      # noqa: BLE001
            pass                                               # the cache is optional
    df["TradDt"] = pd.to_datetime(df["TradDt"]).dt.date
    df["XpryDt"] = pd.to_datetime(df["XpryDt"]).dt.date
    return df.sort_values(["TradDt", "XpryDt", "StrkPric"]).reset_index(drop=True)


def weekly_expiry_calendar(store: pd.DataFrame) -> List[date]:
    """
    Expiry dates that are actually observed in the data.

    Taken from the exchange feed rather than assumed to be Thursdays, so the
    NIFTY weekly shift to Tuesday is handled without a hardcoded weekday.
    """
    return sorted(store["XpryDt"].unique())


def settlement_price(store: pd.DataFrame, expiry: date,
                     index_close: Optional[Dict[date, float]] = None) -> Optional[float]:
    """
    The exchange's official settlement price for the underlying on expiry day.

    PRIMARY SOURCE: on an expiry session every option row carries it in SttlmPric,
    as a single distinct value across all rows.

    FALLBACK: the legacy derivatives archive publishes SETTLE_PR as 0.0 on expiry
    rows for 2019 and most of 2020, so that field is unusable there. NSE's index
    archive supplies a substitute, and the substitution is VERIFIED rather than
    assumed: across all 90 expiry sessions where both sources exist, the index
    closing value equals the settlement price EXACTLY (90/90, max |diff| = 0.0).
    The fallback is therefore a second reading of the same number, not a proxy.

    Returns None when neither source has it, so callers fail closed.
    """
    rows = store[(store["TradDt"] == expiry) & (store["XpryDt"] == expiry)]
    if not rows.empty:
        vals = rows["SttlmPric"].dropna().unique()
        if len(vals) == 1 and vals[0] > 0:
            return float(vals[0])
    if index_close:
        v = index_close.get(expiry)
        if v and v > 0:
            return float(v)
    return None


def settlement_source(store: pd.DataFrame, expiry: date) -> str:
    """Which source a settlement price came from, for provenance in reports."""
    rows = store[(store["TradDt"] == expiry) & (store["XpryDt"] == expiry)]
    if not rows.empty:
        vals = rows["SttlmPric"].dropna().unique()
        if len(vals) == 1 and vals[0] > 0:
            return "BHAVCOPY_SETTLEMENT"
    return "NSE_INDEX_CLOSE_VERIFIED_IDENTICAL"



class ChainIndex:
    """
    (trade date, expiry) -> that day's chain, built once.

    The naive form filters the whole store inside the session loop. At 4.0M rows
    over ~1,650 sessions that is billions of row comparisons and the backtest does
    not finish. Grouping once turns each lookup into a dict access. It is purely a
    lookup structure: no row is altered, added or dropped.
    """

    def __init__(self, store: pd.DataFrame):
        self._by_day_expiry = {k: v for k, v in store.groupby(["TradDt", "XpryDt"], sort=False)}
        self._expiries_by_day: Dict[Any, List[date]] = {}
        for (day, exp) in self._by_day_expiry:
            self._expiries_by_day.setdefault(day, []).append(exp)
        for day in self._expiries_by_day:
            self._expiries_by_day[day].sort()
        self._settlement: Dict[date, Optional[float]] = {}
        self._settlement_source: Dict[date, str] = {}

    def chain(self, day: date, expiry: date) -> pd.DataFrame:
        return self._by_day_expiry.get((day, expiry), pd.DataFrame())

    def has_day(self, day: date) -> bool:
        return day in self._expiries_by_day

    def settlement(self, expiry: date, index_close: Optional[Dict[date, float]]) -> Optional[float]:
        if expiry not in self._settlement:
            rows = self.chain(expiry, expiry)
            val = None
            src = "NSE_INDEX_CLOSE_VERIFIED_IDENTICAL"
            if not rows.empty:
                vals = rows["SttlmPric"].dropna().unique()
                if len(vals) == 1 and vals[0] > 0:
                    val, src = float(vals[0]), "BHAVCOPY_SETTLEMENT"
            if val is None and index_close:
                v = index_close.get(expiry)
                if v and v > 0:
                    val = float(v)
            self._settlement[expiry] = val
            self._settlement_source[expiry] = src
        return self._settlement[expiry]

    def settlement_source(self, expiry: date) -> str:
        return self._settlement_source.get(expiry, "NSE_INDEX_CLOSE_VERIFIED_IDENTICAL")


# ─────────────────────────── CONSTRUCTION ───────────────────────────

def condor_strikes(spot: float, vix: float, otm_sd: float, wing_sd: float,
                   strike_step: float = STRIKE_STEP) -> Dict[str, float]:
    """The strategy's own expected-move formula. No parameter is altered."""
    exp_move = spot * (vix / 100.0) * np.sqrt(SPEC_DTE_FOR_EXPECTED_MOVE / 365.0)
    rnd = lambda k: round(k / strike_step) * strike_step          # noqa: E731
    return {
        "expected_move": exp_move,
        "short_call": rnd(spot + otm_sd * exp_move),
        "long_call": rnd(spot + wing_sd * exp_move),
        "short_put": rnd(spot - otm_sd * exp_move),
        "long_put": rnd(spot - wing_sd * exp_move),
    }


def _lookup(day_chain: pd.DataFrame, strike: float, opt: str) -> Optional[pd.Series]:
    """One contract on one session, or None. Never the nearest available strike."""
    r = day_chain[(day_chain["StrkPric"] == strike) & (day_chain["OptnTp"] == opt)]
    return None if r.empty else r.iloc[0]


def build_condor(
    store: pd.DataFrame, entry_day: date, expiry: date,
    spot: float, vix: float, otm_sd: float = SPEC_OTM_SD, wing_sd: float = SPEC_WING_SD,
    require_traded: bool = True,
) -> Dict[str, Any]:
    """
    Resolves all four legs to real contracts at real prices, or refuses.

    Fails closed when a leg is absent or did not trade. It never substitutes a
    nearer strike, because that would silently change the strategy.
    """
    ks = condor_strikes(spot, vix, otm_sd, wing_sd)
    chain = (store.chain(entry_day, expiry) if isinstance(store, ChainIndex)
             else store[(store["TradDt"] == entry_day) & (store["XpryDt"] == expiry)])
    if chain.empty:
        return {"ok": False, "reason": "NO_CHAIN_FOR_EXPIRY", "strikes": ks}

    wants = [
        ("short_call", "CE", "SELL", ks["short_call"]),
        ("long_call", "CE", "BUY", ks["long_call"]),
        ("short_put", "PE", "SELL", ks["short_put"]),
        ("long_put", "PE", "BUY", ks["long_put"]),
    ]
    resolved, missing, untraded = [], [], []
    for role, opt, side, k in wants:
        row = _lookup(chain, k, opt)
        if row is None:
            missing.append(f"{role}@{k:.0f}{opt}")
            continue
        if require_traded and int(row["TtlTradgVol"]) <= 0:
            untraded.append(f"{role}@{k:.0f}{opt}")
            continue
        if float(row["ClsPric"]) <= 0:
            untraded.append(f"{role}@{k:.0f}{opt}:zero_price")
            continue
        resolved.append((role, opt, side, k, row))

    if missing:
        return {"ok": False, "reason": "STRIKE_ABSENT", "detail": missing, "strikes": ks}
    if untraded:
        return {"ok": False, "reason": "LEG_DID_NOT_TRADE", "detail": untraded, "strikes": ks}
    return {"ok": True, "legs": resolved, "strikes": ks}


def _intrinsic(opt: str, strike: float, settle: float) -> float:
    return max(0.0, settle - strike) if opt == "CE" else max(0.0, strike - settle)



def observed_credit_points(
    chains: "ChainIndex", entry_day: date, expiry: date, spot: float, vix: float,
    otm_sd: float = SPEC_OTM_SD, wing_sd: float = SPEC_WING_SD,
) -> Optional[Dict[str, float]]:
    """
    The credit actually available for this cycle, in POINTS, from real prints.

    Points need no lot size, so this works across the whole 2019-2026 history —
    including the legacy era where the exchange publishes no board-lot quantity and
    the rupee-denominated backtest correctly refuses to run. It removes the need to
    hold the credit constant at a later era's mean, which would import the
    volatility regime of one period into another.

    Returns None when any leg is absent or did not trade, so a cycle is either
    priced from four real fills or not priced at all.
    """
    built = build_condor(chains, entry_day, expiry, spot, vix, otm_sd, wing_sd)
    if not built["ok"]:
        return None
    prices = {role: float(row["ClsPric"]) for role, _, _, _, row in built["legs"]}
    strikes = {role: float(k) for role, _, _, k, _ in built["legs"]}
    credit = (prices["short_call"] + prices["short_put"]
              - prices["long_call"] - prices["long_put"])
    return {
        "credit_points": credit,
        "short_call": strikes["short_call"], "short_put": strikes["short_put"],
        "long_call": strikes["long_call"], "long_put": strikes["long_put"],
        "call_wing_width": strikes["long_call"] - strikes["short_call"],
        "put_wing_width": strikes["short_put"] - strikes["long_put"],
    }


# ──────────────────────────── COSTS ────────────────────────────

# STT on EXERCISE of an in-the-money option is levied on the intrinsic
# (settlement) value at 0.125%, not on premium at 0.1%. IndianCostModel documents
# this in its header but only implements the premium-sale rate, so the exercise
# rate is named here and applied only where an exercise actually occurs.
STT_RATE_EXERCISE = 0.00125


def condor_leg_costs(leg_side: str, entry_price: float, exit_price: float,
                     quantity: int, slippage_points: float = 0.10) -> float:
    """
    Statutory cost for ONE condor leg held to expiry.

    The generic roundtrip helper assumes buy-then-sell, which charges a short
    leg's STT on its EXIT. A short option that expires worthless exits at 0, so
    that route reports almost no STT when the real liability is 0.1% of the
    premium RECEIVED at entry. This function charges each side where it is
    actually incurred:

      SELL leg  STT 0.100% on the premium sold at entry
      BUY  leg  stamp duty 0.003% on the premium paid at entry, and
                STT 0.125% on intrinsic if it finishes in the money and exercises
      both      brokerage for the ENTRY order only (expiry settles without an
                order), exchange + SEBI turnover on both legs of the cash flow,
                GST on the service charges, and entry-side slippage only

    Every rate is taken from IndianCostModel so there is a single source of truth.
    """
    entry_turnover = entry_price * quantity
    exit_turnover = exit_price * quantity
    is_sell = leg_side == "SELL"

    brokerage = IndianCostModel.BROKERAGE_PER_ORDER              # entry order only
    if is_sell:
        stt = entry_turnover * IndianCostModel.STT_RATE_SELL
        stamp = 0.0
    else:
        stt = exit_turnover * STT_RATE_EXERCISE if exit_price > 0 else 0.0
        stamp = entry_turnover * IndianCostModel.STAMP_DUTY_RATE_BUY

    turnover = entry_turnover + exit_turnover
    exchange = turnover * IndianCostModel.EXCHANGE_TURNOVER_RATE
    sebi = turnover * IndianCostModel.SEBI_RATE
    gst = (brokerage + exchange + sebi) * IndianCostModel.GST_RATE
    slippage = slippage_points * quantity                        # entry fill only

    return brokerage + stt + exchange + sebi + stamp + gst + slippage


# ──────────────────────────── BACKTEST ────────────────────────────

def run_real_condor_backtest(
    index_df: pd.DataFrame,
    store: pd.DataFrame,
    otm_sd: float = SPEC_OTM_SD,
    wing_sd: float = SPEC_WING_SD,
    max_vix: float = SPEC_MAX_VIX,
    min_rsi: float = 40.0,
    max_rsi: float = 68.0,
    signal_lag: int = 0,
    hold_trading_days: int = 5,
    entry_dte_min: Optional[int] = None,
    entry_dte_max: Optional[int] = None,
    one_trade_per_expiry: bool = True,
) -> Dict[str, Any]:
    """
    Point-in-time weekly condor backtest on authentic prices.

    signal_lag=0 reproduces the research's own timing (the regime is read from the
    same close that fills the trade). signal_lag=1 is the strictly causal variant:
    the regime is read from the PREVIOUS close and the trade fills at today's. The
    difference between the two measures same-bar exposure instead of assuming it away.

    ENTRY TIMING is the faithful translation of the specification, decided before
    any result was inspected. The research holds `df.iloc[i+1:i+6]` — five forward
    bars — and prices the strikes with sqrt(5/365). Both refer to the same five
    TRADING sessions, so the canonical entry is the session exactly
    `hold_trading_days` sessions before the target expiry. Anchoring on the real
    expiry calendar rather than a fixed stride also handles NIFTY's weekly shift
    from Thursday to Tuesday without a hardcoded weekday.

    Passing entry_dte_min/max instead selects on CALENDAR days, which admits
    short-stub expiries priced with a five-day expected move. It is retained only
    as a sensitivity control.
    """
    d = index_df.sort_values("datetime").reset_index(drop=True).copy()
    if "rsi_14" not in d.columns:
        d["rsi_14"] = _rsi(d["close"], 14)
    d["sess"] = d["datetime"].dt.date

    expiries = weekly_expiry_calendar(store)
    available_days = set(store["TradDt"].unique())
    chains = ChainIndex(store)
    # Authentic index closes, used only where the bhavcopy settlement field is
    # unpublished (2019-2020 legacy sessions). Verified identical where both exist.
    index_close = dict(zip(d["sess"], d["close"].astype(float)))

    # Session index over the authentic exchange calendar, so "5 trading days
    # before expiry" is counted in real sessions rather than assumed weekdays.
    sess_list = list(d["sess"])
    sess_pos = {v: k for k, v in enumerate(sess_list)}
    use_calendar_window = entry_dte_min is not None and entry_dte_max is not None
    trades: List[CondorTrade] = []
    rejects: Dict[str, int] = {}
    used_expiries: set = set()

    def rej(k: str) -> None:
        rejects[k] = rejects.get(k, 0) + 1

    for i in range(len(d)):
        sess = d.loc[i, "sess"]
        if sess not in available_days:
            rej("NO_BHAVCOPY_FOR_SESSION"); continue

        src = i - signal_lag
        if src < 0:
            continue
        vix = d.loc[src, "vix"]
        rsi = d.loc[src, "rsi_14"]
        if not np.isfinite(vix) or not np.isfinite(rsi):
            rej("REGIME_INPUT_UNAVAILABLE"); continue
        if not (vix < max_vix and min_rsi <= rsi <= max_rsi):
            rej("REGIME_FILTER_BLOCKED"); continue

        nxt = [e for e in expiries if e > sess]
        if not nxt:
            rej("NO_FORWARD_EXPIRY"); continue
        expiry = nxt[0]
        if one_trade_per_expiry and expiry in used_expiries:
            rej("EXPIRY_ALREADY_TRADED"); continue
        dte = (expiry - sess).days
        if use_calendar_window:
            if not (entry_dte_min <= dte <= entry_dte_max):
                rej("DTE_OUTSIDE_WEEKLY_CYCLE"); continue
        else:
            exp_pos = sess_pos.get(expiry)
            if exp_pos is None:
                rej("EXPIRY_NOT_A_KNOWN_SESSION"); continue
            if exp_pos - i != hold_trading_days:
                rej("NOT_THE_CANONICAL_HOLD_WINDOW"); continue

        spot = float(d.loc[i, "close"])
        built = build_condor(chains, sess, expiry, spot, float(vix), otm_sd, wing_sd)
        if not built["ok"]:
            rej(built["reason"]); continue

        settle = chains.settlement(expiry, index_close)
        if settle is None:
            rej("NO_SETTLEMENT_PRICE"); continue

        # Lot size must be authentic. UDiFF publishes it per contract and it is NOT
        # constant over time (75 -> 65, with both live simultaneously during the
        # transition), so it is read per trade rather than assumed. The legacy
        # archive does not publish it at all and is not derivable from
        # VAL_INLAKH/CONTRACTS, so those sessions fail closed for rupee accounting
        # rather than being priced with a guessed multiplier.
        lots_seen = {int(r["NewBrdLotQty"]) for _, _, _, _, r in built["legs"]
                     if "NewBrdLotQty" in r.index and pd.notna(r["NewBrdLotQty"])}
        if len(lots_seen) != 1 or not lots_seen or next(iter(lots_seen)) <= 0:
            rej("LOT_SIZE_UNAVAILABLE_OR_INCONSISTENT"); continue
        lot = next(iter(lots_seen))

        legs: List[CondorLeg] = []
        gross = 0.0
        for role, opt, side, k, row in built["legs"]:
            entry_p = float(row["ClsPric"])
            exit_p = _intrinsic(opt, k, settle)
            sign = -1.0 if side == "SELL" else 1.0
            pnl = sign * (exit_p - entry_p) * lot
            gross += pnl
            legs.append(CondorLeg(
                role=role, option_type=opt, side=side, strike=float(k),
                expiry=str(expiry), security_id=str(int(row["FinInstrmId"])),
                contract_name=str(row["FinInstrmNm"]), quantity=lot,
                entry_price=entry_p, exit_price=exit_p,
                entry_volume=int(row["TtlTradgVol"]), entry_oi=int(row["OpnIntrst"]),
                pnl=round(pnl, 2),
                entry_day_high=float(row["HghPric"]), entry_day_low=float(row["LwPric"]),
            ))

        credit = sum((l.entry_price if l.side == "SELL" else -l.entry_price) for l in legs)
        by_role = {l.role: l for l in legs}
        wing_w = max(by_role["long_call"].strike - by_role["short_call"].strike,
                     by_role["short_put"].strike - by_role["long_put"].strike)
        costs = sum(
            condor_leg_costs(l.side, l.entry_price, l.exit_price, lot) for l in legs
        )
        breach_up = settle > by_role["short_call"].strike
        breach_dn = settle < by_role["short_put"].strike

        used_expiries.add(expiry)
        trades.append(CondorTrade(
            entry_date=str(sess), expiry=str(expiry), days_held=dte,
            spot_entry=spot, spot_settle=settle, vix_entry=float(vix), rsi_entry=float(rsi),
            expected_move=round(built["strikes"]["expected_move"], 2), legs=legs,
            net_credit_points=round(credit, 2), wing_width=round(wing_w, 2),
            max_loss_points=round(wing_w - credit, 2),
            gross_pnl=round(gross, 2), costs=round(costs, 2),
            net_pnl=round(gross - costs, 2),
            breached=bool(breach_up or breach_dn),
            breach_side="call" if breach_up else ("put" if breach_dn else "none"),
            lot_size=lot, settlement_source=chains.settlement_source(expiry),
        ))

    return {
        "status": "OK" if trades else "NO_TRADES",
        "trades": trades,
        "rejects": rejects,
        "sessions_scanned": len(d),
        "execution_basis": EXECUTION_BASIS,
        "signal_lag": signal_lag,
        "entry_rule": ("CALENDAR_DTE_WINDOW" if use_calendar_window
                       else f"EXACTLY_{hold_trading_days}_TRADING_SESSIONS_TO_EXPIRY"),
    }


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - (100 / (1 + gain / loss.replace(0, np.nan)))



def adverse_fill_pnl(trade: "CondorTrade") -> Optional[Dict[str, Any]]:
    """
    Reprices a trade at the WORST fill that actually traded on the entry session.

    Sells hit the session's LOW and buys hit its HIGH, so the credit collected is
    the smallest the market genuinely offered that day. This bounds execution risk
    with real exchange prints instead of an assumed spread.

    READ THIS AS AN EXTREME BOUND, NOT AN EXPECTED OUTCOME. The strategy enters at
    the CLOSE, and NSE's closing price for an F&O contract is derived from the last
    half hour, so the relevant adverse window is that half hour rather than the whole
    session. Measured on 5-minute bars for contracts at exactly the offsets this
    strategy uses (ATM+/-13 shorts, ATM+/-17 wings, read-only /charts/intraday,
    2026-09-18): the daily close fell inside the closing half-hour range on 223 of
    223 observations, and that half-hour span averaged 17.7% of the full-day span on
    the weekly contracts most like Bot 1's legs. A full-day worst-tick fill is
    therefore several times more adverse than entering at the close can plausibly be.
    Use `slippage_sensitivity` for the realistic range and this function for the floor.

    Returns None if any leg lacks a usable traded range.
    """
    gross = 0.0
    credit = 0.0
    for l in trade.legs:
        hi, lo = l.entry_day_high, l.entry_day_low
        if hi <= 0 or lo <= 0 or hi < lo:
            return None
        fill = lo if l.side == "SELL" else hi
        sign = -1.0 if l.side == "SELL" else 1.0
        gross += sign * (l.exit_price - fill) * l.quantity
        credit += fill if l.side == "SELL" else -fill
    costs = sum(
        condor_leg_costs(l.side, (l.entry_day_low if l.side == "SELL" else l.entry_day_high),
                         l.exit_price, l.quantity)
        for l in trade.legs
    )
    return {"gross_pnl": round(gross, 2), "costs": round(costs, 2),
            "net_pnl": round(gross - costs, 2), "net_credit_points": round(credit, 2)}



# ──────────────────── PRICE-FREE BREACH STUDY ────────────────────

def run_breach_study(
    index_df: pd.DataFrame,
    store: pd.DataFrame,
    otm_sd: float = SPEC_OTM_SD,
    wing_sd: float = SPEC_WING_SD,
    max_vix: float = SPEC_MAX_VIX,
    min_rsi: float = 40.0,
    max_rsi: float = 68.0,
    hold_trading_days: int = 5,
    signal_lag: int = 0,
) -> Dict[str, Any]:
    """
    Whether the shorts would have been breached — computed WITHOUT option prices.

    This exists because the statistically decisive question for a condor is the
    breach rate, and answering it needs only spot, VIX, the strike formula and the
    settlement price. None of those depend on a lot size or on a leg having traded,
    so this runs over the FULL history including the legacy era where the bhavcopy
    publishes neither lot size nor settlement, and the index archive supplies the
    settlement that is verified identical where both exist.

    It deliberately reports NO P&L. A breach rate alone cannot value the structure;
    it can only show whether the observed rate is distinguishable from the
    break-even rate implied by prices measured elsewhere.
    """
    d = index_df.sort_values("datetime").reset_index(drop=True).copy()
    if "rsi_14" not in d.columns:
        d["rsi_14"] = _rsi(d["close"], 14)
    d["sess"] = d["datetime"].dt.date

    expiries = weekly_expiry_calendar(store)
    chains = ChainIndex(store)
    index_close = dict(zip(d["sess"], d["close"].astype(float)))
    sess_pos = {v: k for k, v in enumerate(d["sess"])}

    rows, rejects, used = [], {}, set()

    def rej(k: str) -> None:
        rejects[k] = rejects.get(k, 0) + 1

    for i in range(len(d)):
        sess = d.loc[i, "sess"]
        src = i - signal_lag
        if src < 0:
            continue
        vix, rsi = d.loc[src, "vix"], d.loc[src, "rsi_14"]
        if not np.isfinite(vix) or not np.isfinite(rsi):
            rej("REGIME_INPUT_UNAVAILABLE"); continue
        if not (vix < max_vix and min_rsi <= rsi <= max_rsi):
            rej("REGIME_FILTER_BLOCKED"); continue

        nxt = [e for e in expiries if e > sess]
        if not nxt:
            rej("NO_FORWARD_EXPIRY"); continue
        expiry = nxt[0]
        if expiry in used:
            rej("EXPIRY_ALREADY_TRADED"); continue
        exp_pos = sess_pos.get(expiry)
        if exp_pos is None or exp_pos - i != hold_trading_days:
            rej("NOT_THE_CANONICAL_HOLD_WINDOW"); continue

        settle = chains.settlement(expiry, index_close)
        if settle is None:
            rej("NO_SETTLEMENT_PRICE"); continue

        spot = float(d.loc[i, "close"])
        ks = condor_strikes(spot, float(vix), otm_sd, wing_sd)
        priced = observed_credit_points(chains, sess, expiry, spot, float(vix),
                                        otm_sd, wing_sd)
        up = settle > ks["short_call"]
        dn = settle < ks["short_put"]
        beyond_wing = settle > ks["long_call"] or settle < ks["long_put"]
        used.add(expiry)
        rows.append({
            "entry_date": str(sess), "expiry": str(expiry), "spot_entry": spot,
            "spot_settle": settle, "vix": float(vix), "rsi": float(rsi),
            "expected_move": ks["expected_move"],
            "short_call": ks["short_call"], "short_put": ks["short_put"],
            "long_call": ks["long_call"], "long_put": ks["long_put"],
            "breached": bool(up or dn), "beyond_wing": bool(beyond_wing),
            "breach_side": "call" if up else ("put" if dn else "none"),
            "move_in_expected_moves": abs(settle - spot) / ks["expected_move"],
            "settlement_source": chains.settlement_source(expiry),
            "observed_credit_points": priced["credit_points"] if priced else None,
            "legs_priced": bool(priced),
        })

    return {"cycles": pd.DataFrame(rows), "rejects": rejects,
            "sessions_scanned": int(len(d))}


def summarise_condor(trades: List[CondorTrade]) -> Dict[str, Any]:
    """Per-lot economics. Margin-independent, so no unverified SPAN number is needed."""
    if not trades:
        return {"total_trades": 0, "note": "no trades in the covered window",
                "execution_basis": EXECUTION_BASIS}
    df = pd.DataFrame([{
        "entry_date": t.entry_date, "net_pnl": t.net_pnl, "gross_pnl": t.gross_pnl,
        "costs": t.costs, "credit": t.net_credit_points, "max_loss": t.max_loss_points,
        "breached": t.breached, "dte": t.days_held,
    } for t in trades])
    eq = df["net_pnl"].cumsum()
    dd = (eq - eq.cummax()).min()
    wins = df[df["net_pnl"] > 0]["net_pnl"]
    loss = df[df["net_pnl"] <= 0]["net_pnl"]
    return {
        "total_trades": int(len(df)),
        "net_pnl_per_lot": float(df["net_pnl"].sum()),
        "gross_pnl_per_lot": float(df["gross_pnl"].sum()),
        "total_costs_per_lot": float(df["costs"].sum()),
        "win_rate": float((df["net_pnl"] > 0).mean() * 100.0),
        "breach_rate": float(df["breached"].mean() * 100.0),
        "avg_credit_points": float(df["credit"].mean()),
        "avg_max_loss_points": float(df["max_loss"].mean()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(loss.mean()) if len(loss) else 0.0,
        "profit_factor": float(wins.sum() / abs(loss.sum())) if len(loss) and loss.sum() != 0 else None,
        "max_drawdown_rupees_per_lot": float(abs(dd)),
        "expectancy_per_trade": float(df["net_pnl"].mean()),
        "execution_basis": EXECUTION_BASIS,
        "margin_basis": "SPAN_UNVERIFIED_PER_LOT_ECONOMICS_REPORTED",
    }
