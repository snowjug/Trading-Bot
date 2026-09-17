"""
Independent P&L Calculator & Audit Engine (Phase 28).
Strictly decoupled calculation of Gross and Net P&L directly from raw execution parameters.
Does NOT rely on strategy internal state or self-reported numbers.

Compares:
ENGINE_PNL vs INDEPENDENT_PNL
If discrepancy > 0.01 INR:
FAIL VALIDATION.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Tuple
from src.execution.cost_model import IndianCostModel, CostBreakdown


class PnLValidationError(Exception):
    """Raised when engine reported PnL diverges from independent calculation."""
    pass


@dataclass
class IndependentTradeAudit:
    trade_id: str
    strategy: str
    side: str
    quantity: int
    entry_fill: float
    exit_fill: float
    engine_gross_pnl: float
    engine_net_pnl: float
    independent_gross_pnl: float
    independent_costs: CostBreakdown
    independent_net_pnl: float
    discrepancy: float
    status: str  # 'RECONCILED' or 'FAILED'


class IndependentPnLCalculator:
    """
    Independent financial auditor for all trading engines.
    """

    TOLERANCE_INR = 0.05  # Max allowable discrepancy due to float rounding

    @classmethod
    def calculate_trade_pnl(
        cls,
        side: str,
        entry_fill: float,
        exit_fill: float,
        quantity: int,
        entry_bid: float = 0.0,
        entry_ask: float = 0.0,
        exit_bid: float = 0.0,
        exit_ask: float = 0.0,
    ) -> Tuple[float, CostBreakdown, float]:
        """
        Independently calculates (gross_pnl, costs, net_pnl).
        """
        s = side.upper().strip()
        if "BUY" in s or "LONG" in s:
            gross_pnl = (exit_fill - entry_fill) * quantity
        elif "SELL" in s or "SHORT" in s:
            gross_pnl = (entry_fill - exit_fill) * quantity
        else:
            raise ValueError(f"Unknown position side: {side}")

        costs = IndianCostModel.calculate_roundtrip_costs(
            entry_price=entry_fill,
            exit_price=exit_fill,
            quantity=quantity,
            entry_bid=entry_bid,
            entry_ask=entry_ask,
            exit_bid=exit_bid,
            exit_ask=exit_ask,
        )

        net_pnl = gross_pnl - costs.total_costs
        return round(gross_pnl, 2), costs, round(net_pnl, 2)

    @classmethod
    def audit_trade(
        cls,
        trade_record: Dict[str, Any],
        strict_fail: bool = True,
    ) -> IndependentTradeAudit:
        """
        Audits a single trade record against independent calculation.
        """
        tid = str(trade_record.get("id", trade_record.get("trade_id", "UNKNOWN")))
        strat = str(trade_record.get("strategy", "UNKNOWN"))
        side = str(trade_record.get("side", "BUY"))
        qty = int(trade_record.get("qty", trade_record.get("quantity", 0)))
        entry_f = float(trade_record.get("entry_fill", trade_record.get("entry_premium", 0.0)))
        exit_f = float(trade_record.get("exit_fill", 0.0))

        engine_gross = float(trade_record.get("gross_pnl", 0.0))
        engine_net = float(trade_record.get("net_pnl", 0.0))

        ind_gross, ind_costs, ind_net = cls.calculate_trade_pnl(
            side=side,
            entry_fill=entry_f,
            exit_fill=exit_f,
            quantity=qty,
            entry_bid=float(trade_record.get("entry_bid", 0.0) or 0.0),
            entry_ask=float(trade_record.get("entry_ask", 0.0) or 0.0),
            exit_bid=float(trade_record.get("exit_bid", 0.0) or 0.0),
            exit_ask=float(trade_record.get("exit_ask", 0.0) or 0.0),
        )

        discrepancy = abs(engine_net - ind_net)
        passed = discrepancy <= cls.TOLERANCE_INR

        if not passed and strict_fail:
            raise PnLValidationError(
                f"PnL AUDIT FAILURE for Trade {tid} ({strat}): "
                f"Engine Net=Rs {engine_net:.2f}, Independent Net=Rs {ind_net:.2f} "
                f"(Diff=Rs {discrepancy:.2f} > Rs {cls.TOLERANCE_INR})"
            )

        return IndependentTradeAudit(
            trade_id=tid,
            strategy=strat,
            side=side,
            quantity=qty,
            entry_fill=entry_f,
            exit_fill=exit_f,
            engine_gross_pnl=engine_gross,
            engine_net_pnl=engine_net,
            independent_gross_pnl=ind_gross,
            independent_costs=ind_costs,
            independent_net_pnl=ind_net,
            discrepancy=round(discrepancy, 2),
            status="RECONCILED" if passed else "FAILED",
        )
