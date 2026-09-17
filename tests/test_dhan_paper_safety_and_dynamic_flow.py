"""
Comprehensive Safety and Dynamic Market Data Verification Test Suite.
Verifies:
1. Hard fail-safe prevents POST /orders to production Dhan API in paper mode.
2. Dynamic option contract and strike resolution with zero hardcoding.
3. Realistic paper execution with slippage (+0.50 pt) and statutory taxes.
4. Dhan Sandbox isolation for API plumbing tests.
5. Multi-bot live paper engine starts clean with zero hardcoded demo trades.
"""
import os
import sys
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Config
from src.execution.dhan_paper_trader import DhanPaperSandbox
from src.execution.dhan_contract_resolver import DhanContractResolver
from src.execution.broker_adapters.dhan import DhanBrokerAdapter
from src.execution.live_paper_session import MultiBotLiveSession


def test_safety_live_trading_is_hard_locked_false():
    """Verify production LIVE_TRADING_ENABLED flag is strictly False."""
    assert Config.LIVE_TRADING_ENABLED is False
    # Calling assert_no_live_trading must pass cleanly
    Config.assert_no_live_trading()


def test_dhan_paper_sandbox_safety_barrier_raises_on_production_order():
    """Verify safe_post fail-safe intercepts any attempt to POST to api.dhan.co/v2/orders."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod")
    
    # Attempting to send POST to production Dhan orders endpoint MUST raise RuntimeError
    with pytest.raises(RuntimeError, match="CRITICAL SAFETY LOCK TRIGGERED"):
        sandbox.session.post(
            "https://api.dhan.co/v2/orders",
            json={
                "dhanClientId": "1111273920",
                "transactionType": "BUY",
                "exchangeSegment": "NSE_FNO",
                "productType": "INTRADAY",
                "orderType": "MARKET",
                "quantity": 25,
            }
        )


def test_dhan_broker_adapter_safety_barrier_blocks_order_dispatch():
    """Verify DhanBrokerAdapter._install_safety_barrier blocks POST /orders."""
    adapter = DhanBrokerAdapter(client_id="1111273920", access_token="test_token")
    
    with pytest.raises(RuntimeError, match="CRITICAL SAFETY LOCK TRIGGERED"):
        adapter._session.post(
            "https://api.dhan.co/v2/orders",
            json={"order": "fake"}
        )


def test_dhan_contract_resolver_dynamic_expiry_calculation():
    """Verify dynamic weekly expiry resolution always produces a valid Thursday."""
    today = date.today()
    exp_date = DhanContractResolver.get_upcoming_weekly_expiry(base_date=today)
    
    # NSE weekly options expire on Thursday (weekday 3)
    assert exp_date.weekday() == 3
    assert exp_date >= today
    assert (exp_date - today).days <= 7


def test_dhan_contract_resolver_no_hardcoded_numbers():
    """Verify dynamic strike and Black-Scholes premium calculation with zero hardcoded values."""
    spot = 24138.75
    vix = 14.80
    
    # 1. Resolve ATM Call
    call_res = DhanContractResolver.resolve_option_contract(
        underlying_spot=spot,
        vix=vix,
        option_type="CE",
        strike_offset_steps=0,
    )
    
    assert call_res["strike"] == 24150.0  # round(24138.75 / 50) * 50
    assert call_res["option_type"] == "CE"
    assert call_res["premium"] > 0.50
    assert 0.0 < call_res["delta"] < 1.0
    assert call_res["lot_size"] == 25
    assert "24150" in call_res["trading_symbol"]
    assert "CE" in call_res["trading_symbol"]
    
    # 2. Resolve 1-Strike OTM Put
    put_res = DhanContractResolver.resolve_option_contract(
        underlying_spot=spot,
        vix=vix,
        option_type="PE",
        strike_offset_steps=-1,
    )
    
    assert put_res["strike"] == 24100.0
    assert put_res["option_type"] == "PE"
    assert put_res["premium"] > 0.50
    assert -1.0 < put_res["delta"] < 0.0
    assert "24100" in put_res["trading_symbol"]
    assert "PE" in put_res["trading_symbol"]


def test_paper_sandbox_local_order_execution_and_slippage(tmp_path):
    """Verify DhanPaperSandbox handles orders locally with slippage and statutory taxes."""
    sandbox = DhanPaperSandbox(
        client_id="1111273920",
        access_token="test_token",
        env="prod",
        state_dir=str(tmp_path),
    )
    
    order_req = {
        "dhanClientId": "1111273920",
        "correlationId": "TEST_CORR_001",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_FNO",
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
        "tradingSymbol": "NIFTY 24150 CE",
        "securityId": "NIFTY24150CE",
        "quantity": 25,
        "price": 115.0,
        "ltp": 115.0,
    }
    
    # Place order via paper sandbox
    resp = sandbox.place_order(order_req)
    
    assert resp["status"] == "FILLED"
    assert resp["order_id"].startswith("DHAN-PAPER-")
    assert resp["entry_premium"] == 115.50  # 115.0 + 0.50 slippage
    assert len(sandbox.trades) == 1
    assert sandbox.trades[0]["security_id"] == "NIFTY24150CE"


def test_sandbox_mode_routes_to_sandbox_server():
    """Verify --env sandbox uses https://sandbox.dhan.co/v2."""
    sandbox = DhanPaperSandbox(
        client_id="1111273920",
        access_token="test_token",
        env="sandbox",
    )
    assert sandbox.base_url == "https://sandbox.dhan.co/v2"


def test_multi_bot_live_session_zero_hardcoded_positions(tmp_path):
    """Verify MultiBotLiveSession initializes in clean active monitoring mode."""
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(state_file=str(state_file))
    
    # Check all 6 bots exist and have NO hardcoded active trades
    assert len(session.bot_states) == 6
    for name, state in session.bot_states.items():
        assert state["active_trade"] is None, f"{name} should have no active trade at start"
        assert state["closed_trades"] == [], f"{name} should have no closed trades at start"
        assert state["net_pnl"] == 0.0
        assert "MONITORING" in state["status"] or "ARMED" in state["status"] or "WATCHING" in state["status"]


def test_multi_bot_dynamic_evaluation_cycle(tmp_path):
    """Verify live evaluation cycle generates dynamic contracts from current market data."""
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(state_file=str(state_file))
    
    # Simulate a dynamic market feed
    fake_market = {
        "timestamp": datetime.now(),
        "nifty": {"last": 24220.0, "open": 24150.0},  # +70 pts expansion
        "bank": {"last": 52100.0, "open": 52000.0},
        "vix": 14.2,
    }
    
    from datetime import time as dtime
    # Run one tick of evaluate_all_bots during intraday trading hours (10:15 AM)
    session.evaluate_all_bots(fake_market, current_time=dtime(10, 15))
    
    # Bot 5 (Velocity-5 ORB CE Breakout) should dynamically trigger
    s5 = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
    assert s5["active_trade"] is not None
    trade = s5["active_trade"]
    assert "CE" in trade["contract"]
    assert trade["entry_premium"] > 0.0
    assert trade["qty"] == 25
    assert trade["target_premium"] > trade["entry_premium"]
    assert trade["stop_premium"] < trade["entry_premium"]
