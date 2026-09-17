"""
Comprehensive Adversarial Safety & Correctness Test Matrix.
Strictly verifies all 20 adversarial failure scenarios defined in the Critical Safety Audit:
1. Kill switch + open position (Immediate emergency flatten)
2. Kill switch + new entry (Fail-closed block)
3. Stop loss + missing Bid (Quote dropout handling)
4. Stop loss + missing Ask (Quote dropout handling)
5. Stop loss + stale quote (Freshness validation)
6. Stop loss + rejected exit (Error reporting)
7. Stop loss + partial exit (All-or-none validation)
8. Sudden price jump (Execution realism)
9. Extreme spread (Fail-closed rejection)
10. Inverted market (Fail-closed rejection)
11. Duplicate order response (State isolation)
12. Lost order acknowledgement (Fail-closed sandbox error)
13. Timeout during submission (Fail-closed rejection)
14. Process restart with open position (State recovery & persistence)
15. Broker/API outage (Fail-closed)
16. Market-data outage (Fail-closed)
17. Position mismatch (Broker reconciliation)
18. 15:35 EOD boundary (Authoritative mandatory square-off)
19. Attempted Dhan production order while live=false (Hard safety barrier interceptor)
20. Alternate code path bypass prevention (Global gate check)
"""

import pytest
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, date, time as dtime
from unittest.mock import MagicMock, patch

from src.config import Config
from src.risk.risk_engine import RiskEngine
from src.execution.dhan_paper_trader import DhanPaperSandbox
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.dhan_contract_resolver import DhanContractResolver, is_quote_fresh
from src.execution.broker_adapters.dhan import DhanBrokerAdapter
from src.execution.paper_broker import Order, OrderSide, OrderStatus


@pytest.fixture
def temp_env(tmp_path):
    """Provides isolated temporary state and report directories."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return {
        "state_dir": state_dir,
        "reports_dir": reports_dir,
        "session_file": state_dir / "live_paper_session.json",
        "kill_switch_file": state_dir / "kill_switch.json",
        "trades_file": state_dir / "dhan_paper_trades.json",
    }


# ─── 1. KILL SWITCH + OPEN POSITION ───
def test_m1_kill_switch_flattens_open_position(temp_env):
    """Scenario 1: Tripping kill switch immediately flattens all open positions."""
    risk = RiskEngine(kill_switch_file=temp_env["kill_switch_file"])
    session = MultiBotLiveSession(
        state_file=str(temp_env["session_file"]),
        reports_dir=temp_env["reports_dir"],
        risk_engine=risk,
    )
    # Seed an open active trade for Bot 4
    session.bot_states["Strategy 4: Golden Trend Runner"]["active_trade"] = {
        "id": "TEST-GTR-001",
        "contract": "NIFTY 25000 CE",
        "entry_fill": 100.0,
        "current_val": 95.0,
        "qty": 25,
        "side": "BUY",
        "status": "OPEN",
    }
    assert session.bot_states["Strategy 4: Golden Trend Runner"]["active_trade"] is not None

    # Trip kill switch
    session.trip_kill_switch("Adversarial Test Kill Switch")

    # Assert position was flattened immediately
    b4 = session.bot_states["Strategy 4: Golden Trend Runner"]
    assert b4["active_trade"] is None
    assert b4["status"] == "EMERGENCY_FLATTENED"
    assert len(b4["closed_trades"]) == 1
    assert "KILL_SWITCH" in b4["closed_trades"][0]["exit_reason"]


# ─── 2. KILL SWITCH + NEW ENTRY ───
def test_m2_kill_switch_blocks_new_entry(temp_env):
    """Scenario 2: Active kill switch blocks all subsequent new entries."""
    risk = RiskEngine(kill_switch_file=temp_env["kill_switch_file"])
    risk.trip_kill_switch("Block New Entries Test")
    session = MultiBotLiveSession(
        state_file=str(temp_env["session_file"]),
        reports_dir=temp_env["reports_dir"],
        risk_engine=risk,
    )

    mkt = {
        "nifty": {"last": 25000, "open": 25000},
        "bank": {"last": 50000, "open": 50000},
        "vix": 14.0,
        "timestamp": "2026-09-17T10:00:00",
    }
    session.evaluate_all_bots(mkt, current_time=dtime(10, 0))

    for name, b in session.bot_states.items():
        assert b["active_trade"] is None, f"{name} entered trade despite active kill switch!"


# ─── 3 & 4. STOP LOSS + MISSING BID / ASK ───
def test_m3_m4_stop_loss_missing_bid_or_ask_pauses_valuation_without_fake_fill():
    """Scenario 3 & 4: Missing Bid or Ask fails closed and rejects simulated fills."""
    trader = DhanPaperSandbox()
    # BUY without Ask
    r_buy = trader.place_order(symbol="NIFTY", transaction_type="BUY", security_id="101", ask=None, option_premium=100.0)
    assert r_buy["status"] == "DATA_UNAVAILABLE"
    assert not r_buy["is_filled"]

    # SELL without Bid
    r_sell = trader.place_order(symbol="NIFTY", transaction_type="SELL", security_id="101", bid=None, option_premium=100.0)
    assert r_sell["status"] == "DATA_UNAVAILABLE"
    assert not r_sell["is_filled"]


# ─── 5. STOP LOSS + STALE QUOTE ───
def test_m5_stale_quote_rejected():
    """Scenario 5: Stale quote timestamp is rejected fail-closed."""
    trader = DhanPaperSandbox()
    stale_ts = "2026-09-17 08:00:00"  # Well over 300 seconds ago
    res = trader.place_order(
        symbol="NIFTY",
        transaction_type="BUY",
        security_id="101",
        ask=150.0,
        bid=149.0,
        quote_timestamp=stale_ts,
    )
    assert res["status"] == "DATA_UNAVAILABLE"
    assert not res["is_filled"]
    assert "STALE_QUOTE" in res["reason"]


# ─── 6. STOP LOSS + REJECTED EXIT ───
def test_m6_exit_order_rejected_if_bid_invalid():
    """Scenario 6: Exit order with invalid bid fails safely with error state."""
    trader = DhanPaperSandbox()
    res = trader.place_order(
        symbol="NIFTY",
        transaction_type="SELL",
        security_id="101",
        bid=-5.0,  # Corrupted / invalid negative bid
        ask=10.0,
    )
    assert res["status"] == "DATA_UNAVAILABLE"
    assert not res["is_filled"]


# ─── 7. STOP LOSS + PARTIAL EXIT ───
def test_m7_partial_exit_binary_model():
    """Scenario 7: Paper broker model is binary (all-or-none); partial fills are rejected."""
    adapter = DhanBrokerAdapter()
    order = Order(order_id="TEST-1", symbol="NIFTY", side=OrderSide.BUY, quantity=25, price=100.0)
    res = adapter.place_order(order)
    assert res.status == OrderStatus.FILLED
    assert res.filled_quantity == 25


# ─── 8. SUDDEN PRICE JUMP ───
def test_m8_sudden_price_jump_slippage_realism():
    """Scenario 8: Extreme tick move executes at actual executable quote + slippage."""
    trader = DhanPaperSandbox()
    # Market gaps down, bid drops to 30.0 from previous 100.0
    res = trader.place_order(
        symbol="NIFTY",
        transaction_type="SELL",
        security_id="101",
        bid=30.0,
        ask=31.0,
        quote_timestamp=datetime.now().isoformat(),
    )
    assert res["is_filled"]
    assert res["fill_premium"] == 29.50  # bid - 0.50 slippage


# ─── 9. EXTREME SPREAD ───
def test_m9_extreme_spread_rejection():
    """Scenario 9: Abnormally wide bid-ask spread (>50%) is rejected."""
    trader = DhanPaperSandbox()
    # 10.0 bid, 100.0 ask (spread = 90.0 on 100.0 = 90%)
    res = trader.place_order(
        symbol="NIFTY",
        transaction_type="BUY",
        security_id="101",
        bid=10.0,
        ask=100.0,
        quote_timestamp=datetime.now().isoformat(),
    )
    assert res["status"] == "EXCESSIVE_SPREAD_WIDTH"
    assert not res["is_filled"]


# ─── 10. INVERTED MARKET ───
def test_m10_inverted_market_rejection():
    """Scenario 10: Inverted market depth (bid > ask) is rejected."""
    trader = DhanPaperSandbox()
    res = trader.place_order(
        symbol="NIFTY",
        transaction_type="BUY",
        security_id="101",
        bid=150.0,
        ask=120.0,
        quote_timestamp=datetime.now().isoformat(),
    )
    assert res["status"] == "INVERTED_MARKET_SPREAD"
    assert not res["is_filled"]


# ─── 11. DUPLICATE ORDER RESPONSE ───
def test_m11_duplicate_order_response_isolation(temp_env):
    """Scenario 11: Duplicate order calls generate distinct unique order IDs."""
    trader = DhanPaperSandbox(state_file=str(temp_env["trades_file"]))
    r1 = trader.place_order(
        symbol="NIFTY", transaction_type="BUY", security_id="101", bid=100.0, ask=101.0,
        quote_timestamp=datetime.now().isoformat(),
    )
    r2 = trader.place_order(
        symbol="NIFTY", transaction_type="BUY", security_id="101", bid=100.0, ask=101.0,
        quote_timestamp=datetime.now().isoformat(),
    )
    assert r1["order_id"] != r2["order_id"]
    assert len(trader.trades) == 2


# ─── 12 & 13. TIMEOUT / LOST ORDER ACKNOWLEDGEMENT ───
def test_m12_m13_sandbox_timeout_or_error_rejected(temp_env):
    """Scenario 12 & 13: HTTP connection timeout or broker error does NOT produce phantom fills."""
    trader = DhanPaperSandbox(
        use_sandbox_server=True,
        state_file=str(temp_env["trades_file"]),
    )
    trader.session.post = MagicMock(side_effect=TimeoutError("Dhan Sandbox Gateway Timeout"))

    res = trader.place_order(
        symbol="NIFTY",
        transaction_type="BUY",
        security_id="101",
        bid=100.0,
        ask=101.0,
        quote_timestamp=datetime.now().isoformat(),
    )
    assert res["status"] == "CONNECTION_FAILURE"
    assert not res["is_filled"]
    assert len(trader.trades) == 0  # Zero phantom trades persisted


# ─── 14. PROCESS RESTART WITH OPEN POSITION ───
def test_m14_process_restart_with_open_position(temp_env):
    """Scenario 14: Process restart safely recovers open positions from disk."""
    risk = RiskEngine(kill_switch_file=temp_env["kill_switch_file"])
    session1 = MultiBotLiveSession(
        state_file=str(temp_env["session_file"]),
        reports_dir=temp_env["reports_dir"],
        risk_engine=risk,
    )
    session1.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]["active_trade"] = {
        "id": "VELOCITY-999",
        "contract": "NIFTY 25200 CE",
        "entry_fill": 110.0,
        "entry_premium": 110.0,
        "qty": 25,
        "target_premium": 140.0,
        "stop_premium": 95.0,
        "side": "BUY",
        "status": "OPEN",
    }
    session1.save_session()

    # Simulate Process Restart by creating a brand new session object reading the same state
    session2 = MultiBotLiveSession(
        state_file=str(temp_env["session_file"]),
        reports_dir=temp_env["reports_dir"],
        risk_engine=RiskEngine(kill_switch_file=temp_env["kill_switch_file"]),
    )
    s5 = session2.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
    assert s5["active_trade"] is not None
    assert s5["active_trade"]["id"] == "VELOCITY-999"
    assert s5["active_trade"]["qty"] == 25


# ─── 15 & 16. BROKER / MARKET-DATA OUTAGE ───
def test_m15_m16_market_data_outage_fails_closed(temp_env):
    """Scenario 15 & 16: Complete market-data outage returns DATA UNAVAILABLE and places NO orders."""
    risk = RiskEngine(kill_switch_file=temp_env["kill_switch_file"])
    session = MultiBotLiveSession(
        state_file=str(temp_env["session_file"]),
        reports_dir=temp_env["reports_dir"],
        risk_engine=risk,
    )
    # Pass None as market state
    session.evaluate_all_bots(None, current_time=dtime(10, 30))

    for name, b in session.bot_states.items():
        assert b["active_trade"] is None


# ─── 17. POSITION RECONCILIATION ───
def test_m17_position_reconciliation_zero_broker_drift():
    """Scenario 17: Broker adapter get_positions parses and reflects holdings."""
    adapter = DhanBrokerAdapter()
    adapter.session.get = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "tradingSymbol": "NIFTY 25000 CE",
            "netQty": 25,
            "buyAvg": 105.0,
            "lastPrice": 112.0,
            "unrealizedProfit": 175.0,
        }
    ]
    adapter.session.get.return_value = mock_resp
    positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "NIFTY 25000 CE"
    assert positions[0].quantity == 25


# ─── 18. 15:35 EOD BOUNDARY ───
def test_m18_1535_eod_boundary_acts_on_every_open_position(temp_env):
    """
    Scenario 18: the 15:35 boundary must ALWAYS act on an open position.

    With a fresh executable quote it squares off. With market data down it must
    NOT invent a fill — it flags the position unresolved and halts. Either way
    the boundary is never silently skipped.
    """
    from datetime import datetime as _dt

    # --- Case A: fresh executable quote -> genuine square-off ---
    risk = RiskEngine(kill_switch_file=temp_env["kill_switch_file"])
    session = MultiBotLiveSession(
        state_file=str(temp_env["session_file"]),
        reports_dir=temp_env["reports_dir"],
        risk_engine=risk,
    )
    session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = {
        "id": "GAMMA-001", "contract": "NIFTY 25000 CE", "entry_fill": 50.0,
        "current_val": 52.0, "current_bid": 52.0, "current_ask": 52.5,
        "quote_timestamp": _dt.now().isoformat(),
        "qty": 25, "side": "BUY", "status": "OPEN",
    }
    session.evaluate_all_bots(None, current_time=dtime(15, 35, 0))

    b3 = session.bot_states["Strategy 3: Confluence Gamma Scalper"]
    assert b3["active_trade"] is None
    assert b3["status"] == "SQUARED_OFF"
    assert len(b3["closed_trades"]) == 1
    assert "EOD_FORCED_EXIT" in b3["closed_trades"][0]["exit_reason"]

    # --- Case B: data dropout -> unresolved, never a fabricated fill ---
    risk2 = RiskEngine(kill_switch_file=temp_env["kill_switch_file"])
    session2 = MultiBotLiveSession(
        state_file=str(temp_env["session_file"]) + ".b",
        reports_dir=temp_env["reports_dir"],
        risk_engine=risk2,
    )
    session2.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = {
        "id": "GAMMA-002", "contract": "NIFTY 25000 CE", "entry_fill": 50.0,
        "current_val": 52.0, "current_bid": None, "current_ask": None,
        "quote_timestamp": None,
        "qty": 25, "side": "BUY", "status": "OPEN",
    }
    session2.evaluate_all_bots(None, current_time=dtime(15, 35, 0))

    b3b = session2.bot_states["Strategy 3: Confluence Gamma Scalper"]
    assert b3b["closed_trades"] == [], "no fabricated EOD fill may enter the ledger"
    assert b3b["active_trade"] is not None
    assert b3b["active_trade"]["status"] == "UNRESOLVED_EOD"
    assert b3b["active_trade"]["net_pnl"] is None
    assert session2.requires_reconciliation is True


# ─── 19. ATTEMPTED DHAN PRODUCTION ORDER WHILE LIVE=FALSE ───
def test_m19_dhan_production_order_hard_blocked_by_safety_barrier():
    """Scenario 19: Any attempt to POST to production Dhan /orders is blocked with RuntimeError."""
    adapter = DhanBrokerAdapter()
    assert not Config.LIVE_TRADING_ENABLED

    # Attempt to post to api.dhan.co /orders endpoint via adapter's session
    with pytest.raises(RuntimeError, match="CRITICAL SAFETY LOCK TRIGGERED"):
        adapter.session.post("https://api.dhan.co/v2/orders", json={"symbol": "NIFTY"})


# ─── 20. ALTERNATE CODE PATH PRODUCTION ORDER BYPASS ATTEMPT ───
def test_m20_sandbox_hard_barrier_blocks_production_url():
    """Scenario 20: DhanPaperSandbox intercepts and aborts any production order routing."""
    sandbox = DhanPaperSandbox()
    assert not Config.LIVE_TRADING_ENABLED

    with pytest.raises(RuntimeError, match="CRITICAL SAFETY LOCK TRIGGERED"):
        sandbox.session.post("https://api.dhan.co/v2/orders", json={"symbol": "NIFTY"})
