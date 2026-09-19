"""
Deterministic Iron Condor Strategy.
Structure:
  BUY farther OTM PE (ATM - short_dist - wing)
  SELL nearer OTM PE (ATM - short_dist)
  SELL nearer OTM CE (ATM + short_dist)
  BUY farther OTM CE (ATM + short_dist + wing)
Defined risk credit spread with configurable distances and wings.
"""

from typing import Optional, Dict, Any
from datetime import datetime, time
import pandas as pd
from src.strategies.base_strategy import (
    BaseStrategy, MarketData, EntrySignal, PositionStructure, OptionLeg,
    OptionType, OrderSide
)


class IronCondorStrategy(BaseStrategy):
    """
    Iron Condor (OTM Strangle Short + Farther OTM Long Wings):
    - Defined risk multi-leg credit spread.
    - Sells OTM CE and PE at distance X, buys outer wings at distance X + wing.
    - Reduced margin requirement on NSE (~Rs 25,000 - 35,000/lot).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        cfg.setdefault("strategy_name", "IRON_CONDOR")
        cfg.setdefault("take_profit_pct", 0.40)
        cfg.setdefault("stop_loss_pct", 0.75)
        cfg.setdefault("entry_time", "09:20")
        cfg.setdefault("exit_time", "15:20")
        cfg.setdefault("short_distance", 100.0)
        cfg.setdefault("wing_width", 100.0)
        super().__init__(cfg)
        self.short_distance = float(self.config.get("short_distance", 100.0))
        self.wing_width = float(self.config.get("wing_width", 100.0))
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
            parameters={
                "spot": market_data.spot_price,
                "short_distance": self.short_distance,
                "wing_width": self.wing_width
            }
        )

    def build_position(self, market_data: MarketData, signal: EntrySignal) -> PositionStructure:
        atm = self.round_strike(market_data.spot_price)
        short_ce = atm + self.short_distance
        short_pe = atm - self.short_distance
        long_ce = short_ce + self.wing_width
        long_pe = short_pe - self.wing_width

        chain = market_data.chain
        expiry = market_data.expiry_date

        s_ce_row = chain[(chain["StrkPric"] == short_ce) & (chain["OptnTp"] == "CE")]
        s_pe_row = chain[(chain["StrkPric"] == short_pe) & (chain["OptnTp"] == "PE")]
        b_ce_row = chain[(chain["StrkPric"] == long_ce) & (chain["OptnTp"] == "CE")]
        b_pe_row = chain[(chain["StrkPric"] == long_pe) & (chain["OptnTp"] == "PE")]

        if s_ce_row.empty or s_pe_row.empty or b_ce_row.empty or b_pe_row.empty:
            pos = PositionStructure(strategy_name=self.name, underlying=self.underlying, expiry=expiry)
            pos.status = "REJECTED_MISSING_CONTRACT"
            return pos

        s_ce = s_ce_row.iloc[0]
        s_pe = s_pe_row.iloc[0]
        b_ce = b_ce_row.iloc[0]
        b_pe = b_pe_row.iloc[0]

        s_ce_px = float(s_ce["OpnPric"] if "OpnPric" in s_ce and s_ce["OpnPric"] > 0 else s_ce.get("open", s_ce.get("ClsPric", 0.0)))
        s_pe_px = float(s_pe["OpnPric"] if "OpnPric" in s_pe and s_pe["OpnPric"] > 0 else s_pe.get("open", s_pe.get("ClsPric", 0.0)))
        b_ce_px = float(b_ce["OpnPric"] if "OpnPric" in b_ce and b_ce["OpnPric"] > 0 else b_ce.get("open", b_ce.get("ClsPric", 0.0)))
        b_pe_px = float(b_pe["OpnPric"] if "OpnPric" in b_pe and b_pe["OpnPric"] > 0 else b_pe.get("open", b_pe.get("ClsPric", 0.0)))

        lot_size = int(s_ce.get("NewBrdLotQty", self.config.get("default_lot_size", 50)))
        net_credit = (s_ce_px + s_pe_px) - (b_ce_px + b_pe_px)
        max_loss_pts = max(0.0, self.wing_width - net_credit)

        legs = [
            OptionLeg(
                contract_id=str(b_pe.get("FinInstrmId", f"NIFTY_{expiry}_{long_pe}_PE")),
                contract_name=str(b_pe.get("FinInstrmNm", f"NIFTY {expiry} {long_pe} PE")),
                option_type=OptionType.PE,
                side=OrderSide.BUY,
                strike=long_pe,
                expiry=expiry,
                quantity=lot_size,
                entry_price=b_pe_px,
                entry_time=market_data.timestamp,
            ),
            OptionLeg(
                contract_id=str(s_pe.get("FinInstrmId", f"NIFTY_{expiry}_{short_pe}_PE")),
                contract_name=str(s_pe.get("FinInstrmNm", f"NIFTY {expiry} {short_pe} PE")),
                option_type=OptionType.PE,
                side=OrderSide.SELL,
                strike=short_pe,
                expiry=expiry,
                quantity=lot_size,
                entry_price=s_pe_px,
                entry_time=market_data.timestamp,
            ),
            OptionLeg(
                contract_id=str(s_ce.get("FinInstrmId", f"NIFTY_{expiry}_{short_ce}_CE")),
                contract_name=str(s_ce.get("FinInstrmNm", f"NIFTY {expiry} {short_ce} CE")),
                option_type=OptionType.CE,
                side=OrderSide.SELL,
                strike=short_ce,
                expiry=expiry,
                quantity=lot_size,
                entry_price=s_ce_px,
                entry_time=market_data.timestamp,
            ),
            OptionLeg(
                contract_id=str(b_ce.get("FinInstrmId", f"NIFTY_{expiry}_{long_ce}_CE")),
                contract_name=str(b_ce.get("FinInstrmNm", f"NIFTY {expiry} {long_ce} CE")),
                option_type=OptionType.CE,
                side=OrderSide.BUY,
                strike=long_ce,
                expiry=expiry,
                quantity=lot_size,
                entry_price=b_ce_px,
                entry_time=market_data.timestamp,
            ),
        ]

        margin_req = float(max_loss_pts * lot_size * 1.15)
        margin_req = max(margin_req, 20000.0)

        pos = PositionStructure(
            strategy_name=self.name,
            underlying=self.underlying,
            expiry=expiry,
            legs=legs,
            entry_time=market_data.timestamp,
            net_premium_points=net_credit,
            max_loss_points=max_loss_pts,
            max_profit_points=net_credit,
            margin_required=margin_req,
            lot_size=lot_size,
            take_profit_points=net_credit * self.take_profit_pct,
            stop_loss_points=net_credit * self.stop_loss_pct,
            status="OPEN",
            metadata={
                "atm": atm,
                "short_ce": short_ce,
                "short_pe": short_pe,
                "long_ce": long_ce,
                "long_pe": long_pe
            }
        )
        return pos
