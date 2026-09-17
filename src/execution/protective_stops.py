"""
Protective stop architecture (B8).

WHAT IS TRUE TODAY
------------------
Every stop and target in this system is SOFTWARE-SIDE. They are fields on a
position dict, evaluated once per monitoring cycle (~30s) against a fresh,
non-inverted executable quote. There is no broker-native protective order: the
`boStopLossValue` / `boProfitValue` fields in the Dhan order payload are zero.

Consequences, stated plainly so nobody mistakes this for broker protection:

  * If the process dies, stops are NOT enforced. Nothing squares the position.
  * If the market-data feed dies, stops are NOT evaluated (the position is
    marked DATA_UNAVAILABLE rather than exited on a stale price — deliberate,
    because exiting on a fabricated price is worse).
  * Between two polls the market can traverse the stop level entirely; realised
    stop slippage can therefore far exceed the modelled 0.50 point.
  * A gap through the stop is not protected at all.

A software stop is NOT equivalent to an exchange-resident SL-M or a bracket
order. Any readiness claim that treats them as equivalent is false.

WHAT THIS MODULE IS FOR
-----------------------
It defines the interface a future broker-native protective order would
implement, so the wiring point is explicit rather than improvised later. It is
deliberately INERT: `BrokerNativeProtectiveStop.submit` raises, and
`protective_stops_enabled()` always returns False while LIVE_TRADING_ENABLED is
False. Nothing in this module places, amends or cancels an order.
"""

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import Config
from src.utils.logging import setup_logging

logger = setup_logging("execution.protective_stops")


@dataclass
class ProtectiveStopRequest:
    """A protective exit a strategy wants to rest at the broker."""
    security_id: str
    quantity: int
    stop_price: float
    target_price: Optional[float] = None
    side: str = "BUY"          # side of the OPEN position
    exchange_segment: str = "NSE_FNO"
    product_type: str = "INTRADAY"


class ProtectiveStopBackend(ABC):
    """Interface for anything that enforces a protective exit."""

    #: True when the stop rests at the exchange rather than in this process.
    is_broker_native: bool = False

    @abstractmethod
    def submit(self, request: ProtectiveStopRequest) -> dict:
        ...

    @abstractmethod
    def cancel(self, stop_id: str) -> bool:
        ...


class SoftwareProtectiveStop(ProtectiveStopBackend):
    """
    The behaviour in force today: the monitoring loop evaluates stops in-process.

    `submit` records intent only. It exists so callers can query
    `is_broker_native` and discover, truthfully, that the position has no
    exchange-resident protection.
    """

    is_broker_native = False

    def submit(self, request: ProtectiveStopRequest) -> dict:
        logger.info(
            f"Software-side stop registered for {request.security_id} @ {request.stop_price}. "
            "NOT broker-resident: unprotected if this process stops."
        )
        return {
            "stop_id": f"SOFT-{request.security_id}-{request.stop_price}",
            "broker_native": False,
            "enforced_by": "monitoring_loop",
            "protection_gap": "none while process is alive and quotes are fresh; total otherwise",
        }

    def cancel(self, stop_id: str) -> bool:
        return True


class BrokerNativeProtectiveStop(ProtectiveStopBackend):
    """
    Placeholder for exchange-resident SL-M / bracket orders. NOT IMPLEMENTED.

    Activating this means sending real orders, so it stays disabled and raises
    if called. Implementing it is a prerequisite for any real-capital use.
    """

    is_broker_native = True

    def submit(self, request: ProtectiveStopRequest) -> dict:
        raise NotImplementedError(
            "Broker-native protective orders are not implemented and must not be "
            "enabled while LIVE_TRADING_ENABLED is False. Submitting one would "
            "place a real order at the exchange."
        )

    def cancel(self, stop_id: str) -> bool:
        raise NotImplementedError("Broker-native protective orders are not implemented.")


class ProtectionState(str, Enum):
    """
    The honest protection status of an open position.

    Nothing in this system may report a position as protected unless a stop is
    actually evaluable right now. A crashed process or a dead feed yields
    UNPROTECTED_* — never SOFTWARE_STOP_ARMED.
    """

    SOFTWARE_STOP_ARMED = "SOFTWARE_STOP_ARMED"
    UNPROTECTED_STALE_DATA = "UNPROTECTED_STALE_DATA"
    UNPROTECTED_NO_QUOTE = "UNPROTECTED_NO_QUOTE"
    BROKER_NATIVE_STOP_UNAVAILABLE = "BROKER_NATIVE_STOP_UNAVAILABLE"


def assess_protection(
    stop_price: Optional[float],
    quote_timestamp: Any = None,
    executable_price: Optional[float] = None,
) -> dict:
    """
    Reports what protection a position actually has at this instant.

    `broker_native` is ALWAYS False: no exchange-resident stop exists. The
    software stop counts as armed only when a stop level is set AND a fresh
    executable price is available to compare it against; otherwise the position
    is explicitly UNPROTECTED.
    """
    from src.execution.dhan_contract_resolver import is_quote_fresh

    result = {
        "broker_native": False,
        "broker_native_state": ProtectionState.BROKER_NATIVE_STOP_UNAVAILABLE.value,
        "protected": False,
        "state": ProtectionState.UNPROTECTED_NO_QUOTE.value,
        "detail": "",
    }

    if stop_price is None or float(stop_price) <= 0:
        result["detail"] = "no stop level configured"
        return result

    if executable_price is None or float(executable_price) <= 0:
        result["detail"] = "no executable price to evaluate the stop against"
        return result

    if not is_quote_fresh(quote_timestamp):
        result["state"] = ProtectionState.UNPROTECTED_STALE_DATA.value
        result["detail"] = (
            "quote is stale, so the stop cannot be evaluated; the position is "
            "NOT protected even though a stop level exists"
        )
        return result

    result["protected"] = True
    result["state"] = ProtectionState.SOFTWARE_STOP_ARMED.value
    result["detail"] = (
        "software stop evaluable in-process only; no protection while the "
        "process is down or the feed is dead"
    )
    return result


def protective_stops_enabled() -> bool:
    """Broker-native protection is unavailable; always False in paper mode."""
    return False


def get_protective_stop_backend() -> ProtectiveStopBackend:
    """Returns the backend actually in force. Always the software one today."""
    if Config.LIVE_TRADING_ENABLED:
        raise RuntimeError(
            "LIVE_TRADING_ENABLED is True but no broker-native protective stop "
            "backend is implemented. Refusing to run positions without protection."
        )
    return SoftwareProtectiveStop()
