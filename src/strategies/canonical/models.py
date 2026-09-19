"""
Canonical Trading Strategy Data Models and Schema.
Defines the machine-readable Single Source of Truth format required by
Sections 5 and 24 of the Canonical Indian Trading Strategy Benchmark Master Prompt.
"""
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class StrategyFamily(str, Enum):
    PRICE_ACTION = "PRICE_ACTION"
    TREND_FOLLOWING = "TREND_FOLLOWING"
    MOMENTUM = "MOMENTUM"
    MEAN_REVERSION = "MEAN_REVERSION"
    FUTURES = "FUTURES"
    OPTIONS_SPREAD = "OPTIONS_SPREAD"
    OPTIONS_VOLATILITY = "OPTIONS_VOLATILITY"
    PCR_OI = "PCR_OI"
    EXPIRY = "EXPIRY"
    OVERNIGHT = "OVERNIGHT"


class InstrumentClass(str, Enum):
    INDEX_FUTURE = "INDEX_FUTURE"
    STOCK_FUTURE = "STOCK_FUTURE"
    INDEX_OPTION = "INDEX_OPTION"
    STOCK_OPTION = "STOCK_OPTION"
    MULTI_LEG_OPTION = "MULTI_LEG_OPTION"


@dataclass
class CanonicalStrategyDefinition:
    """
    Standard, machine-readable specification for a canonical strategy.
    Shared identically between research backtests and paper trading engines.
    """
    name: str
    family: str
    instrument: str
    instrument_class: str
    timeframe: str
    source: str
    economic_mechanism: str
    entry_rules: Dict[str, Any]
    stop_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]
    target_rules: Optional[Dict[str, Any]] = None
    position_sizing: Dict[str, Any] = field(default_factory=lambda: {
        "unit": "LOTS",
        "lots": 1,
        "max_risk_pct_account": 0.60
    })
    capital_requirement: Dict[str, Any] = field(default_factory=lambda: {
        "rule": "PREMIUM_OR_SPAN_MARGIN",
        "minimum_account": 20000.0
    })
    execution_assumptions: Dict[str, Any] = field(default_factory=lambda: {
        "order_type": "MARKET_OR_LIMIT_AT_CLOSE",
        "slippage_model": "HALF_SPREAD_PLUS_TICKS",
        "cost_model": "INDIAN_STATUTORY_POST_OCT_2024"
    })

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d["family"], Enum):
            d["family"] = d["family"].value
        if isinstance(d["instrument_class"], Enum):
            d["instrument_class"] = d["instrument_class"].value
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalStrategyDefinition":
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "CanonicalStrategyDefinition":
        return cls.from_dict(json.loads(json_str))
