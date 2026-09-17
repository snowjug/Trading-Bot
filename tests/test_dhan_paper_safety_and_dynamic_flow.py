"""
Final Dhan Paper-Trading Readiness Verification Test Suite.
Verifies all 9 mandatory institutional requirements:
1. Real contract resolution from Dhan Scrip Master (numeric securityId, lot size).
2. Invalid / expired contract rejection (fail-closed).
3. Missing market data -> no signal -> no trade.
4. Missing option quote -> no fill -> no trade.
5. Invalid security ID -> rejection.
6. Realistic paper fill (bid/ask executable execution + slippage).
7. Dynamic exit and P&L calculation with statutory costs.
8. Hard production order safety barrier (blocks POST /orders).
9. Sandbox vs production-paper environment separation.
"""

import os
import sys
import pytest
from datetime import datetime, date, timedelta, time as dtime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Config
from src.execution.dhan_paper_trader import DhanPaperSandbox
from src.execution.dhan_scrip_master import DhanScripMaster
from src.execution.dhan_contract_resolver import DhanContractResolver
from src.execution.broker_adapters.dhan import DhanBrokerAdapter
from src.execution.live_paper_session import MultiBotLiveSession


# ─── 1. REAL CONTRACT RESOLUTION FROM OFFICIAL SCRIP MASTER ───
def test_real_contract_resolution_from_scrip_master():
    """Verify authentic numeric Dhan securityId and exchange lot size resolution."""
    # Synchronize scrip master
    synced = DhanScripMaster.sync_master()
    assert synced is True

    contract = DhanScripMaster.resolve_contract(
        underlying="NIFTY",
        option_type="CE",
        target_strike=24150.0,
    )

    assert contract is not None
    # Security ID must be an authentic numeric string (e.g. "57379")
    assert contract["security_id"].isdigit(), f"Expected numeric securityId, got {contract['security_id']}"
    assert contract["underlying"] == "NIFTY"
    assert contract["option_type"] == "CE"
    assert contract["strike"] > 0
    assert contract["lot_size"] in [25, 50, 65, 75]  # Authentic exchange lot size
    assert "CALL" in contract["custom_symbol"] or "CE" in contract["custom_symbol"]
    assert contract["is_tradable"] is True


# ─── 2. INVALID / EXPIRED CONTRACT REJECTION ───
def test_invalid_or_expired_contract_rejection():
    """Verify non-existent or expired contracts return None and fail closed."""
    # Case A: Expired date in the past
    expired = DhanScripMaster.resolve_contract(
        underlying="NIFTY",
        option_type="CE",
        target_strike=24150.0,
        as_of_date=date(2035, 1, 1),  # Far future date beyond all active contracts
    )
    assert expired is None, "Expired / non-existent future contract should return None"

    # Case B: Absurd non-existent strike (e.g. 999,999)
    absurd_strike = DhanScripMaster.resolve_contract(
        underlying="NIFTY",
        option_type="CE",
        target_strike=999999.0,
    )
    assert absurd_strike is None, "Absurd non-existent strike should fail closed and return None"


# ─── 3. MISSING MARKET DATA -> NO SIGNAL -> NO TRADE ───
def test_missing_market_data_leads_to_no_trade(tmp_path):
    """Verify missing spot/vix results in DATA UNAVAILABLE -> NO SIGNAL -> NO TRADE."""
    session = MultiBotLiveSession(state_file=str(tmp_path / "paper_session.json"))

    # When market state is None (offline / data unavailable)
    session.evaluate_all_bots(None)

    # Every bot must remain in clean monitoring mode with 0 trades
    for name, state in session.bot_states.items():
        assert state["active_trade"] is None, f"{name} should not enter on missing market data"
        assert len(state["closed_trades"]) == 0
        assert state["net_pnl"] == 0.0


# ─── 4. MISSING OPTION QUOTE -> NO FILL -> NO TRADE ───
def test_missing_option_quote_leads_to_no_trade(tmp_path):
    """Verify orders are rejected if real executable option quote is unavailable."""
    sandbox = DhanPaperSandbox(
        client_id="1111273920",
        access_token="test_token",
        env="prod",
        state_dir=str(tmp_path),
    )

    # Attempt to place order with missing quote / None premium
    resp = sandbox.place_order(
        strategy_name="Test Scalper",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        option_premium=None,
        quote=None,
    )

    assert resp["is_filled"] is False
    assert resp["status"] == "REJECTED_MISSING_QUOTE"
    assert "DATA UNAVAILABLE" in resp["reason"]
    assert len(sandbox.trades) == 0, "No trade record should be appended for rejected order"


# ─── 5. INVALID SECURITY ID -> NO TRADE ───
def test_invalid_security_id_leads_to_no_trade(tmp_path):
    """Verify empty or invalid security ID is rejected."""
    sandbox = DhanPaperSandbox(
        client_id="1111273920",
        access_token="test_token",
        env="prod",
        state_dir=str(tmp_path),
    )

    # Attempt with empty securityId
    resp = sandbox.place_order(
        strategy_name="Test Scalper",
        symbol="NIFTY",
        security_id="",
        transaction_type="BUY",
        quantity=25,
        option_premium=100.0,
    )

    assert resp["is_filled"] is False
    assert resp["status"] == "REJECTED_INVALID_SECURITY_ID"
    assert len(sandbox.trades) == 0


# ─── 6. REALISTIC PAPER FILL (BID / ASK / LTP + SLIPPAGE) ───
def test_realistic_paper_fill_using_executable_quotes(tmp_path):
    """Verify BUY fills at Ask + 0.50 slippage and SELL fills at Bid - 0.50 slippage."""
    sandbox = DhanPaperSandbox(
        client_id="1111273920",
        access_token="test_token",
        env="prod",
        state_dir=str(tmp_path),
    )

    # Case A: BUY with executable Ask (ask=120.00, ltp=119.00)
    buy_quote = {
        "security_id": "57379",
        "ltp": 119.00,
        "bid": 118.50,
        "ask": 120.00,
        "timestamp": "2026-09-17T10:15:00",
    }
    buy_resp = sandbox.place_order(
        strategy_name="Velocity-5",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        quote=buy_quote,
    )

    assert buy_resp["is_filled"] is True
    assert buy_resp["status"] == "FILLED"
    # Fill price must be Ask + 0.50 pt slippage = 120.50
    assert buy_resp["fill_premium"] == 120.50
    assert buy_resp["execution_mode"] == "ASK_PLUS_SLIPPAGE"
    assert buy_resp["quote_timestamp"] == "2026-09-17T10:15:00"

    # Case B: SELL with executable Bid (bid=135.00, ltp=135.50)
    sell_quote = {
        "security_id": "57379",
        "ltp": 135.50,
        "bid": 135.00,
        "ask": 136.00,
        "timestamp": "2026-09-17T10:25:00",
    }
    sell_resp = sandbox.place_order(
        strategy_name="Velocity-5",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="SELL",
        quantity=25,
        quote=sell_quote,
    )

    assert sell_resp["is_filled"] is True
    # Fill price must be Bid - 0.50 pt slippage = 134.50
    assert sell_resp["fill_premium"] == 134.50
    assert sell_resp["execution_mode"] == "BID_MINUS_SLIPPAGE"


# ─── 7. DYNAMIC EXIT AND P&L CALCULATION WITH STATUTORY COSTS ───
def test_exit_and_pnl_calculation(tmp_path):
    """Verify dynamic P&L accounting with statutory friction (STT, brokerage, taxes)."""
    sandbox = DhanPaperSandbox(
        client_id="1111273920",
        access_token="test_token",
        env="prod",
        state_dir=str(tmp_path),
    )

    # Entry: BUY 25 qty @ Ask 100.0 (+0.50 slippage = 100.50)
    entry = sandbox.place_order(
        strategy_name="Golden Trend",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        quote={"ltp": 100.0, "ask": 100.0, "timestamp": "2026-09-17T11:00:00"},
    )
    assert entry["fill_premium"] == 100.50
    entry_cost = entry["entry_costs_inr"]
    assert entry_cost > 0  # Brokerage + statutory charges

    # Exit: SELL 25 qty @ Bid 130.0 (-0.50 slippage = 129.50)
    exit_order = sandbox.place_order(
        strategy_name="Golden Trend",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="SELL",
        quantity=25,
        quote={"ltp": 130.0, "bid": 130.0, "timestamp": "2026-09-17T11:30:00"},
    )
    assert exit_order["fill_premium"] == 129.50

    gross_pts = exit_order["fill_premium"] - entry["fill_premium"]  # 129.50 - 100.50 = 29.0 pts
    gross_pnl = gross_pts * 25  # 725.0 INR
    net_pnl = gross_pnl - (entry_cost + exit_order["entry_costs_inr"])

    assert round(gross_pnl, 2) == 725.0
    assert net_pnl < gross_pnl  # Confirms statutory friction was deducted
    assert net_pnl > 0


# ─── 8. PRODUCTION /ORDERS HARD SAFETY BARRIER ───
def test_production_orders_safety_barrier():
    """Verify fail-safe interceptor strictly raises RuntimeError on any production POST /orders attempt."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod")
    adapter = DhanBrokerAdapter(client_id="1111273920", access_token="test_token")

    # A: DhanPaperSandbox session POST to api.dhan.co/v2/orders MUST be blocked
    with pytest.raises(RuntimeError, match="CRITICAL SAFETY LOCK TRIGGERED"):
        sandbox.session.post(
            "https://api.dhan.co/v2/orders",
            json={"order": "prohibited"}
        )

    # B: DhanBrokerAdapter session POST to api.dhan.co/v2/orders MUST be blocked
    with pytest.raises(RuntimeError, match="CRITICAL SAFETY LOCK TRIGGERED"):
        adapter.session.post(
            "https://api.dhan.co/v2/orders",
            json={"order": "prohibited"}
        )


# ─── 9. SANDBOX VS PRODUCTION ENVIRONMENT SEPARATION ───
def test_sandbox_and_production_environment_separation():
    """Verify sandbox routes to https://sandbox.dhan.co/v2 while prod routes locally in paper mode."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="sandbox")
    prod_paper = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod")

    assert sandbox.use_sandbox_server is True
    assert sandbox.base_url == "https://sandbox.dhan.co/v2"

    assert prod_paper.use_sandbox_server is False
    assert prod_paper.base_url == "https://api.dhan.co/v2"
