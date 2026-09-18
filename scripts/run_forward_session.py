import os
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Config
from src.utils.logging import setup_logging
from src.execution.shadow_engine import ShadowEngine
from src.execution.dhan_contract_resolver import DhanContractResolver, is_quote_fresh
from src.execution.live_strategy_adapter import LiveStrategyAdapter
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.live_market_bars import get_today_session_bar

logger = setup_logging("scripts.run_forward_session")

def run_forward_session():
    """
    Orchestrates the live forward session.
    Bots 1, 5, 7 run in SHADOW mode.
    Bot 6 runs in PAPER mode.
    """
    logger.info("Initializing Live Shadow/Paper Forward Session...")
    Config.assert_no_live_trading()
    
    shadow_engine = ShadowEngine()
    paper_session = MultiBotLiveSession(auto_reconcile=False)
    adapter = LiveStrategyAdapter()
    
    bot_modes = {
        "Strategy 1: Apex VRP Engine": "SHADOW",
        "Strategy 2: Zen Curvature Overnight": "SHADOW",
        "Strategy 3: Confluence Gamma Scalper": "SHADOW",
        "Strategy 4: Golden Trend Runner": "SHADOW",
        "Strategy 5: Velocity-5 Momentum Scalper": "SHADOW",
        "Strategy 6: Micro Momentum Sniper": "PAPER",
        "Strategy 7: Discovery (None)": "SHADOW",
    }
    
    EOD_FLAT = dtime(15, 15)
    
    stats = {
        "cycles": 0,
        "stale_quotes": 0,
        "rejected_quotes": 0,
        "spread_warnings": 0,
        "risk_rejections": 0,
    }
    
    last_eval_time = {
        "Strategy 1: Apex VRP Engine": time.time(),
        "Strategy 5: Velocity-5 Momentum Scalper": time.time(),
        "Strategy 6: Micro Momentum Sniper": time.time(),
        "Strategy 7: Discovery (None)": time.time(),
    }
    
    logger.info("Entering active observation loop...")
    try:
        while True:
            now = datetime.now()
            now_time = now.time()
            
            if now_time > dtime(15, 30):
                logger.info("Market is closed. Terminating forward session.")
                break
                
            stats["cycles"] += 1
            
            # Fetch live market state for paper session
            market_state = paper_session.fetch_live_market_state()
            if not market_state:
                logger.warning("Market state unavailable. Retrying in 2s...")
                time.sleep(2)
                continue
                
            today_vix = market_state.get("vix")
            session_bar = get_today_session_bar("NIFTY")
            
            # Reset adapter cycle caches
            adapter.reset_cycle()
            
            # Evaluate all bots to get LiveSignals
            signals = {}
            for name in bot_modes.keys():
                sig = adapter.evaluate(name, session_bar=session_bar, today_vix=today_vix)
                signals[name] = sig
                if name in last_eval_time:
                    last_eval_time[name] = time.time()

            # Pre-fetch quotes for signal resolution
            active_quotes = {}
            
            # Because LiveSignal only gives direction and reason (not specific contract security_ids except for what we build)
            # We have to resolve the contract for the signal. 
            # In live_paper_session, contracts are manually resolved in if-blocks.
            # To simulate perfectly, we'll try to resolve ATM contracts for directional signals.
            n_last = market_state["nifty"]["last"]
            atm_k = round(n_last / 50.0) * 50.0
            
            for name, sig in signals.items():
                if sig and sig.is_actionable:
                    o_type = "CE" if sig.direction == 1 else "PE"
                    meta = DhanContractResolver.resolve_option_contract(n_last, today_vix, o_type, target_strike=atm_k)
                    if meta and meta.get("security_id"):
                        sec_id = str(meta["security_id"])
                        q = DhanContractResolver.get_quote(sec_id)
                        if q:
                            active_quotes[sec_id] = q
                            sig.contract_meta = meta # Attach for later
                            
            # Also pre-fetch quotes for open shadow positions
            for t_id, pos in shadow_engine.open_positions.items():
                sec_id = str(pos["security_id"])
                if sec_id not in active_quotes:
                    q = DhanContractResolver.get_quote(sec_id)
                    if q: active_quotes[sec_id] = q
            
            shadow_engine.update_open_positions(active_quotes)
            
            # Process Signals
            for name, sig in signals.items():
                mode = bot_modes.get(name, "SHADOW")
                
                # Check EOD flat conditions for shadow
                if now_time >= EOD_FLAT:
                    for t_id, pos in list(shadow_engine.open_positions.items()):
                        if pos["bot"] == name:
                            shadow_engine.close_position(t_id, "EOD_FLAT", active_quotes)
                            
                if not sig or not sig.is_actionable:
                    continue
                    
                meta = getattr(sig, "contract_meta", None)
                if not meta:
                    stats["rejected_quotes"] += 1
                    continue
                    
                sec_id = str(meta["security_id"])
                q = active_quotes.get(sec_id)
                
                if not q:
                    stats["rejected_quotes"] += 1
                    continue
                    
                fresh = is_quote_fresh(q.get("exchange_timestamp"))
                if not fresh:
                    stats["stale_quotes"] += 1
                    continue
                    
                bid, ask = q.get("bid", 0.0), q.get("ask", 0.0)
                if bid <= 0 or ask <= 0 or bid > ask:
                    stats["rejected_quotes"] += 1
                    continue
                    
                if (ask - bid) / ask > 0.05:
                    stats["spread_warnings"] += 1
                    
                action_str = "BUY" # Simplification for directional bots
                risk_res, risk_reason = paper_session.evaluate_entry_risk(
                    name, sec_id, 65, ask if action_str == "BUY" else bid
                )
                
                risk_decision = "APPROVED" if risk_res else "REJECTED"
                if not risk_res:
                    stats["risk_rejections"] += 1
                
                if mode == "SHADOW":
                    # Check if already in position
                    already_open = any(p["bot"] == name for p in shadow_engine.open_positions.values())
                    if not already_open:
                        shadow_engine.process_signal(
                            name, 
                            {"direction": action_str, "qty": 65, "underlying": "NIFTY", "confidence": sig.confidence}, 
                            q, 
                            risk_decision, 
                            risk_reason
                        )
                elif mode == "PAPER":
                    # For Bot 6, we would execute the paper trade, but we just delegate to MultiBotLiveSession
                    pass
                    
            # Let Paper Session evaluate its own loop for paper trades.
            paper_session.evaluate_all_bots(market_state, current_time=now.time())
            
            # Heartbeat reporting
            print(f"\n[{now.strftime('%H:%M:%S')}] CYCLE {stats['cycles']}", flush=True)
            print(f"Dhan: LIVE {market_state.get('timestamp', '--')}", flush=True)
            
            for bot_key, bot_label in [
                ("Strategy 1: Apex VRP Engine", "Bot1"),
                ("Strategy 5: Velocity-5 Momentum Scalper", "Bot5"),
                ("Strategy 6: Micro Momentum Sniper", "Bot6"),
                ("Strategy 7: Discovery (None)", "Bot7"),
            ]:
                mode = bot_modes.get(bot_key, "SHADOW")
                
                # Determine status
                status = "WAIT"
                if mode == "SHADOW":
                    if any(p["bot"] == bot_key for p in shadow_engine.open_positions.values()):
                        status = "IN_POSITION"
                else:
                    bs = paper_session.bot_states.get(bot_key, {})
                    if bs.get("active_trade") and bs["active_trade"].get("status") != "CLOSED":
                        status = "IN_POSITION"
                
                print(f"{bot_label}: {mode} / {status}", flush=True)
                
                # Freshness warning
                time_since_eval = time.time() - last_eval_time.get(bot_key, 0)
                if time_since_eval > 10:
                    print(f"WARNING: {bot_label} has not been evaluated in {time_since_eval:.1f} seconds!", flush=True)
                    
            time.sleep(2)
            
    except KeyboardInterrupt:
        logger.info("Forward session interrupted by user.")
        
    finally:
        logger.info("Generating final forward session report...")
        generate_forward_report(shadow_engine, stats, paper_session)

def generate_forward_report(shadow_engine: ShadowEngine, stats: dict, paper_session: MultiBotLiveSession):
    report_path = Path(f"reports/FORWARD_SESSION_{datetime.now().strftime('%Y-%m-%d')}.md")
    
    shadow_trades = list(shadow_engine.open_positions.values()) + shadow_engine.closed_positions
    total_shadow = len(shadow_trades)
    shadow_pnl = sum(t.get("would_be_net_pnl", 0.0) for t in shadow_trades)
    
    content = f"""# LIVE FORWARD OBSERVATION SESSION
Date: {datetime.now().strftime('%Y-%m-%d')}
LIVE_TRADING_ENABLED: FALSE

## METRICS
- Total Dhan Market-Data Cycles: {stats['cycles']}
- Stale Quotes Rejected: {stats['stale_quotes']}
- Missing/Inverted Quotes Rejected: {stats['rejected_quotes']}
- Spread Warnings (>5%): {stats['spread_warnings']}
- RiskEngine Rejections: {stats['risk_rejections']}

## SHADOW TRADES (HYPOTHETICAL)
- Total Shadow Trades: {total_shadow}
- Hypothetical Net P&L: Rs {shadow_pnl:,.2f}

"""
    for t in shadow_trades:
        content += f"- **{t['bot']}** | {t['signal']} {t['contract']} | Entry: {t['would_be_entry_price']} | Exit: {t.get('exit_fill', 'OPEN')} | Net: Rs {t.get('would_be_net_pnl', 0.0):,.2f} | MAE: Rs {t.get('mae', 0.0)} | MFE: Rs {t.get('mfe', 0.0)}\n"
        
    with open(report_path, "w") as f:
        f.write(content)
        
    logger.info(f"Report written to {report_path}")

if __name__ == "__main__":
    run_forward_session()
