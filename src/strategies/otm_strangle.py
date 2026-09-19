"""
Deterministic OTM Strangle Strategy.
Structure: SELL OTM CE + SELL OTM PE.
Configurable predetermined strike distance (50, 100, 150, 200 points).
"""

from typing import Optional, Dict, Any
from datetime import datetime, time
import pandas as pd
from src.strategies.base_strategy import (
    BaseStrategy, MarketData, EntrySignal, PositionStructure, OptionLeg,
    OptionType, OrderSide
)


class OTMStrangleStrategy(BaseStrategy):
    """
    OTM Strangle:
    - At entry time, identifies ATM and adds/subtracts strike distance.
    - Sells 1 lot OTM CE (ATM + distance) and 1 lot OTM PE (ATM - distance).
    - Collects net credit.
    - Naked short premium requiring ~Rs 1.25L - 1.40L margin on NSE.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        cfg.setdefault("strategy_name", "OTM_STRANGLE")
        cfg.setdefault("take_profit_pct", 0.40)
        cfg.setdefault("stop_loss_pct", 0.75)
        cfg.setdefault("entry_time", "09:20")
        cfg.setdefault("exit_time", "15:20")
        cfg.setdefault("strike_distance", 100.0)  # 50, 100, 150, 200
        super().__init__(cfg)
        self.strike_distance = float(self.config.get("strike_distance", 100.0))
        self.entry_time_str = self.config.get("entry_time", "09:20")
        self.entry_hour, self.entry_min = map(int, self.entry_time_str.split(":"))

    def check_entry(self, market_data: MarketData) -> Optional[EntrySignal]:
        cur_time = market_data.timestamp.time()
        if cur_time.hour != self.entry_hour or cur_time.minute != self.entry_min:
            if not (self.entry_hour == 9 and self.entry_min <= 15 and cur_time.hour == 9 and cur_time.minute <= 20):
                return None

        if self.vix_filter_max > 0 and market_data.vix > self.vix_filter_max:
            return None

        if market_data.chain is None or market_data.chain.empty:
            return None

        return EntrySignal(
            strategy_name=self.name,
            underlying=self.underlying,
            timestamp=market_data.timestamp,
            parameters={"spot": market_data.spot_price, "strike_distance": self.strike_distance}
        )

    def build_position(self, market_data: MarketData, signal: EntrySignal) -> PositionStructure:
        atm_strike = self.round_strike(market_data.spot_price)
        ce_strike = atm_strike + self.strike_distance
        pe_strike = atm_strike - self.strike_distance
        chain = market_data.chain
        expiry = market_data.expiry_date

        ce_row = chain[(chain["StrkPric"] == ce_strike) & (chain["OptnTp"] == "CE")]
        pe_row = chain[(chain["StrkPric"] == pe_strike) & (chain["OptnTp"] == "PE")]

        if ce_row.empty or pe_row.empty:
            pos = PositionStructure(strategy_name=self.name, underlying=self.underlying, expiry=expiry)
            pos.status = "REJECTED_MISSING_CONTRACT"
            return pos

        ce_r = ce_row.iloc[0]
        pe_r = pe_row.iloc[0]

        ce_px = float(ce_r["OpnPric"] if "OpnPric" in ce_r and ce_r["OpnPric"] > 0 else ce_r.get("open", ce_r.get("ClsPric", 0.0)))
        pe_px = float(pe_r["OpnPric"] if "OpnPric" in pe_r and pe_r["OpnPric"] > 0 else pe_r.get("open", pe_r.get("ClsPric", 0.0)))

        lot_size = int(ce_r.get("NewBrdLotQty", self.config.get("default_lot_size", 50)))
        net_credit = ce_px + pe_px

        legs = [
            OptionLeg(
                contract_id=str(ce_r.get("FinInstrmId", f"NIFTY_{expiry}_{ce_strike}_CE")),
                contract_name=str(ce_r.get("FinInstrmNm", f"NIFTY {expiry} {ce_strike} CE")),
                option_type=OptionType.CE,
                side=OrderSide.SELL,
                strike=ce_strike,
                expiry=expiry,
                quantity=lot_size,
                entry_price=ce_px,
                entry_time=market_data.timestamp,
            ),
            OptionLeg(
                contract_id=str(pe_r.get("FinInstrmId", f"NIFTY_{expiry}_{pe_strike}_PE")),
                contract_name=str(pe_r.get("FinInstrmNm", f"NIFTY {expiry} {pe_strike} PE")),
                option_type=OptionType.PE,
                side=OrderSide.SELL,
                strike=pe_strike,
                expiry=expiry,
                quantity=lot_size,
                entry_price=pe_px,
                entry_time=market_data.timestamp,
            )
        ]

        margin_req = float(self.config.get("margin_required_per_lot", 130000.0))

        pos = PositionStructure(
            strategy_name=self.name,
            underlying=self.underlying,
            expiry=expiry,
            legs=legs,
            entry_time=market_data.timestamp,
            net_premium_points=net_credit,
            max_loss_points=net_credit * 2.5,
            max_profit_points=net_credit,
            margin_required=margin_req,
            lot_size=lot_size,
            take_profit_points=net_credit * self.take_profit_pct,
            stop_loss_points=net_credit * self.stop_loss_pct,
            status="OPEN",
            metadata={"atm": atm_strike, "ce_strike": ce_strike, "pe_strike": pe_strike}
        )
        return pos
