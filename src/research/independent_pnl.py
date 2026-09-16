"""
Independent P&L and Statutory Cost Reconciliation Engine.
Phase 28K & 28L Implementation.

Implements an isolated, second-source P&L calculator completely independent of the
primary backtesting engine. Cross-audits:
- Gross P&L
- Statutory Indian taxes (Post-Oct 2024 STT, GST 18%, Stamp Duty, Exchange & SEBI fees)
- Slippage friction
- Mathematical ledger reconciliation tolerance (< Rs 1.00 mismatch)
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


@dataclass
class TradeLedgerEntry:
    trade_id: str
    strategy: str
    signal_time: str
    decision_time: str
    order_time: str
    fill_time: str
    underlying: str
    contract_symbol: str
    quantity: int
    direction: str  # 'BUY' or 'SELL'
    entry_price: float
    exit_price: float
    gross_pnl: float
    brokerage: float
    stt: float
    gst: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    slippage: float
    total_costs: float
    net_pnl: float
    verification_status: str  # 'VERIFIED_REAL_CONTRACT', 'EOD_REPLAY', or 'UNVERIFIABLE'


class IndependentPnLCalculator:
    """
    Isolated P&L calculator implementing direct statutory tax schedules.
    Zero shared code or class inheritance from src/backtesting/cost_model.py.
    """

    # Post-Oct 2024 Indian Statutory Fee Schedule
    BROKERAGE_PER_ORDER = 20.0  # Rs 20 flat discount broker
    STT_OPTION_SELL_RATE = 0.0010  # 0.10% on options premium turnover (sell leg)
    STT_FUTURES_SELL_RATE = 0.0002  # 0.02% on futures turnover (sell leg)
    EXCHANGE_TURNOVER_RATE = 0.00035  # NSE: 0.035% of premium turnover
    SEBI_TURNOVER_RATE = 0.000001  # Rs 10 per Crore (0.0001%)
    STAMP_DUTY_BUY_RATE = 0.00003  # Rs 300 per Crore on buy turnover (0.003%)
    GST_RATE = 0.18  # 18% on (Brokerage + Exchange + SEBI)

    @classmethod
    def compute_trade_costs(
        cls,
        entry_price: float,
        exit_price: float,
        quantity: int,
        is_option: bool = True,
        slippage_pts: float = 0.5,
    ) -> dict:
        """Independently calculate penny-matched Indian transaction friction."""
        qty = abs(quantity)
        buy_turnover = entry_price * qty
        sell_turnover = exit_price * qty
        total_turnover = buy_turnover + sell_turnover

        # 1. Brokerage (Rs 20 buy + Rs 20 sell)
        brokerage = 2.0 * cls.BROKERAGE_PER_ORDER

        # 2. STT (levied on sell side only)
        stt_rate = cls.STT_OPTION_SELL_RATE if is_option else cls.STT_FUTURES_SELL_RATE
        stt = round(sell_turnover * stt_rate, 2)

        # 3. Exchange transaction fee (on both legs)
        exchange_charges = round(total_turnover * cls.EXCHANGE_TURNOVER_RATE, 2)

        # 4. SEBI turnover charges
        sebi_charges = round(total_turnover * cls.SEBI_TURNOVER_RATE, 4)

        # 5. Stamp duty (levied on buy leg only)
        stamp_duty = round(buy_turnover * cls.STAMP_DUTY_BUY_RATE, 2)

        # 6. GST (18% on Brokerage + Exchange + SEBI)
        gst_taxable = brokerage + exchange_charges + sebi_charges
        gst = round(gst_taxable * cls.GST_RATE, 2)

        # 7. Slippage friction
        slippage = round(slippage_pts * qty, 2)

        total_costs = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + slippage, 2)

        return {
            "brokerage": brokerage,
            "stt": stt,
            "exchange_charges": exchange_charges,
            "sebi_charges": sebi_charges,
            "stamp_duty": stamp_duty,
            "gst": gst,
            "slippage": slippage,
            "total_costs": total_costs,
        }

    @classmethod
    def calculate_trade_pnl(
        cls,
        entry_price: float,
        exit_price: float,
        quantity: int,
        is_long: bool = True,
        is_option: bool = True,
        slippage_pts: float = 0.5,
    ) -> Tuple[float, dict, float]:
        """Compute gross P&L, independent costs, and net P&L."""
        qty = abs(quantity)
        gross_pnl = round((exit_price - entry_price) * qty if is_long else (entry_price - exit_price) * qty, 2)
        costs = cls.compute_trade_costs(entry_price, exit_price, qty, is_option, slippage_pts)
        net_pnl = round(gross_pnl - costs["total_costs"], 2)
        return gross_pnl, costs, net_pnl

    @classmethod
    def reconcile_trade(
        cls,
        primary_gross: float,
        primary_costs: float,
        primary_net: float,
        independent_gross: float,
        independent_costs: float,
        independent_net: float,
        tolerance: float = 1.00,
    ) -> Tuple[bool, str]:
        """Check if primary engine matches independent engine within tolerance."""
        gross_diff = abs(primary_gross - independent_gross)
        cost_diff = abs(primary_costs - independent_costs)
        net_diff = abs(primary_net - independent_net)

        if gross_diff > tolerance or cost_diff > tolerance or net_diff > tolerance:
            err = f"Mismatch! Gross diff: Rs {gross_diff:.2f}, Cost diff: Rs {cost_diff:.2f}, Net diff: Rs {net_diff:.2f}"
            return False, err
        return True, "MATCH"
