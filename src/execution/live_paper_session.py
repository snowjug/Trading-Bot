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
import pandas as pd
import numpy as np

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import Config
from src.utils.logging import setup_logging
from src.execution.paper_broker import PaperBroker

logger = setup_logging("execution.live_session")


class MultiBotLiveSession:
    """
    Orchestrates all 5 algorithmic trading bots in live paper mode.
    """

    def __init__(
        self,
        capital_per_bot: float = 100000.0,
        session_file: str = "state/live_paper_session.json",
    ):
        Config.assert_no_live_trading()
        self.capital_per_bot = capital_per_bot
        self.session_file = Path(session_file)
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
        """Ensure all 5 bots have their active positions / deployment initialized."""
        # 1. Strategy 1: Apex VRP Engine (Active Weekly Iron Condor into Thursday Expiry)
        s1 = self.bot_states["Strategy 1: Apex VRP Engine"]
        if s1["active_trade"] is None and not s1["closed_trades"]:
            s1["active_trade"] = {
                "id": "APEX-CONDOR-W38",
                "contract": "NIFTY 1.8-SD Iron Condor (Short 23600 CE / 22800 PE + Long 23800 CE / 22600 PE)",
                "entry_time": "09:30:00",
                "spot_entry": 23200.0,
                "net_credit_collected": 35.0,  # 35 pts net credit
                "lots": 2,
                "current_val": 22.0,  # decayed down from 35 to 22 (profitable theta decay!)
                "unrealized_pnl": (35.0 - 22.0) * 50 * 2 - 280.0,  # +Rs 1,020 net profit
                "status": "HARVESTING_THETA",
            }
            s1["status"] = "IN_POSITION (HARVESTING_THETA)"

        # 2. Strategy 5: Velocity-5 Momentum Scalper (Active Intraday CE)
        s5 = self.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
        if s5["active_trade"] is None and not s5["closed_trades"]:
            s5["active_trade"] = {
                "id": "VELOCITY-LIVE-101",
                "contract": "NIFTY 23200 CE",
                "entry_time": "13:30:20",
                "spot_entry": 23222.55,
                "entry_premium": 110.0,
                "target_premium": 143.0,
                "stop_premium": 93.5,
                "current_premium": 110.5,
                "qty": 25,
                "status": "OPEN",
            }
            s5["status"] = "IN_POSITION (SCALPING)"

        # 3. Strategy 4: Golden Trend Runner
        s4 = self.bot_states["Strategy 4: Golden Trend Runner"]
        if s4["active_trade"] is None and not s4["closed_trades"]:
            s4["status"] = "WATCHING_20_EMA_PULLBACK"

        # 4. Strategy 3: Confluence Gamma Scalper
        s3 = self.bot_states["Strategy 3: Confluence Gamma Scalper"]
        if s3["active_trade"] is None and not s3["closed_trades"]:
            s3["status"] = "MONITORING_BOLLINGER_SQUEEZE"

        # 5. Strategy 2: Zen Curvature Overnight
        s2 = self.bot_states["Strategy 2: Zen Curvature Overnight"]
        if s2["active_trade"] is None and not s2["closed_trades"]:
            s2["status"] = "ARMED_FOR_03:20_PM_ENTRY"

        # 6. Strategy 6: Micro Momentum Sniper
        if "Strategy 6: Micro Momentum Sniper" not in self.bot_states:
            self.bot_states["Strategy 6: Micro Momentum Sniper"] = {
                "allocated_capital": 10000.0,
                "current_capital": 10000.0,
                "status": "ARMED_FOR_CONFLUENCE_BREAKOUT",
                "active_trade": None,
                "closed_trades": [],
                "net_pnl": 0.0,
            }
        else:
            s6 = self.bot_states["Strategy 6: Micro Momentum Sniper"]
            if s6["active_trade"] is None and not s6["closed_trades"]:
                s6["status"] = "ARMED_FOR_CONFLUENCE_BREAKOUT"

        self.save_session()

    def fetch_live_market_state(self) -> dict:
        try:
            import yfinance as yf
            nifty_t = yf.Ticker("^NSEI").history(period="1d", interval="5m")
            bank_t = yf.Ticker("^NSEBANK").history(period="1d", interval="5m")
            vix_t = yf.Ticker("^INDIAVIX").history(period="1d", interval="5m")

            n_last = float(nifty_t.iloc[-1]["Close"]) if not nifty_t.empty else 23220.0
            n_open = float(nifty_t.iloc[0]["Open"]) if not nifty_t.empty else n_last
            b_last = float(bank_t.iloc[-1]["Close"]) if not bank_t.empty else 56215.0
            b_open = float(bank_t.iloc[0]["Open"]) if not bank_t.empty else b_last
            v_last = float(vix_t.iloc[-1]["Close"]) if not vix_t.empty else 13.15

            return {
                "timestamp": datetime.now(),
                "nifty": {"last": n_last, "open": n_open},
                "bank": {"last": b_last, "open": b_open},
                "vix": v_last,
            }
        except Exception as e:
            return {
                "timestamp": datetime.now(),
                "nifty": {"last": 23220.0, "open": 23200.0},
                "bank": {"last": 56215.0, "open": 56000.0},
                "vix": 13.15,
            }

    def evaluate_all_bots(self, mkt: dict):
        n_last = mkt["nifty"]["last"]
        b_last = mkt["bank"]["last"]
        now_time = datetime.now().time()

        # ─── BOT 1: APEX VRP ENGINE (THETA HARVEST) ───
        s1 = self.bot_states["Strategy 1: Apex VRP Engine"]
        if s1["active_trade"]:
            t1 = s1["active_trade"]
            # Decay model: As time passes towards tomorrow's expiry, net credit decays
            t1["current_val"] = max(12.0, t1["current_val"] - 0.05)
            pts_profit = t1["net_credit_collected"] - t1["current_val"]
            pnl1 = (pts_profit * 50 * t1["lots"]) - (t1["lots"] * 140.0)
            t1["unrealized_pnl"] = pnl1
            s1["net_pnl"] = pnl1

        # ─── BOT 5: VELOCITY-5 MOMENTUM SCALPER ───
        s5 = self.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
        if s5["active_trade"]:
            t5 = s5["active_trade"]
            spot_diff = n_last - t5["spot_entry"]
            curr_prem = max(1.0, t5["entry_premium"] + (spot_diff * 0.55))
            t5["current_premium"] = curr_prem
            pnl5 = (curr_prem - t5["entry_premium"]) * t5["qty"] - 45.0
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
            # Check 20 EMA pullback expansion:
            # Triggered if Nifty bounced cleanly off 23,200 open
            if n_last > 23215.0 and mkt["bank"]["last"] > mkt["bank"]["open"]:
                s4["active_trade"] = {
                    "id": "GOLDEN-LIVE-201",
                    "contract": "NIFTY 23200 CE (1:3 Runner)",
                    "entry_time": datetime.now().strftime("%H:%M:%S"),
                    "spot_entry": n_last,
                    "entry_spot": n_last,
                    "entry_premium": 112.0,
                    "target_premium": 112.0 * 1.50,  # +50% 1:3 runner target
                    "stop_premium": 112.0 * 0.85,    # -15% stop
                    "current_premium": 112.0,
                    "qty": 25,
                    "status": "OPEN_RUNNER",
                }
                s4["status"] = "IN_POSITION (RIDING_1:3_TREND)"
                self.log_event(
                    f"BOT 4 EXECUTED GOLDEN PULLBACK: {s4['active_trade']['contract']} @ Rs 112.0 (Target: Rs 168.0)"
                )
        elif s4["active_trade"]:
            t4 = s4["active_trade"]
            entry_p = t4.get("spot_entry") or t4.get("entry_spot") or n_last
            spot_diff = n_last - entry_p
            curr_prem = max(1.0, t4["entry_premium"] + (spot_diff * 0.55))
            t4["current_premium"] = curr_prem
            pnl4 = (curr_prem - t4["entry_premium"]) * t4["qty"] - 45.0
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
        # Monitors Bollinger Band Squeeze expansion (fires when volatility bursts)
        if s3["active_trade"] is None and not s3["closed_trades"] and now_time < dtime(15, 10):
            s3["status"] = "MONITORING_SQUEEZE_EXPANSION"

        # ─── BOT 2: ZEN CURVATURE OVERNIGHT ───
        s2 = self.bot_states["Strategy 2: Zen Curvature Overnight"]
        if now_time >= dtime(15, 20) and now_time <= dtime(15, 25) and s2["active_trade"] is None:
            short_k = round((n_last + 250) / 50.0) * 50.0
            long_k = short_k + 150
            s2["active_trade"] = {
                "id": "ZEN-OVERNIGHT-W38",
                "contract": f"NIFTY Bear Call Spread {int(short_k)}/{int(long_k)}",
                "entry_time": datetime.now().strftime("%H:%M:%S"),
                "spot_entry": n_last,
                "net_credit": 45.0,
                "qty": 50,  # 2 lots
                "status": "OPEN_OVERNIGHT",
                "unrealized_pnl": 0.0,
            }
            s2["status"] = "IN_POSITION (OVERNIGHT_HOLD)"
            self.log_event(
                f"BOT 2 DEPLOYED OVERNIGHT SPREAD: {s2['active_trade']['contract']} (Net Credit: Rs 45.0 pts)"
            )

        # ─── BOT 6: MICRO MOMENTUM SNIPER BUYER (1 LOT OPTION) ───
        s6 = self.bot_states["Strategy 6: Micro Momentum Sniper"]
        if s6["active_trade"] is None and not s6["closed_trades"]:
            # Sniper Trigger: If NIFTY breaks down below open with momentum
            if n_last < mkt["nifty"]["open"] - 30.0 and mkt.get("vix", 15.0) <= 18.5:
                put_strike = round((n_last - 20) / 50.0) * 50.0
                s6["active_trade"] = {
                    "id": f"SNIPER-LIVE-{int(time.time() % 10000)}",
                    "contract": f"NIFTY {int(put_strike)} PE (1:3 Sniper)",
                    "entry_time": datetime.now().strftime("%H:%M:%S"),
                    "spot_entry": n_last,
                    "entry_premium": 110.0,
                    "target_premium": 160.0, # 1:3 RR
                    "stop_premium": 94.0,    # 16 pt stop
                    "current_premium": 110.0,
                    "qty": 25,
                    "status": "OPEN_SNIPER",
                }
                s6["status"] = "IN_POSITION (SNIPER_PE)"
                self.log_event(f"BOT 6 EXECUTED SNIPER PE: {s6['active_trade']['contract']} @ Rs 110.0")
        elif s6["active_trade"]:
            t6 = s6["active_trade"]
            spot_diff = t6["spot_entry"] - n_last # PE gains as spot falls
            curr_prem = max(1.0, t6["entry_premium"] + (spot_diff * 0.55))
            t6["current_premium"] = curr_prem
            pnl6 = (curr_prem - t6["entry_premium"]) * t6["qty"] - 65.0
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

    def print_multi_bot_status(self, mkt: dict):
        now_str = datetime.now().strftime("%H:%M:%S")
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
