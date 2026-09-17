"""
Broker position reconciliation (B9).

Compares the session's local view of open positions against the broker's
reported positions. On any disagreement trading HALTS: an unexplained mismatch
means the local book is not a trustworthy description of real exposure, and
trading through it would compound the error.

STRICTLY READ-ONLY. This module never places, amends or cancels an order. In
paper mode the broker side is expected to be empty, so the reconciler's job is
to prove the local book is also empty of anything the broker does not know about.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import Config
from src.utils.logging import setup_logging

logger = setup_logging("execution.reconciler")


@dataclass
class ReconciliationResult:
    """Outcome of a local-vs-broker position comparison."""
    reconciled: bool
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    local_positions: Dict[str, float] = field(default_factory=dict)
    broker_positions: Dict[str, float] = field(default_factory=dict)
    mismatches: List[str] = field(default_factory=list)
    broker_available: bool = True
    halt_required: bool = False
    reason: str = ""


def extract_local_positions(bot_states: Dict[str, Any]) -> Dict[str, float]:
    """Aggregates local open quantity per security id, across all strategies."""
    local: Dict[str, float] = {}
    for state in bot_states.values():
        at = state.get("active_trade")
        if not at or at.get("status") == "CLOSED":
            continue
        # Multi-leg structures carry per-leg ids; reconcile each leg separately.
        legs = [
            at.get("call_security_id"), at.get("put_security_id"),
            at.get("short_security_id"), at.get("long_security_id"),
        ]
        legs = [str(x) for x in legs if x]
        if not legs:
            sid = str(at.get("security_id", "")).strip()
            if sid and "/" not in sid:
                legs = [sid]
        qty = abs(float(at.get("qty", 0) or 0))
        for leg in legs:
            local[leg] = local.get(leg, 0.0) + qty
    return local


def extract_broker_positions(raw_positions: Optional[List[Dict[str, Any]]]) -> Dict[str, float]:
    """Normalises a Dhan positions payload into {security_id: net_quantity}."""
    broker: Dict[str, float] = {}
    for item in raw_positions or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("securityId") or item.get("security_id") or "").strip()
        if not sid:
            continue
        qty = item.get("netQty", item.get("net_quantity", item.get("quantity", 0)))
        try:
            qty_f = abs(float(qty))
        except (TypeError, ValueError):
            qty_f = 0.0
        if qty_f > 0:
            broker[sid] = broker.get(sid, 0.0) + qty_f
    return broker


def reconcile_positions(
    bot_states: Dict[str, Any],
    broker_positions: Optional[List[Dict[str, Any]]],
    broker_available: bool = True,
) -> ReconciliationResult:
    """
    Compares local and broker positions and decides whether trading may continue.

    In paper mode (LIVE_TRADING_ENABLED False) no order ever reaches the broker,
    so the broker legitimately reports nothing while the local book holds
    simulated positions. That expected asymmetry is reported but does not halt
    trading; any OTHER disagreement does.
    """
    local = extract_local_positions(bot_states)
    broker = extract_broker_positions(broker_positions)
    paper_mode = not Config.LIVE_TRADING_ENABLED

    if not broker_available:
        return ReconciliationResult(
            reconciled=False, local_positions=local, broker_positions=broker,
            broker_available=False, halt_required=True,
            reason="BROKER_STATE_UNAVAILABLE: cannot verify local positions against broker",
            mismatches=["broker position feed unavailable"],
        )

    mismatches: List[str] = []
    for sid, qty in local.items():
        b_qty = broker.get(sid, 0.0)
        if b_qty != qty and not (paper_mode and b_qty == 0.0):
            mismatches.append(f"{sid}: local {qty:g} vs broker {b_qty:g}")

    # A position the broker knows about that we do not is always a hard mismatch,
    # in paper mode too: nothing this system did could have created it.
    for sid, b_qty in broker.items():
        if sid not in local:
            mismatches.append(f"{sid}: broker {b_qty:g} with NO local position")

    if mismatches:
        reason = "POSITION_MISMATCH: " + "; ".join(mismatches)
        logger.critical(f"{reason}. Halting new trading pending investigation.")
        return ReconciliationResult(
            reconciled=False, local_positions=local, broker_positions=broker,
            mismatches=mismatches, halt_required=True, reason=reason,
        )

    return ReconciliationResult(
        reconciled=True, local_positions=local, broker_positions=broker,
        reason="RECONCILED" + (" (paper mode: broker book expected empty)" if paper_mode else ""),
    )


def fetch_broker_positions_readonly() -> tuple:
    """
    Read-only fetch of broker positions. Returns (positions, available).

    Uses the existing adapter's GET /positions route. Never sends an order.
    """
    try:
        from src.execution.broker_adapters.dhan import DhanBrokerAdapter

        adapter = DhanBrokerAdapter()
        if not adapter.client_id or not adapter.access_token:
            return None, False
        return adapter.get_positions(), True
    except Exception as e:
        logger.warning(f"Broker position fetch failed: {e}")
        return None, False
