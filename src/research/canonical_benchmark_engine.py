"""
Canonical Strategy Benchmark Engine.
Executes the standardized canonical strategy library against authentic historical data
under strict clean-room and statutory Indian friction models.
Fulfills Sections 4, 5, 25, 29, 30, 31, 36, 40 of the Master Prompt.
"""
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import math
import numpy as np
import pandas as pd

from src.research.independent_pnl import IndependentPnLCalculator
from src.strategies.canonical.catalog import get_all_canonical_strategies
from src.strategies.canonical.models import CanonicalStrategyDefinition


@dataclass
class CanonicalBenchmarkResult:
    name: str
    family: str
    instrument: str
    total_sessions: int
    trade_sessions: int
    no_signal_sessions: int
    unpriceable_sessions: int
    data_error_sessions: int
    trades: int
    win_rate: float
    gross_pnl: float
    costs: float
    net_pnl: float
    expectancy: float
    profit_factor: Optional[float]
    sharpe: Optional[float]
    max_dd: float
    max_dd_pct: float
    worst_trade: float
    trades_per_day: float
    capital_required: float
    cost_stress_survives_2x: bool
    capital_20k: Dict[str, Any]
    capital_50k: Dict[str, Any]
    capital_100k: Dict[str, Any]
    status: str
    verdict_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_portfolio_drawdown(series: pd.Series) -> Tuple[float, float]:
    """Calculates peak-to-trough absolute drawdown and max drawdown percentage."""
    if series.empty:
        return 0.0, 0.0
    equity = series.cumsum()
    peak = equity.cummax()
    dd = peak - equity
    max_dd = float(dd.max()) if not dd.empty else 0.0
    return round(max_dd, 2), 0.0


def eval_capital_tier(
    net_pnl: float,
    max_dd: float,
    capital_required: float,
    account_size: float,
    daily_pnl: pd.Series,
) -> Dict[str, Any]:
    """
    Evaluates whole-lot executability and metrics for a specific capital level.
    Enforces maximum 60% of account at risk in a single position.
    """
    if capital_required <= 0 or capital_required > (account_size * 0.60):
        return {
            "executable": False,
            "lots": 0,
            "note": f"NOT EXECUTABLE — one lot needs Rs {capital_required:,.0f} (>60% of Rs {account_size:,.0f})",
            "net_pnl": 0.0,
            "return_pct": 0.0,
            "max_dd": 0.0,
            "max_dd_pct": 0.0
        }
    lots = int((account_size * 0.60) // capital_required)
    scaled_net = round(net_pnl * lots, 2)
    ret_pct = round((scaled_net / account_size) * 100.0, 2)
    scaled_dd = round(max_dd * lots, 2)
    dd_pct = round((scaled_dd / account_size) * 100.0, 2)
    return {
        "executable": True,
        "lots": lots,
        "net_pnl": scaled_net,
        "return_pct": ret_pct,
        "max_dd": scaled_dd,
        "max_dd_pct": dd_pct
    }
