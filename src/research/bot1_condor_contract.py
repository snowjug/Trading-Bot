"""
Bot 1 — Iron Condor data-ingestion contract and fail-closed four-leg engine.

WHY THIS EXISTS
---------------
Bot 1's specification requires four legs at +-1.8 SD (shorts) and +-2.4 SD
(wings). Measured against the live DhanHQ `/charts/rollingoption` endpoint on
2026-09-17 (read-only), the available strike ladder stops at ATM+-10:

    ATM .. ATM+10  -> 770 rows, real iv/oi/strike/spot/OHLCV at 5-minute bars
    ATM+11 .. +17  -> HTTP 200 with EMPTY arrays

Across 420 sessions (2025-01-02 .. 2026-09-16, VIX 9.15-27.89) the 1.8-SD short
is reachable on **0.0%** of days and the 2.4-SD wing on **0.0%** of days. The
maximum reachable distance at median spot/VIX is ~1.34 SD.

So Bot 1 cannot be backtested at its specified strikes with obtainable data.

This module therefore does NOT implement a condor backtest on invented prices.
It defines the CONTRACT a correct dataset must satisfy, and an engine that
refuses to run until that contract is met. Dropping in a compliant dataset later
requires no change to strategy logic.

NOTHING HERE FABRICATES: no synthetic premium, no assumed delta, no modelled IV,
no invented margin. Every accessor either returns authentic data or fails closed.
"""

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.logging import setup_logging

logger = setup_logging("research.bot1_contract")

# ── Measured empirically against the live API on 2026-09-17 (read-only) ──
MEASURED_MAX_STRIKE_OFFSET = 10      # ATM+10 served; ATM+11 returns empty
NIFTY_STRIKE_STEP = 50.0
MEASURED_COVERAGE_NOTE = (
    "DhanHQ /charts/rollingoption serves ATM..ATM+/-10 (+/-500 pts) with real "
    "iv/oi/strike/spot/OHLCV; ATM+/-11 and beyond return HTTP 200 with empty "
    "arrays. Verified 2026-09-17."
)


class CondorFeasibility(str, Enum):
    """Why a condor can or cannot be constructed for a given session."""

    FEASIBLE = "FEASIBLE"
    INSUFFICIENT_STRIKE_COVERAGE = "INSUFFICIENT_STRIKE_COVERAGE"
    MISSING_QUOTE = "MISSING_QUOTE"
    MISSING_UNDERLYING_STATE = "MISSING_UNDERLYING_STATE"
    SPECIFICATION_INCOMPLETE = "SPECIFICATION_INCOMPLETE"


@dataclass(frozen=True)
class CondorLegSpec:
    """One leg of the structure. Identity is required — never a synthetic blend."""

    role: str                 # short_call | long_call | short_put | long_put
    option_type: str          # CE | PE
    side: str                 # SELL | BUY
    sd_multiple: float        # 1.8 shorts, 2.4 wings (from the strategy spec)
    strike: Optional[float] = None
    expiry: Optional[str] = None
    security_id: Optional[str] = None
    quantity: Optional[int] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None

    @property
    def is_priced(self) -> bool:
        return (
            self.entry_price is not None and self.exit_price is not None
            and self.entry_price > 0 and self.exit_price > 0
        )

    @property
    def is_identified(self) -> bool:
        return all(x is not None for x in (self.strike, self.expiry, self.security_id, self.quantity))


@dataclass
class CondorConstruction:
    """The full four-leg structure, or an explicit refusal."""

    feasibility: CondorFeasibility
    legs: List[CondorLegSpec] = field(default_factory=list)
    reason: str = ""
    required_offsets: Dict[str, int] = field(default_factory=dict)
    available_offset: int = MEASURED_MAX_STRIKE_OFFSET

    @property
    def is_complete_four_leg(self) -> bool:
        roles = {leg.role for leg in self.legs}
        return roles == {"short_call", "long_call", "short_put", "long_put"}


class OptionChainSource(Protocol):
    """
    The ingestion interface a compliant historical option dataset must satisfy.

    A conforming source supplies, per (date, expiry, strike, option_type), an
    authentic executable price plus identity. Implementations must NOT
    interpolate, model or otherwise invent absent strikes.
    """

    def max_strike_offset(self) -> int:
        """Furthest strike offset (in strike steps) the source can actually serve."""

    def get_leg_quote(
        self, trade_date: str, expiry: str, strike: float, option_type: str
    ) -> Optional[Dict[str, Any]]:
        """Authentic quote for one contract, or None. Never a modelled price."""


class DhanRollingOptionSource:
    """
    Concrete source backed by the verified `/charts/rollingoption` endpoint.

    Read-only. Declares the measured ceiling so callers fail closed rather than
    silently sampling a nearer strike than the strategy specifies.
    """

    def __init__(self, max_offset: int = MEASURED_MAX_STRIKE_OFFSET):
        self._max_offset = max_offset

    def max_strike_offset(self) -> int:
        return self._max_offset

    def get_leg_quote(
        self, trade_date: str, expiry: str, strike: float, option_type: str
    ) -> Optional[Dict[str, Any]]:
        # Intentionally not implemented against arbitrary absolute strikes: the
        # endpoint addresses strikes by ATM-relative offset and cannot serve the
        # offsets this strategy needs. Implementing a nearest-available
        # substitution here would silently change the strategy.
        logger.warning(
            "DhanRollingOptionSource cannot address arbitrary absolute strikes; "
            f"{MEASURED_COVERAGE_NOTE}"
        )
        return None


def required_strike_offsets(
    spot: float, vix: float, otm_sd: float, wing_sd: float,
    days_to_expiry: int = 5, strike_step: float = NIFTY_STRIKE_STEP,
) -> Dict[str, int]:
    """
    Strike offsets (in steps from ATM) the specification demands for this session.

    Uses the strategy's own expected-move formula; no parameter is altered.
    """
    exp_move = spot * (vix / 100.0) * np.sqrt(days_to_expiry / 365.0)
    return {
        "short_call": int(round(otm_sd * exp_move / strike_step)),
        "short_put": int(round(otm_sd * exp_move / strike_step)),
        "long_call": int(round(wing_sd * exp_move / strike_step)),
        "long_put": int(round(wing_sd * exp_move / strike_step)),
    }


def assess_condor_feasibility(
    spot: Optional[float], vix: Optional[float], source: OptionChainSource,
    otm_sd: float = 1.8, wing_sd: float = 2.4, days_to_expiry: int = 5,
) -> CondorConstruction:
    """
    Decides whether a compliant four-leg condor can be sourced for this session.

    Fails closed on missing underlying state and on any leg whose strike lies
    beyond the source's real coverage. It NEVER substitutes a nearer strike.
    """
    if not spot or not vix or spot <= 0 or vix <= 0:
        return CondorConstruction(
            feasibility=CondorFeasibility.MISSING_UNDERLYING_STATE,
            reason="spot and VIX are both required to derive the expected move",
        )

    needed = required_strike_offsets(spot, vix, otm_sd, wing_sd, days_to_expiry)
    available = source.max_strike_offset()
    unreachable = {k: v for k, v in needed.items() if v > available}

    if unreachable:
        return CondorConstruction(
            feasibility=CondorFeasibility.INSUFFICIENT_STRIKE_COVERAGE,
            reason=(
                f"legs {sorted(unreachable)} require offsets {unreachable} but the "
                f"source serves at most ATM+/-{available}. {MEASURED_COVERAGE_NOTE} "
                "Substituting a nearer strike would change the strategy, so this "
                "fails closed."
            ),
            required_offsets=needed,
            available_offset=available,
        )

    legs = [
        CondorLegSpec("short_call", "CE", "SELL", otm_sd),
        CondorLegSpec("long_call", "CE", "BUY", wing_sd),
        CondorLegSpec("short_put", "PE", "SELL", otm_sd),
        CondorLegSpec("long_put", "PE", "BUY", wing_sd),
    ]
    return CondorConstruction(
        feasibility=CondorFeasibility.FEASIBLE, legs=legs,
        required_offsets=needed, available_offset=available,
        reason="all four legs lie within the source's real strike coverage",
    )


def compute_condor_pnl(legs: List[CondorLegSpec], lot_size: int) -> Dict[str, Any]:
    """
    Per-leg P&L from AUTHENTIC prices only.

    Refuses if any leg is unidentified or unpriced. There is no fallback premium,
    no delta proxy and no combined synthetic contract.
    """
    if len(legs) != 4:
        return {"ok": False, "reason": f"expected 4 legs, got {len(legs)}"}
    missing = [l.role for l in legs if not l.is_identified or not l.is_priced]
    if missing:
        return {"ok": False, "reason": f"legs not identified/priced: {missing}"}

    per_leg = []
    gross = 0.0
    for leg in legs:
        direction = -1.0 if leg.side == "SELL" else 1.0
        qty = int(leg.quantity or lot_size)
        pnl = direction * (leg.exit_price - leg.entry_price) * qty
        gross += pnl
        per_leg.append({
            "role": leg.role, "security_id": leg.security_id, "expiry": leg.expiry,
            "strike": leg.strike, "option_type": leg.option_type, "side": leg.side,
            "quantity": qty, "entry_price": leg.entry_price,
            "exit_price": leg.exit_price, "pnl": round(pnl, 2),
        })

    call_width = abs(legs[1].strike - legs[0].strike)
    put_width = abs(legs[2].strike - legs[3].strike)
    net_credit = sum(
        (leg.entry_price if leg.side == "SELL" else -leg.entry_price) for leg in legs
    )
    max_loss = (max(call_width, put_width) - net_credit) * lot_size

    return {
        "ok": True, "per_leg": per_leg, "gross_pnl": round(gross, 2),
        "net_credit_points": round(net_credit, 2),
        "max_loss_rupees": round(max_loss, 2),
        "gross_exposure": round(sum(abs(l["entry_price"] * l["quantity"]) for l in per_leg), 2),
        "margin_basis": "BROKER_MARGIN_UNVERIFIED",
        "span_margin": None,
    }


def run_condor_backtest(
    underlying_df: pd.DataFrame, source: OptionChainSource,
    otm_sd: float = 1.8, wing_sd: float = 2.4,
) -> Dict[str, Any]:
    """
    Four-leg condor backtest. Refuses to produce results without real coverage.

    Returns a status object rather than fabricated metrics, so an empty result is
    explicit instead of looking like a flat strategy.
    """
    if "vix" not in underlying_df.columns:
        return {"status": "BLOCKED", "reason": "underlying frame has no vix column",
                "sessions_feasible": 0, "sessions_total": len(underlying_df)}

    feasible = 0
    reasons: Dict[str, int] = {}
    for _, row in underlying_df.iterrows():
        c = assess_condor_feasibility(row.get("close"), row.get("vix"), source, otm_sd, wing_sd)
        if c.feasibility is CondorFeasibility.FEASIBLE:
            feasible += 1
        else:
            reasons[c.feasibility.value] = reasons.get(c.feasibility.value, 0) + 1

    if feasible == 0:
        return {
            "status": "BLOCKED",
            "reason": "no session has all four specified legs within real strike coverage",
            "sessions_total": len(underlying_df), "sessions_feasible": 0,
            "failure_breakdown": reasons,
            "external_dependency": (
                "Requires an option dataset covering at least +/-2.4 SD "
                f"(~ATM+/-17 strikes at typical VIX). {MEASURED_COVERAGE_NOTE}"
            ),
        }

    return {
        "status": "PARTIAL_COVERAGE", "sessions_total": len(underlying_df),
        "sessions_feasible": feasible, "failure_breakdown": reasons,
        "reason": "coverage exists for a subset of sessions; a subset backtest would "
                  "be regime-selected and is therefore NOT run automatically",
    }
