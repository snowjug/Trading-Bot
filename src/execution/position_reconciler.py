"""
Broker position reconciliation (B9 / Codex CRITICAL #2).

Compares the session's local view of open positions against the broker's
reported positions. On any disagreement — or on any inability to establish what
the broker actually holds — trading HALTS for new entries.

STRICTLY READ-ONLY. This module never places, amends, cancels or closes an
order. It performs GET requests only.

WHY THIS FILE HAS AN EXPLICIT SCHEMA
------------------------------------
The previous version consumed `DhanBrokerAdapter.get_positions()`, which returns
`PaperPosition` dataclasses, while the parser accepted only dicts containing
`securityId`. Every broker position was therefore silently skipped and the
broker always appeared FLAT. Worse, adapter errors were converted into an empty
list, so an outage was indistinguishable from "no positions" and trading
continued straight through a reconciliation failure.

The canonical `BrokerPosition` / `BrokerSnapshot` types below exist so that
"I know the broker is flat" can never again be confused with "I could not find
out what the broker holds".
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import Config
from src.utils.logging import setup_logging

logger = setup_logging("execution.reconciler")


class BrokerStateStatus(str, Enum):
    """The four distinguishable states of broker knowledge."""

    AVAILABLE_FLAT = "AVAILABLE_FLAT"            # queried successfully, no open positions
    AVAILABLE_POSITIONS = "AVAILABLE_POSITIONS"  # queried successfully, positions returned
    UNAVAILABLE = "UNAVAILABLE"                  # error, timeout, auth failure, non-200
    MALFORMED = "MALFORMED"                      # responded, but the payload is not parseable

    @property
    def is_trustworthy(self) -> bool:
        """Only a clean query result may be used to authorise further trading."""
        return self in (BrokerStateStatus.AVAILABLE_FLAT, BrokerStateStatus.AVAILABLE_POSITIONS)


@dataclass
class BrokerPosition:
    """Canonical broker-side position. `security_id` is the reconciliation key."""

    security_id: str
    net_qty: float
    trading_symbol: str = ""
    side: str = ""
    avg_price: float = 0.0
    source: str = "DHAN"


@dataclass
class BrokerSnapshot:
    """A complete, self-describing answer to 'what does the broker hold?'."""

    status: BrokerStateStatus
    positions: List[BrokerPosition] = field(default_factory=list)
    error: str = ""
    raw_row_count: int = 0
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_trustworthy(self) -> bool:
        return self.status.is_trustworthy

    def as_quantity_map(self) -> Dict[str, float]:
        """{security_id: net quantity}, aggregating rows for the same contract."""
        out: Dict[str, float] = {}
        for pos in self.positions:
            out[pos.security_id] = out.get(pos.security_id, 0.0) + abs(float(pos.net_qty))
        return out


@dataclass
class ReconciliationResult:
    """Outcome of a local-vs-broker position comparison."""

    reconciled: bool
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    local_positions: Dict[str, float] = field(default_factory=dict)
    broker_positions: Dict[str, float] = field(default_factory=dict)
    mismatches: List[str] = field(default_factory=list)
    broker_available: bool = True
    broker_status: BrokerStateStatus = BrokerStateStatus.AVAILABLE_FLAT
    halt_required: bool = False
    reason: str = ""


def extract_local_positions(bot_states: Dict[str, Any]) -> Dict[str, float]:
    """Aggregates local open quantity per security id, across all strategies."""
    local: Dict[str, float] = {}
    for state in bot_states.values():
        at = state.get("active_trade")
        if not at or at.get("status") == "CLOSED":
            continue
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


def _coerce_row(item: Any) -> Optional[BrokerPosition]:
    """
    Converts one broker row into a BrokerPosition.

    Returns None when the row cannot be trusted. Callers escalate that to
    MALFORMED for the whole snapshot — a row that cannot be understood is never
    skipped, because skipping it would understate broker exposure.
    """
    # Canonical objects pass straight through.
    if isinstance(item, BrokerPosition):
        return item

    # Typed objects (e.g. PaperPosition) exposing the needed attributes.
    if not isinstance(item, dict):
        sid = getattr(item, "security_id", None) or getattr(item, "securityId", None)
        qty = getattr(item, "net_qty", None)
        if qty is None:
            qty = getattr(item, "quantity", None)
        if sid is None or qty is None:
            return None
        try:
            return BrokerPosition(
                security_id=str(sid).strip(),
                net_qty=float(qty),
                trading_symbol=str(getattr(item, "symbol", "") or ""),
                avg_price=float(getattr(item, "avg_price", 0.0) or 0.0),
            )
        except (TypeError, ValueError):
            return None

    sid = item.get("securityId") or item.get("security_id")
    if sid is None or not str(sid).strip():
        return None
    qty = item.get("netQty", item.get("net_quantity", item.get("quantity")))
    if qty is None:
        return None
    try:
        qty_f = float(qty)
    except (TypeError, ValueError):
        return None

    return BrokerPosition(
        security_id=str(sid).strip(),
        net_qty=qty_f,
        trading_symbol=str(item.get("tradingSymbol", "") or ""),
        side=str(item.get("positionType", "") or ""),
        avg_price=float(item.get("costPrice", item.get("buyAvg", 0.0)) or 0.0),
    )


def parse_broker_payload(raw: Any) -> BrokerSnapshot:
    """
    Parses a raw broker positions payload into a canonical snapshot.

    Any unparseable row makes the WHOLE snapshot MALFORMED. Partial parsing
    would silently understate broker exposure, which is precisely the failure
    this module exists to prevent.
    """
    if raw is None:
        return BrokerSnapshot(
            status=BrokerStateStatus.UNAVAILABLE,
            error="Broker returned no payload",
        )
    if not isinstance(raw, (list, tuple)):
        return BrokerSnapshot(
            status=BrokerStateStatus.MALFORMED,
            error=f"Expected a list of positions, got {type(raw).__name__}",
        )

    positions: List[BrokerPosition] = []
    for idx, item in enumerate(raw):
        parsed = _coerce_row(item)
        if parsed is None:
            return BrokerSnapshot(
                status=BrokerStateStatus.MALFORMED,
                error=f"Unparseable broker position row at index {idx}: {item!r}",
                raw_row_count=len(raw),
            )
        # Genuinely flat rows (net zero) carry no exposure.
        if abs(parsed.net_qty) > 0:
            positions.append(parsed)

    status = (
        BrokerStateStatus.AVAILABLE_POSITIONS if positions
        else BrokerStateStatus.AVAILABLE_FLAT
    )
    return BrokerSnapshot(status=status, positions=positions, raw_row_count=len(raw))


def reconcile_snapshot(bot_states: Dict[str, Any], snapshot: BrokerSnapshot) -> ReconciliationResult:
    """
    Compares local positions against a canonical broker snapshot.

    Fail-closed rules:
      * UNAVAILABLE or MALFORMED -> halt. Broker state is unknown, and unknown
        is never treated as flat.
      * Any quantity mismatch -> halt.
      * Any broker position with no local counterpart -> halt, in paper mode too,
        because nothing this system did could have created it.

    In paper mode no order reaches the broker, so a local position with a flat
    broker book is the EXPECTED asymmetry and does not halt.
    """
    local = extract_local_positions(bot_states)
    paper_mode = not Config.LIVE_TRADING_ENABLED

    if not snapshot.is_trustworthy:
        reason = (
            f"BROKER_STATE_{snapshot.status.value}: cannot verify local positions "
            f"against broker ({snapshot.error or 'no detail'})"
        )
        logger.critical(f"{reason}. Halting new entries.")
        return ReconciliationResult(
            reconciled=False, local_positions=local, broker_positions={},
            broker_available=False, broker_status=snapshot.status,
            halt_required=True, reason=reason,
            mismatches=[f"broker state {snapshot.status.value}"],
        )

    broker = snapshot.as_quantity_map()
    mismatches: List[str] = []

    for sid, qty in local.items():
        b_qty = broker.get(sid, 0.0)
        if b_qty != qty and not (paper_mode and b_qty == 0.0):
            mismatches.append(f"{sid}: local {qty:g} vs broker {b_qty:g}")

    for sid, b_qty in broker.items():
        if sid not in local:
            mismatches.append(f"{sid}: broker {b_qty:g} with NO local position")

    if mismatches:
        reason = "POSITION_MISMATCH: " + "; ".join(mismatches)
        logger.critical(f"{reason}. Halting new entries pending investigation.")
        return ReconciliationResult(
            reconciled=False, local_positions=local, broker_positions=broker,
            broker_status=snapshot.status, mismatches=mismatches,
            halt_required=True, reason=reason,
        )

    return ReconciliationResult(
        reconciled=True, local_positions=local, broker_positions=broker,
        broker_status=snapshot.status,
        reason="RECONCILED" + (" (paper mode: broker book expected empty)" if paper_mode else ""),
    )


def reconcile_positions(
    bot_states: Dict[str, Any],
    broker_positions: Any,
    broker_available: bool = True,
) -> ReconciliationResult:
    """Compatibility wrapper: converts a raw payload into a snapshot, then reconciles."""
    if not broker_available:
        snapshot = BrokerSnapshot(
            status=BrokerStateStatus.UNAVAILABLE,
            error="caller reported broker unavailable",
        )
    else:
        snapshot = parse_broker_payload(broker_positions)
    return reconcile_snapshot(bot_states, snapshot)


def fetch_broker_snapshot() -> BrokerSnapshot:
    """
    Read-only fetch of the broker position book as a canonical snapshot.

    Every failure mode is reported distinctly; none of them degrade to an empty
    position list. GET only — this function cannot mutate broker state.
    """
    try:
        from src.execution.broker_adapters.dhan import DhanBrokerAdapter

        adapter = DhanBrokerAdapter()
        if not adapter.client_id or not adapter.access_token:
            return BrokerSnapshot(
                status=BrokerStateStatus.UNAVAILABLE,
                error="Dhan credentials not configured",
            )
        return adapter.fetch_positions_snapshot()
    except Exception as e:
        logger.warning(f"Broker position fetch failed: {e}")
        return BrokerSnapshot(status=BrokerStateStatus.UNAVAILABLE, error=str(e))


def fetch_broker_positions_readonly() -> tuple:
    """Compatibility wrapper returning (positions, available) from the snapshot."""
    snapshot = fetch_broker_snapshot()
    if not snapshot.is_trustworthy:
        return None, False
    return snapshot.positions, True


def broker_source_configured() -> bool:
    """True when Dhan credentials exist, i.e. a broker book can be queried at all."""
    return bool(Config.DHAN_CLIENT_ID and Config.DHAN_ACCESS_TOKEN)
