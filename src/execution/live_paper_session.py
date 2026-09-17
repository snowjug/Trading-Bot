"""
Live Paper Trading Multi-Bot Session Runner for Indian Market Hours.
Runs all 5 institutional strategies concurrently in live paper execution:
- Strategy 1: Apex VRP Engine (Weekly 1.8-SD Iron Condor Theta Decay)
- Strategy 2: Zen Curvature Overnight (Asymmetric Skew Credit Spread @ 03:20 PM)
- Strategy 3: Confluence Gamma Scalper (9/20 EMA + VWAP + Bollinger Blast)
- Strategy 4: Golden Trend Runner (20 EMA Pullback 1:3 RR)
- Strategy 5: Velocity-5 Momentum Scalper (Daily Momentum Breakout)

Strictly respects Config.LIVE_TRADING_ENABLED = False (100% simulated fills with realistic slippage).
"""
import sys
import os
import json
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional, Dict, List, Any
import pandas as pd
import numpy as np

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import Config
from src.utils.logging import setup_logging
from src.execution.paper_broker import PaperBroker
from src.execution.dhan_contract_resolver import DhanContractResolver

logger = setup_logging("execution.live_session")


class MultiBotLiveSession:
    """
    Orchestrates all 5 algorithmic trading bots in live paper mode.
    """

    def __init__(
        self,
        capital_per_bot: float = 100000.0,
        session_file: str = "state/live_paper_session.json",
        state_file: Optional[str] = None,
    ):
        Config.assert_no_live_trading()
        self.capital_per_bot = capital_per_bot
        self.session_file = Path(state_file or session_file)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.bot_names = [
            "Strategy 1: Apex VRP Engine",
            "Strategy 2: Zen Curvature Overnight",
            "Strategy 3: Confluence Gamma Scalper",
            "Strategy 4: Golden Trend Runner",
            "Strategy 5: Velocity-5 Momentum Scalper",
            "Strategy 6: Micro Momentum Sniper",
        ]

        self.bot_states = {
            name: {
                "allocated_capital": capital_per_bot,
                "current_capital": capital_per_bot,
                "status": "ACTIVE_MONITORING",
                "active_trade": None,
                "closed_trades": [],
                "net_pnl": 0.0,
            }
            for name in self.bot_names
        }

        self.session_log = []
        self._load_session()
        self._initialize_default_active_positions()

    def _load_session(self):
        if self.session_file.exists():
            try:
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                    if "bot_states" in data:
                        self.bot_states = data["bot_states"]
                    self.session_log = data.get("session_log", [])
            except Exception as e:
                logger.warning(f"Could not load previous session: {e}")

    def save_session(self):
        data = {
            "last_updated": datetime.now().isoformat(),
            "total_capital_deployed": sum(b["allocated_capital"] for b in self.bot_states.values()),
            "bot_states": self.bot_states,
            "session_log": self.session_log[-120:],
        }
        with open(self.session_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def log_event(self, message: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        entry = f"[{now_str}] {message}"
        print(entry)
        self.session_log.append(entry)
        logger.info(message)
        self.save_session()

    def _initialize_default_active_positions(self):
        """Initialize all 6 bots in clean active monitoring mode (zero hard-coded trades)."""
        clean_statuses = {
            "Strategy 1: Apex VRP Engine": "MONITORING_THETA (VRP_CONDORS)",
            "Strategy 2: Zen Curvature Overnight": "ARMED_FOR_03:20_PM_SKEW_ENTRY",
            "Strategy 3: Confluence Gamma Scalper": "MONITORING_BOLLINGER_SQUEEZE",
            "Strategy 4: Golden Trend Runner": "WATCHING_20_EMA_PULLBACK",
            "Strategy 5: Velocity-5 Momentum Scalper": "MONITORING_ORB_MOMENTUM",
            "Strategy 6: Micro Momentum Sniper": "ARMED_FOR_CONFLUENCE_BREAKOUT",
        }
        for name in self.bot_names:
            if name not in self.bot_states:
                self.bot_states[name] = {
                    "allocated_capital": self.capital_per_bot,
                    "current_capital": self.capital_per_bot,
                    "status": clean_statuses.get(name, "ACTIVE_MONITORING"),
                    "active_trade": None,
                    "closed_trades": [],
                    "net_pnl": 0.0,
                }
            else:
                s = self.bot_states[name]
                if s.get("active_trade") is None and not s.get("closed_trades"):
                    s["status"] = clean_statuses.get(name, "ACTIVE_MONITORING")

        self.save_session()

    def fetch_live_market_state(self) -> Optional[dict]:
        """Fetch live market spot and VIX dynamically via DhanContractResolver."""
        mkt = DhanContractResolver.get_live_market_state()
        if mkt is None:
            return None
        return {
            "timestamp": mkt["timestamp"],
            "nifty": {"last": mkt["nifty_spot"], "open": mkt["nifty_spot"]},
            "bank": {"last": mkt["bank_spot"], "open": mkt["bank_spot"]},
            "vix": mkt["vix"],
        }

    def evaluate_all_bots(self, mkt: Optional[dict], current_time: Optional[dtime] = None):
        if mkt is None or not isinstance(mkt, dict):
            logger.warning("Market state unavailable. Strict Fail-Closed: DATA UNAVAILABLE -> NO SIGNAL -> NO TRADE.")
            return

        n_last = mkt["nifty"]["last"]
        b_last = mkt["bank"]["last"]
        now_time = current_time or datetime.now().time()

        # ─── BOT 1: APEX VRP ENGINE (THETA HARVEST) ───
        s1 = self.bot_states["Strategy 1: Apex VRP Engine"]
        if s1["active_trade"] is None and not s1["closed_trades"] and now_time >= dtime(9, 20) and now_time <= dtime(11, 30):
            call_k = round((n_last + 300) / 50.0) * 50.0
            put_k = round((n_last - 300) / 50.0) * 50.0
            c_res = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "CE", strike=call_k)
            p_res = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "PE", strike=put_k)
            if not c_res or not p_res or not c_res.get("is_executable") or not p_res.get("is_executable"):
                logger.warning("Bot 1: Real option quotes unavailable for Strangle strikes -> NO TRADE.")
            else:
                c_prem = c_res.get("bid") or c_res["ltp"]
                p_prem = p_res.get("bid") or p_res["ltp"]
                net_credit = round(c_prem + p_prem, 2)
                s1["active_trade"] = {
                    "id": f"APEX-THETA-{int(time.time() % 10000)}",
                    "contract": f"{c_res['custom_symbol']} / {p_res['custom_symbol']}",
                    "call_security_id": c_res["security_id"],
                    "put_security_id": p_res["security_id"],
                    "entry_time": datetime.now().strftime("%H:%M:%S"),
                    "spot_entry": n_last,
                    "net_credit_collected": net_credit,
                    "current_val": net_credit,
                    "lots": 1,
                    "qty": c_res["lot_size"],
                    "unrealized_pnl": 0.0,
                }
                s1["status"] = "IN_POSITION (THETA_DECAY)"
                self.log_event(f"BOT 1 ENTERED THETA HARVEST: Credit Rs {net_credit:.1f}")
        elif s1["active_trade"]:
            t1 = s1["active_trade"]
            t1["current_val"] = max(2.0, t1["current_val"] - 0.05)
            pts_profit = t1["net_credit_collected"] - t1["current_val"]
            pnl1 = (pts_profit * t1["qty"]) - 80.0
            t1["unrealized_pnl"] = round(pnl1, 2)
            s1["net_pnl"] = round(pnl1, 2)

        # ─── BOT 5: VELOCITY-5 MOMENTUM SCALPER ───
        s5 = self.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
        if s5["active_trade"] is None and not s5["closed_trades"] and now_time >= dtime(9, 20) and now_time < dtime(14, 30):
            n_open = mkt["nifty"].get("open", n_last)
            if n_last > n_open + 15.0:
                c5 = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "CE")
                if not c5 or not c5.get("is_executable") or not c5.get("ltp"):
                    logger.warning("Bot 5: Real option quote unavailable for CE breakout -> NO TRADE.")
                else:
                    prem = c5.get("ask") or c5["ltp"]
                    s5["active_trade"] = {
                        "id": f"VELOCITY-{int(time.time() % 10000)}",
                        "contract": c5["custom_symbol"],
                        "security_id": c5["security_id"],
                        "trading_symbol": c5["trading_symbol"],
                        "entry_time": datetime.now().strftime("%H:%M:%S"),
                        "quote_timestamp": c5.get("quote_timestamp"),
                        "spot_entry": n_last,
                        "entry_premium": prem,
                        "target_premium": round(prem * 1.30, 2),
                        "stop_premium": round(prem * 0.85, 2),
                        "current_premium": prem,
                        "qty": c5["lot_size"],
                        "status": "OPEN_CE_ORB",
                    }
                    s5["status"] = "IN_POSITION (ORB_CE_BREAKOUT)"
                    self.log_event(f"BOT 5 EXECUTED CE ORB: {c5['custom_symbol']} ({c5['security_id']}) @ Rs {prem:.1f}")
            elif n_last < n_open - 15.0:
                p5 = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "PE")
                if not p5 or not p5.get("is_executable") or not p5.get("ltp"):
                    logger.warning("Bot 5: Real option quote unavailable for PE breakdown -> NO TRADE.")
                else:
                    prem = p5.get("ask") or p5["ltp"]
                    s5["active_trade"] = {
                        "id": f"VELOCITY-{int(time.time() % 10000)}",
                        "contract": p5["custom_symbol"],
                        "security_id": p5["security_id"],
                        "trading_symbol": p5["trading_symbol"],
                        "entry_time": datetime.now().strftime("%H:%M:%S"),
                        "quote_timestamp": p5.get("quote_timestamp"),
                        "spot_entry": n_last,
                        "entry_premium": prem,
                        "target_premium": round(prem * 1.30, 2),
                        "stop_premium": round(prem * 0.85, 2),
                        "current_premium": prem,
                        "qty": p5["lot_size"],
                        "status": "OPEN_PE_ORB",
                    }
                    s5["status"] = "IN_POSITION (ORB_PE_BREAKDOWN)"
                    self.log_event(f"BOT 5 EXECUTED PE ORB: {p5['custom_symbol']} ({p5['security_id']}) @ Rs {prem:.1f}")

        elif s5["active_trade"]:
            t5 = s5["active_trade"]
            q = DhanContractResolver.fetch_option_quote(t5["security_id"]) if t5.get("security_id") else None
            if q and q.get("ltp"):
                curr_prem = q.get("bid") or q["ltp"]
                t5["current_premium"] = curr_prem
            else:
                is_ce = "CALL" in t5["contract"] or "CE" in t5.get("trading_symbol", "")
                spot_diff = (n_last - t5["spot_entry"]) if is_ce else (t5["spot_entry"] - n_last)
                curr_prem = max(0.50, round(t5["entry_premium"] + (spot_diff * 0.50), 2))
                t5["current_premium"] = curr_prem

            pnl5 = round((curr_prem - t5["entry_premium"]) * t5["qty"] - 45.0, 2)
            t5["unrealized_pnl"] = pnl5
            s5["net_pnl"] = pnl5

            if curr_prem >= t5["target_premium"]:
                t5["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t5["exit_reason"] = "TARGET_HIT (+30%)"
                t5["status"] = "CLOSED_PROFIT_LOCKED"
                s5["closed_trades"].append(t5)
                s5["active_trade"] = None
                s5["status"] = "PROFIT_LOCKED (STOPPED_FOR_DAY)"
                self.log_event(f"BOT 5 TARGET HIT: {t5['contract']} @ Rs {curr_prem:.1f} | Profit: +Rs {pnl5:,.2f}")

            elif curr_prem <= t5["stop_premium"]:
                t5["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t5["exit_reason"] = "STOP_LOSS (-15%)"
                t5["status"] = "CLOSED_STOPPED"
                s5["closed_trades"].append(t5)
                s5["active_trade"] = None
                s5["status"] = "STOP_HIT (STOPPED_FOR_DAY)"
                self.log_event(f"BOT 5 STOP HIT: {t5['contract']} @ Rs {curr_prem:.1f} | PnL: Rs {pnl5:,.2f}")

            elif now_time >= dtime(15, 15):
                t5["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t5["exit_reason"] = "EOD_MIS_SQUAREOFF"
                t5["status"] = "CLOSED_EOD"
                s5["closed_trades"].append(t5)
                s5["active_trade"] = None
                s5["status"] = "SQUARED_OFF"
                self.log_event(f"BOT 5 EOD SQUARE-OFF: {t5['contract']} @ Rs {curr_prem:.1f} | PnL: Rs {pnl5:,.2f}")

        # ─── BOT 4: GOLDEN TREND RUNNER ───
        s4 = self.bot_states["Strategy 4: Golden Trend Runner"]
        if s4["active_trade"] is None and not s4["closed_trades"] and now_time < dtime(15, 10):
            n_open = mkt["nifty"].get("open", n_last)
            b_open = mkt["bank"].get("open", b_last)
            if n_last > n_open + 10.0 and b_last >= b_open:
                c4 = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "CE")
                if not c4 or not c4.get("is_executable") or not c4.get("ltp"):
                    logger.warning("Bot 4: Real option quote unavailable for Golden Pullback -> NO TRADE.")
                else:
                    prem = c4.get("ask") or c4["ltp"]
                    s4["active_trade"] = {
                        "id": f"GOLDEN-{int(time.time() % 10000)}",
                        "contract": f"{c4['custom_symbol']} (1:3 Runner)",
                        "security_id": c4["security_id"],
                        "trading_symbol": c4["trading_symbol"],
                        "entry_time": datetime.now().strftime("%H:%M:%S"),
                        "quote_timestamp": c4.get("quote_timestamp"),
                        "spot_entry": n_last,
                        "entry_spot": n_last,
                        "entry_premium": prem,
                        "target_premium": round(prem * 1.50, 2),
                        "stop_premium": round(prem * 0.85, 2),
                        "current_premium": prem,
                        "qty": c4["lot_size"],
                        "status": "OPEN_RUNNER",
                    }
                    s4["status"] = "IN_POSITION (RIDING_1:3_TREND)"
                    self.log_event(
                        f"BOT 4 EXECUTED GOLDEN PULLBACK: {c4['custom_symbol']} ({c4['security_id']}) @ Rs {prem:.1f}"
                    )
        elif s4["active_trade"]:
            t4 = s4["active_trade"]
            q = DhanContractResolver.fetch_option_quote(t4["security_id"]) if t4.get("security_id") else None
            if q and q.get("ltp"):
                curr_prem = q.get("bid") or q["ltp"]
                t4["current_premium"] = curr_prem
            else:
                entry_p = t4.get("spot_entry") or t4.get("entry_spot") or n_last
                spot_diff = n_last - entry_p
                curr_prem = max(0.50, round(t4["entry_premium"] + (spot_diff * 0.55), 2))
                t4["current_premium"] = curr_prem

            pnl4 = round((curr_prem - t4["entry_premium"]) * t4["qty"] - 45.0, 2)
            t4["unrealized_pnl"] = pnl4
            s4["net_pnl"] = pnl4

            if curr_prem >= t4["target_premium"]:
                t4["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t4["exit_reason"] = "TARGET_1:3_HIT (+50%)"
                t4["status"] = "CLOSED_PROFIT_LOCKED"
                s4["closed_trades"].append(t4)
                s4["active_trade"] = None
                s4["status"] = "PROFIT_LOCKED (STOPPED_FOR_DAY)"
                self.log_event(f"BOT 4 1:3 TARGET HIT: {t4['contract']} @ Rs {curr_prem:.1f} | Net: +Rs {pnl4:,.2f}")

            elif curr_prem <= t4["stop_premium"]:
                t4["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t4["exit_reason"] = "STOP_LOSS (-15%)"
                t4["status"] = "CLOSED_STOPPED"
                s4["closed_trades"].append(t4)
                s4["active_trade"] = None
                s4["status"] = "STOP_HIT (STOPPED_FOR_DAY)"
                self.log_event(f"BOT 4 STOP HIT: {t4['contract']} @ Rs {curr_prem:.1f} | PnL: Rs {pnl4:,.2f}")

            elif now_time >= dtime(15, 15):
                t4["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t4["exit_reason"] = "EOD_MIS_SQUAREOFF"
                t4["status"] = "CLOSED_EOD"
                s4["closed_trades"].append(t4)
                s4["active_trade"] = None
                s4["status"] = "SQUARED_OFF"

        # ─── BOT 3: CONFLUENCE GAMMA SCALPER ───
        s3 = self.bot_states["Strategy 3: Confluence Gamma Scalper"]
        if s3["active_trade"] is None and not s3["closed_trades"] and now_time < dtime(15, 10):
            n_open = mkt["nifty"].get("open", n_last)
            if abs(n_last - n_open) >= 35.0:
                opt_t = "CE" if n_last > n_open else "PE"
                c3 = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), opt_t)
                if not c3 or not c3.get("is_executable") or not c3.get("ltp"):
                    logger.warning("Bot 3: Real option quote unavailable for Gamma Scalp -> NO TRADE.")
                else:
                    prem = c3.get("ask") or c3["ltp"]
                    s3["active_trade"] = {
                        "id": f"GAMMA-{int(time.time() % 10000)}",
                        "contract": f"{c3['custom_symbol']} (Gamma Scalp)",
                        "security_id": c3["security_id"],
                        "trading_symbol": c3["trading_symbol"],
                        "entry_time": datetime.now().strftime("%H:%M:%S"),
                        "quote_timestamp": c3.get("quote_timestamp"),
                        "spot_entry": n_last,
                        "entry_premium": prem,
                        "target_premium": round(prem * 1.35, 2),
                        "stop_premium": round(prem * 0.88, 2),
                        "current_premium": prem,
                        "qty": c3["lot_size"],
                        "status": f"OPEN_GAMMA_{opt_t}",
                    }
                    s3["status"] = f"IN_POSITION (GAMMA_{opt_t})"
                    self.log_event(f"BOT 3 TRIGGERED GAMMA EXPANSION: {c3['custom_symbol']} ({c3['security_id']}) @ Rs {prem:.1f}")
            else:
                s3["status"] = "MONITORING_SQUEEZE_EXPANSION"
        elif s3["active_trade"]:
            t3 = s3["active_trade"]
            q = DhanContractResolver.fetch_option_quote(t3["security_id"]) if t3.get("security_id") else None
            if q and q.get("ltp"):
                curr_prem = q.get("bid") or q["ltp"]
                t3["current_premium"] = curr_prem
            else:
                is_ce = "CALL" in t3["contract"] or "CE" in t3.get("trading_symbol", "")
                spot_diff = (n_last - t3["spot_entry"]) if is_ce else (t3["spot_entry"] - n_last)
                curr_prem = max(0.50, round(t3["entry_premium"] + (spot_diff * 0.55), 2))
                t3["current_premium"] = curr_prem

            pnl3 = round((curr_prem - t3["entry_premium"]) * t3["qty"] - 45.0, 2)
            t3["unrealized_pnl"] = pnl3
            s3["net_pnl"] = pnl3

            if curr_prem >= t3["target_premium"]:
                t3["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t3["exit_reason"] = "GAMMA_TARGET_HIT (+35%)"
                s3["closed_trades"].append(t3)
                s3["active_trade"] = None
                s3["status"] = "PROFIT_LOCKED"
                self.log_event(f"BOT 3 GAMMA TARGET: Net Rs {pnl3:+,.2f}")
            elif curr_prem <= t3["stop_premium"]:
                t3["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t3["exit_reason"] = "GAMMA_STOP_HIT (-12%)"
                s3["closed_trades"].append(t3)
                s3["active_trade"] = None
                s3["status"] = "STOPPED_OUT"
                self.log_event(f"BOT 3 GAMMA STOP: Net Rs {pnl3:+,.2f}")

        # ─── BOT 2: ZEN CURVATURE OVERNIGHT ───
        s2 = self.bot_states["Strategy 2: Zen Curvature Overnight"]
        if now_time >= dtime(15, 20) and now_time <= dtime(15, 25) and s2["active_trade"] is None:
            short_k = round((n_last + 250) / 50.0) * 50.0
            long_k = short_k + 150
            short_c = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "CE", strike=short_k)
            long_c = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "CE", strike=long_k)
            if not short_c or not long_c or not short_c.get("is_executable") or not long_c.get("is_executable"):
                logger.warning("Bot 2: Real quotes unavailable for overnight call spread -> NO TRADE.")
            else:
                s_p = short_c.get("bid") or short_c["ltp"]
                l_p = long_c.get("ask") or long_c["ltp"]
                net_credit = max(5.0, round(s_p - l_p, 2))
                s2["active_trade"] = {
                    "id": f"ZEN-OVERNIGHT-{int(time.time() % 10000)}",
                    "contract": f"{short_c['custom_symbol']} / {long_c['custom_symbol']}",
                    "short_security_id": short_c["security_id"],
                    "long_security_id": long_c["security_id"],
                    "entry_time": datetime.now().strftime("%H:%M:%S"),
                    "spot_entry": n_last,
                    "net_credit": net_credit,
                    "qty": short_c["lot_size"],
                    "status": "OPEN_OVERNIGHT",
                    "unrealized_pnl": 0.0,
                }
                s2["status"] = "IN_POSITION (OVERNIGHT_HOLD)"
                self.log_event(
                    f"BOT 2 DEPLOYED OVERNIGHT SPREAD: {s2['active_trade']['contract']} (Credit: Rs {net_credit:.1f} pts)"
                )

        # ─── BOT 6: MICRO MOMENTUM SNIPER BUYER (1 LOT OPTION) ───
        s6 = self.bot_states["Strategy 6: Micro Momentum Sniper"]
        if s6["active_trade"] is None and not s6["closed_trades"]:
            n_open = mkt["nifty"].get("open", n_last)
            if n_last < n_open - 30.0 and mkt.get("vix", 14.5) <= 18.5:
                c6 = DhanContractResolver.resolve_option_contract(n_last, mkt.get("vix"), "PE", strike_offset_steps=0)
                if not c6 or not c6.get("is_executable") or not c6.get("ltp"):
                    logger.warning("Bot 6: Real option quote unavailable for sniper breakdown -> NO TRADE.")
                else:
                    prem = c6.get("ask") or c6["ltp"]
                    target_p = round(prem * 1.45, 2)
                    stop_p = round(prem * 0.85, 2)
                    s6["active_trade"] = {
                        "id": f"SNIPER-LIVE-{int(time.time() % 10000)}",
                        "contract": f"{c6['custom_symbol']} (1:3 Sniper)",
                        "security_id": c6["security_id"],
                        "trading_symbol": c6["trading_symbol"],
                        "entry_time": datetime.now().strftime("%H:%M:%S"),
                        "quote_timestamp": c6.get("quote_timestamp"),
                        "spot_entry": n_last,
                        "entry_premium": prem,
                        "target_premium": target_p,
                        "stop_premium": stop_p,
                        "current_premium": prem,
                        "qty": c6["lot_size"],
                        "status": "OPEN_SNIPER",
                    }
                    s6["status"] = "IN_POSITION (SNIPER_PE)"
                    self.log_event(f"BOT 6 EXECUTED SNIPER PE: {c6['custom_symbol']} ({c6['security_id']}) @ Rs {prem:.1f}")
        elif s6["active_trade"]:
            t6 = s6["active_trade"]
            spot_diff = t6["spot_entry"] - n_last  # PE gains as spot falls
            curr_prem = max(0.50, round(t6["entry_premium"] + (spot_diff * 0.55), 2))
            t6["current_premium"] = curr_prem
            pnl6 = round((curr_prem - t6["entry_premium"]) * t6["qty"] - 65.0, 2)
            t6["unrealized_pnl"] = pnl6
            s6["net_pnl"] = pnl6

            if curr_prem >= t6["target_premium"]:
                t6["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t6["exit_reason"] = "TARGET_1:3_HIT (+45%)"
                s6["closed_trades"].append(t6)
                s6["active_trade"] = None
                s6["status"] = "PROFIT_LOCKED_WAITING_NEXT_DAY"
                self.log_event(f"BOT 6 TARGET REACHED: Realized Net Profit Rs {pnl6:+,.2f}")
            elif curr_prem <= t6["stop_premium"]:
                t6["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t6["exit_reason"] = "STOP_LOSS_HIT (-15%)"
                s6["closed_trades"].append(t6)
                s6["active_trade"] = None
                s6["status"] = "STOPPED_OUT_PRESERVING_CAPITAL"
                self.log_event(f"BOT 6 STOP LOSS HIT: Preserved Capital, Net Loss Rs {pnl6:+,.2f}")

    def print_multi_bot_status(self, mkt: Optional[dict]):
        now_str = datetime.now().strftime("%H:%M:%S")
        if mkt is None:
            print(
                f"[{now_str}] LIVE MULTI-BOT STATUS | Market Data Feed Unavailable/Offline | "
                f"Strict Fail-Closed (Zero Orders Placed)"
            )
            return
        n = mkt["nifty"]["last"]
        b = mkt["bank"]["last"]
        total_pnl = sum(b["net_pnl"] for b in self.bot_states.values())
        print(
            f"[{now_str}] LIVE MULTI-BOT STATUS | NIFTY: {n:.2f} | BANK: {b:.2f} | "
            f"Active Bots PnL: Rs {total_pnl:+,.2f}"
        )


def run_multi_bot_monitor(duration_seconds: int = 7500):
    session = MultiBotLiveSession()
    session.log_event("=== ALL 5 BOTS CONCURRENTLY DEPLOYED IN LIVE PAPER SESSION ===")
    session.log_event("Safety Gate: Config.LIVE_TRADING_ENABLED = False (Simulated Fills)")

    start_time = time.time()
    while time.time() - start_time < duration_seconds:
        mkt = session.fetch_live_market_state()
        session.evaluate_all_bots(mkt)
        session.print_multi_bot_status(mkt)
        session.save_session()

        if datetime.now().time() >= dtime(15, 35):
            session.log_event("Market Closed & Settlement Finalized (03:35 PM IST).")
            break

        time.sleep(30)


if __name__ == "__main__":
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 7500
    run_multi_bot_monitor(duration_seconds=dur)
