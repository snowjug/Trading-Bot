import time
from datetime import datetime
import pandas as pd
from typing import Dict, List, Optional
from pathlib import Path
from src.execution.cost_model import IndianCostModel
from src.utils.logging import setup_logging

logger = setup_logging("execution.shadow")

class ShadowEngine:
    """
    Evaluates trading signals hypothetically without consuming paper capital.
    Continuously tracks Maximum Adverse Excursion (MAE), Maximum Favorable Excursion (MFE), 
    and hypothetical P&L against live authentic Bid/Ask prices.
    """
    def __init__(self, data_dir: str = "data/forward"):
        self.data_dir = Path(data_dir)
        self.session_dir = self.data_dir / datetime.now().strftime("%Y-%m-%d")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.shadow_log_path = self.session_dir / "shadow_trades.csv"
        self.open_positions: Dict[str, dict] = {}
        self.closed_positions: List[dict] = []
        self._load_state()

    def _load_state(self):
        if self.shadow_log_path.exists():
            try:
                df = pd.read_csv(self.shadow_log_path)
                for _, row in df.iterrows():
                    d = row.to_dict()
                    if d.get("status") == "OPEN":
                        self.open_positions[d["id"]] = d
                    else:
                        self.closed_positions.append(d)
            except Exception as e:
                logger.error(f"Failed to load shadow state: {e}")

    def _save_state(self):
        all_trades = list(self.open_positions.values()) + self.closed_positions
        if not all_trades:
            return
        df = pd.DataFrame(all_trades)
        df.to_csv(self.shadow_log_path, index=False)

    def process_signal(self, bot: str, signal: dict, quote: dict, risk_decision: str, reason: str):
        """
        Record a shadow signal. If accepted by Risk, open a hypothetical position.
        """
        # signal format follows LiveSignal or dict from the orchestrator
        ts = datetime.now().strftime("%H:%M:%S")
        direction = signal.get("direction", "BUY")
        qty = signal.get("qty", 65)
        
        bid, ask = quote.get("bid", 0.0), quote.get("ask", 0.0)
        
        would_be_price = ask if direction == "BUY" else bid
        
        if risk_decision == "APPROVED" and would_be_price > 0:
            trade_id = f"SHADOW_{int(time.time()*1000)}_{bot.replace(' ', '_')}"
            self.open_positions[trade_id] = {
                "id": trade_id,
                "timestamp": ts,
                "bot": bot,
                "signal": direction,
                "confidence": signal.get("confidence", 1.0),
                "underlying": signal.get("underlying", "NIFTY"),
                "contract": quote.get("trading_symbol", "UNKNOWN"),
                "security_id": quote.get("security_id", "NONE"),
                "expiry": quote.get("expiry", "UNKNOWN"),
                "strike": quote.get("strike", 0.0),
                "option_type": quote.get("option_type", "CE"),
                "theoretical_entry_timestamp": ts,
                "entry_bid": bid,
                "entry_ask": ask,
                "entry_mid": round((bid + ask) / 2.0, 2) if bid and ask else 0.0,
                "would_be_entry_price": would_be_price,
                "would_be_quantity": qty,
                "risk_decision": risk_decision,
                "reason": reason,
                "mae": 0.0,
                "mfe": 0.0,
                "status": "OPEN",
                "would_be_gross_pnl": 0.0,
                "would_be_costs": 0.0,
                "would_be_net_pnl": 0.0,
                "holding_duration_secs": 0,
                "exit_timestamp": None,
                "exit_reason": None,
                "exit_fill": None
            }
            logger.info(f"[SHADOW] {bot} entered {trade_id} @ {would_be_price}")
        else:
            logger.info(f"[SHADOW] {bot} REJECTED: {reason}")
        self._save_state()

    def update_open_positions(self, quotes: Dict[str, dict]):
        """
        Evaluate all open shadow positions against the latest quotes to update MAE/MFE and unrealized P&L.
        """
        now = datetime.now()
        for t_id, pos in list(self.open_positions.items()):
            sec_id = pos["security_id"]
            q = quotes.get(str(sec_id))
            if not q:
                continue
            
            bid, ask = q.get("bid", 0.0), q.get("ask", 0.0)
            if bid <= 0 or ask <= 0:
                continue
                
            entry_price = pos["would_be_entry_price"]
            qty = pos["would_be_quantity"]
            side = pos["signal"]
            
            current_price = bid if side == "BUY" else ask
            
            gross = (current_price - entry_price) * qty if side == "BUY" else (entry_price - current_price) * qty
            
            if gross > pos["mfe"]:
                pos["mfe"] = round(gross, 2)
            if gross < pos["mae"]:
                pos["mae"] = round(gross, 2)
                
            pos["would_be_gross_pnl"] = round(gross, 2)
            costs = IndianCostModel.calculate_roundtrip_costs(entry_price, current_price, qty).total_costs
            pos["would_be_costs"] = round(costs, 2)
            pos["would_be_net_pnl"] = round(gross - costs, 2)
            
            entry_t = datetime.strptime(pos["theoretical_entry_timestamp"], "%H:%M:%S")
            now_t = datetime.strptime(now.strftime("%H:%M:%S"), "%H:%M:%S")
            pos["holding_duration_secs"] = int((now_t - entry_t).total_seconds())

        self._save_state()

    def close_position(self, t_id: str, reason: str, quotes: Dict[str, dict]):
        if t_id not in self.open_positions:
            return
            
        pos = self.open_positions[t_id]
        sec_id = pos["security_id"]
        q = quotes.get(str(sec_id))
        
        bid = q.get("bid", 0.0) if q else 0.0
        ask = q.get("ask", 0.0) if q else 0.0
        
        side = pos["signal"]
        exit_fill = None
        if side == "BUY" and bid > 0:
            exit_fill = bid
        elif side == "SELL" and ask > 0:
            exit_fill = ask
            
        if exit_fill is None or exit_fill <= 0:
            pos["status"] = "UNRESOLVED_EOD"
            pos["exit_reason"] = "NO_EXECUTABLE_QUOTE"
        else:
            pos["exit_timestamp"] = datetime.now().strftime("%H:%M:%S")
            pos["exit_reason"] = reason
            pos["status"] = "CLOSED"
            pos["exit_fill"] = exit_fill
            
            qty = pos["would_be_quantity"]
            entry_price = pos["would_be_entry_price"]
            
            gross = (exit_fill - entry_price) * qty if side == "BUY" else (entry_price - exit_fill) * qty
            costs = IndianCostModel.calculate_roundtrip_costs(entry_price, exit_fill, qty).total_costs
            
            pos["would_be_gross_pnl"] = round(gross, 2)
            pos["would_be_costs"] = round(costs, 2)
            pos["would_be_net_pnl"] = round(gross - costs, 2)
            
        self.closed_positions.append(pos)
        del self.open_positions[t_id]
        logger.info(f"[SHADOW] Closed {t_id}: Net P&L Rs {pos['would_be_net_pnl']} ({reason})")
        self._save_state()
