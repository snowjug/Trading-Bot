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
from pathlib import Path
from src.risk.risk_engine import RiskEngine
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
    session = MultiBotLiveSession(state_file=str(tmp_path / "paper_session.json"),
                                    reports_dir=tmp_path,
                                    risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"))

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
    assert resp["status"] == "DATA_UNAVAILABLE"
    assert "NO_EXECUTION" in resp["reason"]
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


# ─── 6. REALISTIC PAPER FILL (BID / ASK EXECUTABLE + SLIPPAGE) ───
def test_realistic_paper_fill_using_executable_quotes(tmp_path):
    """Verify BUY fills at Ask + 0.50 slippage and SELL fills at Bid - 0.50 slippage."""
    sandbox = DhanPaperSandbox(
        client_id="1111273920",
        access_token="test_token",
        env="prod",
        state_dir=str(tmp_path),
    )

    now_iso = datetime.now().isoformat()

    # Case A: BUY with executable Ask (ask=120.00, ltp=119.00)
    buy_quote = {
        "security_id": "57379",
        "ltp": 119.00,
        "bid": 118.50,
        "ask": 120.00,
        "timestamp": now_iso,
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
    assert buy_resp["quote_timestamp"] == now_iso

    # Case B: SELL with executable Bid (bid=135.00, ltp=135.50)
    sell_quote = {
        "security_id": "57379",
        "ltp": 135.50,
        "bid": 135.00,
        "ask": 136.00,
        "timestamp": now_iso,
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

    now_iso = datetime.now().isoformat()

    # Entry: BUY 25 qty @ Ask 100.0 (+0.50 slippage = 100.50)
    entry = sandbox.place_order(
        strategy_name="Golden Trend",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        quote={"ltp": 100.0, "ask": 100.0, "timestamp": now_iso},
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
        quote={"ltp": 130.0, "bid": 130.0, "timestamp": now_iso},
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


# ─── 10. QUOTE UNAVAILABLE DURING OPEN POSITION -> PAUSE VALUATION (NO FABRICATION) ───
def test_quote_unavailable_during_open_position_pauses_valuation(tmp_path):
    """Verify quote failure during active trade pauses valuation without fabricating prices or P&L."""
    session = MultiBotLiveSession(state_file=str(tmp_path / "paper_session.json"),
                                    reports_dir=tmp_path,
                                    risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"))
    s5 = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]

    # Seed an active trade with real entry values
    s5["active_trade"] = {
        "id": "VELOCITY-TEST",
        "contract": "NIFTY-Sep2026-24150-CE",
        "security_id": "57379",
        "trading_symbol": "NIFTY-Sep2026-24150-CE",
        "entry_time": "09:30:00",
        "spot_entry": 24150.0,
        "entry_premium": 120.0,
        "target_premium": 156.0,
        "stop_premium": 102.0,
        "current_premium": 120.0,
        "qty": 25,
        "status": "OPEN_CE_ORB",
        "unrealized_pnl": 0.0,
        "valuation_status": "LIVE_QUOTE",
    }
    s5["status"] = "IN_POSITION (ORB_CE_BREAKOUT)"

    # When live quote is unavailable (returns None)
    with patch.object(DhanContractResolver, "fetch_option_quote", return_value=None):
        mkt = {
            "nifty": {"last": 24300.0, "open": 24100.0},  # Spot moved +150 pts
            "bank": {"last": 52000.0, "open": 51800.0},
            "vix": 14.0,
        }
        session.evaluate_all_bots(mkt, current_time=dtime(10, 0))

    t5 = s5["active_trade"]
    # Position must NOT be closed, valuation paused, NO synthetic calculation
    assert t5 is not None, "Trade must not be closed on missing data"
    assert t5["valuation_status"] == "DATA_UNAVAILABLE"
    assert t5["current_premium"] == 120.0, "Premium must remain unchanged, not fabricated"
    assert t5["unrealized_pnl"] is None, "PnL must not be synthetically calculated"
    assert s5["net_pnl"] == 0.0


# ─── 11. PROVE NO SPOT_DIFF FORMULA EXISTS IN EXECUTABLE PATH ───
def test_no_spot_diff_formula_in_executable_path():
    """Verify spot_diff * constant synthetic pricing has been eliminated repository-wide."""
    import inspect
    import src.execution.live_paper_session as lps
    src_text = inspect.getsource(lps)
    assert "spot_diff" not in src_text, "Found forbidden 'spot_diff' synthetic valuation in live_paper_session.py"


# ─── 12. PROVE NO FIXED THETA-DECAY IN APEX VRP ───
def test_no_fixed_theta_decay_in_apex_vrp(tmp_path):
    """Verify Apex VRP does not use current_val -= 0.05 fixed theta decay."""
    import inspect
    import src.execution.live_paper_session as lps
    src_text = inspect.getsource(lps)
    assert "- 0.05" not in src_text, "Found forbidden fixed '- 0.05' theta decay in live_paper_session.py"

    # Also prove active strangle pauses when quotes fail
    session = MultiBotLiveSession(state_file=str(tmp_path / "paper_session.json"),
                                    reports_dir=tmp_path,
                                    risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"))
    s1 = session.bot_states["Strategy 1: Apex VRP Engine"]
    s1["active_trade"] = {
        "id": "APEX-THETA-TEST",
        "contract": "NIFTY STRANGLE",
        "call_security_id": "57379",
        "put_security_id": "57380",
        "net_credit_collected": 150.0,
        "current_val": 150.0,
        "qty": 25,
        "unrealized_pnl": 0.0,
        "valuation_status": "LIVE_QUOTE",
    }
    s1["status"] = "IN_POSITION (THETA_DECAY)"

    with patch.object(DhanContractResolver, "fetch_option_quote", return_value=None):
        mkt = {
            "nifty": {"last": 24150.0, "open": 24150.0},
            "bank": {"last": 52000.0, "open": 52000.0},
            "vix": 14.0,
        }
        session.evaluate_all_bots(mkt, current_time=dtime(10, 0))

    t1 = s1["active_trade"]
    assert t1["valuation_status"] == "DATA_UNAVAILABLE"
    assert t1["current_val"] == 150.0, "current_val must not be decremented synthetically"


# ─── 13. MISSING OR INVALID LOT SIZE CAUSES NO TRADE ───
def test_missing_or_invalid_lot_size_causes_no_trade():
    """Verify DhanScripMaster rejects contracts with missing or non-positive lot size."""
    import pandas as pd
    import numpy as np

    fake_df = pd.DataFrame([
        {
            "UNDERLYING": "NIFTY",
            "SEM_OPTION_TYPE": "CE",
            "EXPIRY_DATE_CLEAN": date(2026, 9, 29),
            "SEM_STRIKE_PRICE": 24150.0,
            "SEM_SMST_SECURITY_ID": "57379",
            "SEM_TRADING_SYMBOL": "NIFTY-24150-CE",
            "SEM_CUSTOM_SYMBOL": "NIFTY 29 SEP 24150 CALL",
            "SEM_LOT_UNITS": np.nan,  # Missing lot size
        }
    ])

    with patch.object(DhanScripMaster, "get_master_df", return_value=fake_df):
        res = DhanScripMaster.resolve_contract(
            underlying="NIFTY",
            option_type="CE",
            target_strike=24150.0,
            as_of_date=date(2026, 9, 17),
        )
        assert res is None, "Missing lot size must fail-closed and return None (NO TRADE)"

    # Also test non-positive lot size <= 0
    fake_df_zero = fake_df.copy()
    fake_df_zero["SEM_LOT_UNITS"] = 0
    with patch.object(DhanScripMaster, "get_master_df", return_value=fake_df_zero):
        res_zero = DhanScripMaster.resolve_contract(
            underlying="NIFTY",
            option_type="CE",
            target_strike=24150.0,
            as_of_date=date(2026, 9, 17),
        )
        assert res_zero is None, "Zero/negative lot size must fail-closed and return None (NO TRADE)"


# ─── 14. INVALID CONTRACT METADATA CAUSES NO TRADE ───
def test_invalid_contract_metadata_causes_no_trade():
    """Verify DhanScripMaster rejects malformed contracts (bad securityId, blank symbols)."""
    import pandas as pd

    # Non-numeric / missing security ID
    fake_df = pd.DataFrame([
        {
            "UNDERLYING": "NIFTY",
            "SEM_OPTION_TYPE": "CE",
            "EXPIRY_DATE_CLEAN": date(2026, 9, 29),
            "SEM_STRIKE_PRICE": 24150.0,
            "SEM_SMST_SECURITY_ID": "UNKNOWN",  # Invalid security ID
            "SEM_TRADING_SYMBOL": "NIFTY-24150-CE",
            "SEM_CUSTOM_SYMBOL": "NIFTY 29 SEP 24150 CALL",
            "SEM_LOT_UNITS": 25,
        }
    ])

    with patch.object(DhanScripMaster, "get_master_df", return_value=fake_df):
        res = DhanScripMaster.resolve_contract(
            underlying="NIFTY",
            option_type="CE",
            target_strike=24150.0,
            as_of_date=date(2026, 9, 17),
        )
        assert res is None, "Non-numeric security ID must fail-closed and return None"


# ─── 15. BUY WITH VALID ASK -> EXECUTES AT ASK + SLIPPAGE ───
def test_buy_with_valid_ask_executes_at_ask_plus_slippage(tmp_path):
    """BUY orders must fill at authentic Ask + configured slippage (0.50 pts)."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod", state_dir=str(tmp_path))
    now_iso = datetime.now().isoformat()

    quote = {
        "security_id": "57379",
        "ltp": 150.0,
        "bid": 149.50,
        "ask": 151.00,
        "timestamp": now_iso,
    }
    resp = sandbox.place_order(
        strategy_name="ORB Scalp",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        quote=quote,
    )

    assert resp["is_filled"] is True
    assert resp["status"] == "FILLED"
    assert resp["fill_premium"] == 151.50  # Ask (151.00) + 0.50 slippage
    assert resp["execution_mode"] == "ASK_PLUS_SLIPPAGE"
    assert len(sandbox.trades) == 1


# ─── 16. BUY WITH MISSING ASK + VALID LTP -> NO EXECUTION ───
def test_buy_with_missing_ask_valid_ltp_no_execution(tmp_path):
    """BUY orders with missing Ask must NEVER fall back to LTP; must fail closed."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod", state_dir=str(tmp_path))
    now_iso = datetime.now().isoformat()

    # LTP exists and is valid (150.0), but Ask is None
    quote = {
        "security_id": "57379",
        "ltp": 150.0,
        "bid": 149.0,
        "ask": None,
        "timestamp": now_iso,
    }
    resp = sandbox.place_order(
        strategy_name="ORB Scalp",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        quote=quote,
    )

    assert resp["is_filled"] is False
    assert resp["status"] == "DATA_UNAVAILABLE"
    assert "NO_EXECUTION" in resp["reason"]
    assert "LTP cannot substitute for Ask" in resp["reason"]
    assert len(sandbox.trades) == 0, "No trade must be recorded when Ask is missing"


# ─── 17. SELL WITH VALID BID -> EXECUTES AT BID - SLIPPAGE ───
def test_sell_with_valid_bid_executes_at_bid_minus_slippage(tmp_path):
    """SELL orders must fill at authentic Bid - configured slippage (0.50 pts)."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod", state_dir=str(tmp_path))
    now_iso = datetime.now().isoformat()

    quote = {
        "security_id": "57379",
        "ltp": 160.0,
        "bid": 159.00,
        "ask": 161.00,
        "timestamp": now_iso,
    }
    resp = sandbox.place_order(
        strategy_name="Exit Scalp",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="SELL",
        quantity=25,
        quote=quote,
    )

    assert resp["is_filled"] is True
    assert resp["status"] == "FILLED"
    assert resp["fill_premium"] == 158.50  # Bid (159.00) - 0.50 slippage
    assert resp["execution_mode"] == "BID_MINUS_SLIPPAGE"
    assert len(sandbox.trades) == 1


# ─── 18. SELL WITH MISSING BID + VALID LTP -> NO EXECUTION ───
def test_sell_with_missing_bid_valid_ltp_no_execution(tmp_path):
    """SELL orders with missing Bid must NEVER fall back to LTP; must fail closed."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod", state_dir=str(tmp_path))
    now_iso = datetime.now().isoformat()

    # LTP exists (160.0), but Bid is None
    quote = {
        "security_id": "57379",
        "ltp": 160.0,
        "bid": None,
        "ask": 161.0,
        "timestamp": now_iso,
    }
    resp = sandbox.place_order(
        strategy_name="Exit Scalp",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="SELL",
        quantity=25,
        quote=quote,
    )

    assert resp["is_filled"] is False
    assert resp["status"] == "DATA_UNAVAILABLE"
    assert "NO_EXECUTION" in resp["reason"]
    assert "LTP cannot substitute for Bid" in resp["reason"]
    assert len(sandbox.trades) == 0, "No trade must be recorded when Bid is missing"


# ─── 19. LONG VALUATION WITH MISSING BID -> DATA_UNAVAILABLE, NO SYNTHETIC P&L ───
def test_long_valuation_with_missing_bid_data_unavailable(tmp_path):
    """Long position exit valuation requires authentic Bid. Missing Bid pauses valuation with no synthetic P&L."""
    session = MultiBotLiveSession(state_file=str(tmp_path / "paper_session.json"),
                                    reports_dir=tmp_path,
                                    risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"))
    s5 = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]

    s5["active_trade"] = {
        "id": "VELOCITY-LONG",
        "contract": "NIFTY-24150-CE",
        "security_id": "57379",
        "trading_symbol": "NIFTY-24150-CE",
        "entry_time": "09:30:00",
        "spot_entry": 24150.0,
        "entry_premium": 120.0,
        "target_premium": 156.0,
        "stop_premium": 102.0,
        "current_premium": 120.0,
        "qty": 25,
        "status": "OPEN_CE_ORB",
        "unrealized_pnl": 0.0,
        "valuation_status": "LIVE_QUOTE",
    }
    s5["status"] = "IN_POSITION (ORB_CE_BREAKOUT)"

    now_iso = datetime.now().isoformat()
    # Mock quote with LTP way above target (170 > 156), but Bid is missing (None)
    mock_quote = {
        "security_id": "57379",
        "ltp": 170.0,
        "bid": None,
        "ask": 172.0,
        "timestamp": now_iso,
    }

    with patch.object(DhanContractResolver, "fetch_option_quote", return_value=mock_quote):
        mkt = {
            "nifty": {"last": 24250.0, "open": 24100.0},
            "bank": {"last": 52000.0, "open": 51800.0},
            "vix": 14.0,
        }
        session.evaluate_all_bots(mkt, current_time=dtime(10, 0))

    t5 = s5["active_trade"]
    # Position must NOT close, valuation status must be DATA_UNAVAILABLE, zero synthetic PnL
    assert t5 is not None, "Position must not be prematurely closed"
    assert t5["valuation_status"] == "DATA_UNAVAILABLE"
    assert t5["current_premium"] == 120.0, "Premium must not update to LTP"
    assert t5["unrealized_pnl"] is None, "P&L must not be calculated from LTP"
    assert s5["net_pnl"] == 0.0


# ─── 20. SHORT VALUATION WITH MISSING ASK -> DATA_UNAVAILABLE, NO SYNTHETIC P&L ───
def test_short_valuation_with_missing_ask_data_unavailable(tmp_path):
    """Short position valuation requires authentic Ask (cost to close). Missing Ask pauses valuation."""
    session = MultiBotLiveSession(state_file=str(tmp_path / "paper_session.json"),
                                    reports_dir=tmp_path,
                                    risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"))
    s1 = session.bot_states["Strategy 1: Apex VRP Engine"]

    s1["active_trade"] = {
        "id": "APEX-SHORT",
        "contract": "NIFTY STRANGLE",
        "call_security_id": "57379",
        "put_security_id": "57380",
        "net_credit_collected": 150.0,
        "current_val": 150.0,
        "qty": 25,
        "unrealized_pnl": 0.0,
        "valuation_status": "LIVE_QUOTE",
    }
    s1["status"] = "IN_POSITION (THETA_DECAY)"

    now_iso = datetime.now().isoformat()
    # Mock call quote with valid LTP and Bid, but Ask is missing (None)
    call_quote = {
        "security_id": "57379",
        "ltp": 50.0,
        "bid": 49.0,
        "ask": None,  # Missing Ask
        "timestamp": now_iso,
    }
    put_quote = {
        "security_id": "57380",
        "ltp": 60.0,
        "bid": 59.0,
        "ask": 61.0,
        "timestamp": now_iso,
    }

    def mock_fetch(sec_id, **kwargs):
        if sec_id == "57379":
            return call_quote
        return put_quote

    with patch.object(DhanContractResolver, "fetch_option_quote", side_effect=mock_fetch):
        mkt = {
            "nifty": {"last": 24150.0, "open": 24150.0},
            "bank": {"last": 52000.0, "open": 52000.0},
            "vix": 14.0,
        }
        session.evaluate_all_bots(mkt, current_time=dtime(10, 0))

    t1 = s1["active_trade"]
    assert t1 is not None
    assert t1["valuation_status"] == "DATA_UNAVAILABLE"
    assert t1["current_val"] == 150.0, "Valuation must not fabricate cost to close"
    assert t1["unrealized_pnl"] is None


# ─── 21. INVALID / ZERO / NEGATIVE BID OR ASK -> REJECTED ───
def test_invalid_zero_or_negative_bid_ask_rejected(tmp_path):
    """Orders with zero, negative, or non-numeric Bid or Ask must be rejected with DATA_UNAVAILABLE."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod", state_dir=str(tmp_path))
    now_iso = datetime.now().isoformat()

    invalid_values = [0.0, 0, -1.0, -100.5, "INVALID", None]

    for val in invalid_values:
        # Test BUY with invalid ask
        buy_resp = sandbox.place_order(
            strategy_name="Test",
            symbol="NIFTY 24150 CE",
            security_id="57379",
            transaction_type="BUY",
            quantity=25,
            quote={"ltp": 100.0, "ask": val, "timestamp": now_iso},
        )
        assert buy_resp["is_filled"] is False
        assert buy_resp["status"] == "DATA_UNAVAILABLE"

        # Test SELL with invalid bid
        sell_resp = sandbox.place_order(
            strategy_name="Test",
            symbol="NIFTY 24150 CE",
            security_id="57379",
            transaction_type="SELL",
            quantity=25,
            quote={"ltp": 100.0, "bid": val, "timestamp": now_iso},
        )
        assert sell_resp["is_filled"] is False
        assert sell_resp["status"] == "DATA_UNAVAILABLE"


# ─── 22. STALE QUOTE REJECTED BY FRESHNESS POLICY ───
def test_stale_quote_rejected(tmp_path):
    """Quotes exceeding Config.MAX_QUOTE_AGE_SECONDS must be rejected with DATA_UNAVAILABLE (STALE_QUOTE)."""
    from src.execution.dhan_contract_resolver import is_quote_fresh

    # Verify helper function
    assert is_quote_fresh(None) is False
    assert is_quote_fresh("") is False
    assert is_quote_fresh("invalid-date") is False
    assert is_quote_fresh(datetime.now()) is True
    assert is_quote_fresh((datetime.now() - timedelta(seconds=10)).isoformat()) is True
    # Stale: 600s old exceeds default 300s limit
    assert is_quote_fresh((datetime.now() - timedelta(seconds=600)).isoformat()) is False

    # Verify order rejection in DhanPaperSandbox
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod", state_dir=str(tmp_path))
    stale_iso = (datetime.now() - timedelta(seconds=600)).isoformat()

    stale_quote = {
        "security_id": "57379",
        "ltp": 120.0,
        "ask": 120.5,
        "bid": 119.5,
        "timestamp": stale_iso,
    }
    resp = sandbox.place_order(
        strategy_name="Test",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        quote=stale_quote,
    )

    assert resp["is_filled"] is False
    assert resp["status"] == "DATA_UNAVAILABLE"
    assert "STALE_QUOTE" in resp["reason"]
    assert len(sandbox.trades) == 0


# ─── 23. LTP IS NEVER USED AS AN EXECUTABLE SUBSTITUTE ───
def test_ltp_is_never_used_as_executable_substitute(tmp_path):
    """Verify both functionally and structurally that LTP never substitutes for Bid or Ask."""
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod", state_dir=str(tmp_path))
    now_iso = datetime.now().isoformat()

    # Pass ONLY LTP (ask and bid are None)
    ltp_only_quote = {
        "security_id": "57379",
        "ltp": 150.0,
        "bid": None,
        "ask": None,
        "timestamp": now_iso,
    }

    # BUY attempt must not fill
    buy_resp = sandbox.place_order(
        strategy_name="Test",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="BUY",
        quantity=25,
        quote=ltp_only_quote,
    )
    assert buy_resp["is_filled"] is False
    assert "fill_premium" not in buy_resp

    # SELL attempt must not fill
    sell_resp = sandbox.place_order(
        strategy_name="Test",
        symbol="NIFTY 24150 CE",
        security_id="57379",
        transaction_type="SELL",
        quantity=25,
        quote=ltp_only_quote,
    )
    assert sell_resp["is_filled"] is False
    assert "fill_premium" not in sell_resp

    # Static inspection: check live_paper_session.py for any 'or q["ltp"]' or 'or ltp' in pricing
    import inspect
    import src.execution.live_paper_session as lps
    src_code = inspect.getsource(lps)
    import re
    assert not re.search(r"(bid|ask)\s+or\s+.*ltp", src_code, re.IGNORECASE)
    assert not re.search(r"curr_prem\s*=\s*q\[['\"]ltp['\"]\]", src_code)


# ─── 24. DHAN TIMESTAMP FORMAT VALIDATION ───
def test_dhan_timestamp_formats_parsed_by_is_quote_fresh():
    """Verify Dhan's exchange last_trade_time format (%d/%m/%Y %H:%M:%S) is accurately parsed."""
    from src.execution.dhan_contract_resolver import is_quote_fresh
    
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    assert is_quote_fresh(now_str, max_age_seconds=60) is True

    past_str = (datetime.now() - timedelta(seconds=500)).strftime("%d/%m/%Y %H:%M:%S")
    assert is_quote_fresh(past_str, max_age_seconds=60) is False

    invalid_str = "not-a-timestamp"
    assert is_quote_fresh(invalid_str) is False


# ─── 25. DATA_UNAVAILABLE VALUATION NEVER PUBLISHES NUMERIC P&L ───
def test_data_unavailable_clears_unrealized_pnl_and_reports_cleanly(tmp_path):
    """Verify DATA_UNAVAILABLE sets unrealized_pnl to None and reports write DATA_UNAVAILABLE."""
    from src.execution.live_paper_session import MultiBotLiveSession

    session = MultiBotLiveSession(state_file=str(tmp_path / "test_session.json"),
                                    reports_dir=tmp_path,
                                    risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"))
    s5 = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
    s5["active_trade"] = {
        "id": "TEST-5",
        "strategy": "Strategy 5: Velocity-5 Momentum Scalper",
        "contract": "NIFTY 23500 CE",
        "security_id": "56983",
        "side": "BUY",
        "qty": 65,
        "entry_time": "09:30:00",
        "entry_premium": 100.0,
        "entry_fill": 100.5,
        "target_premium": 130.0,
        "stop_premium": 85.0,
        "current_premium": 105.0,
        "gross_pnl": 325.0,
        "statutory_friction": 65.0,
        "net_pnl": 260.0,
        "unrealized_pnl": 260.0,
        "status": "OPEN",
        "trade_state": "OPEN",
        "valuation_status": "LIVE_QUOTE",
    }

    # Simulate quote dropout: evaluate with missing quote -> valuation paused
    with patch("src.execution.dhan_contract_resolver.DhanContractResolver.fetch_option_quote", return_value=None):
        mkt = {
            "nifty": {"last": 23350.0, "open": 23300.0},
            "bank": {"last": 56300.0, "open": 56250.0},
            "vix": 13.0,
        }
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))

    t5 = s5["active_trade"]
    assert t5["valuation_status"] == "DATA_UNAVAILABLE"
    assert t5["unrealized_pnl"] is None
    assert t5["gross_pnl"] is None
    assert t5["net_pnl"] is None
    assert t5["current_premium"] == 105.0

    # Test report generation writes DATA_UNAVAILABLE, not a numeric P&L
    with patch("src.execution.live_paper_session.REPORTS_DIR", tmp_path):
        session.generate_audit_reports("2026_09_17")

    csv_file = tmp_path / "paper_trades_2026_09_17.csv"
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8")
    assert "DATA_UNAVAILABLE" in content


# ─── 26. DYNAMIC COST CALCULATION MATCHES INDIAN COST MODEL ───
def test_dynamic_cost_calculation_matches_indian_cost_model():
    """Verify IndianCostModel calculates roundtrip costs dynamically conforming to Budget 2024."""
    from src.execution.cost_model import IndianCostModel
    
    costs = IndianCostModel.calculate_roundtrip_costs(
        entry_price=136.50,
        exit_price=180.55,
        quantity=65,
        slippage_points=0.0,
    )
    # Buy turnover = 8872.50, Sell turnover = 11735.75, Total = 20608.25
    # Brokerage: 40.0
    # STT (0.100% on sell): 11.74
    # Exchange (0.050%): 10.30
    # SEBI: 0.02
    # Stamp (0.003% buy): 0.27
    # GST: (40 + 10.30 + 0.02) * 0.18 = 9.06
    # Total statutory: 40 + 11.74 + 10.30 + 0.02 + 0.27 + 9.06 = 71.39
    assert round(costs.brokerage, 2) == 40.0
    assert round(costs.stt, 2) == 11.74
    assert round(costs.exchange_charges, 2) == 10.30
    assert round(costs.gst, 2) == 9.06
    assert round(costs.total_costs, 2) == 71.39
    # Crucially, must NOT equal hardcoded 45.0
    assert costs.total_costs != 45.0


# ─── 27. EXIT SLIPPAGE APPLIED SYMMETRICALLY ───
def test_exit_slippage_applied_symmetrically():
    """Verify BUY adds slippage (ask + 0.50) and SELL subtracts slippage (bid - 0.50)."""
    from src.execution.dhan_paper_trader import DhanPaperSandbox
    
    sandbox = DhanPaperSandbox(client_id="1111273920", access_token="test_token", env="prod")
    now_iso = datetime.now().isoformat()
    quote = {
        "security_id": "56983",
        "ltp": 136.25,
        "bid": 136.0,
        "ask": 136.5,
        "timestamp": now_iso,
    }

    buy_resp = sandbox.place_order(
        strategy_name="Test",
        symbol="NIFTY CE",
        security_id="56983",
        transaction_type="BUY",
        quantity=65,
        quote=quote,
    )
    assert buy_resp["is_filled"] is True
    assert buy_resp["fill_premium"] == 137.0  # 136.5 + 0.50

    sell_resp = sandbox.place_order(
        strategy_name="Test",
        symbol="NIFTY CE",
        security_id="56983",
        transaction_type="SELL",
        quantity=65,
        quote=quote,
    )
    assert sell_resp["is_filled"] is True
    assert sell_resp["fill_premium"] == 135.5  # 136.0 - 0.50


# ─── 28. DHAN INDEX RESOLUTION USES IDX_I ───
def test_dhan_index_resolution_uses_idx_i():
    """Verify DhanContractResolver and DhanDataProvider use IDX_I segment for indices."""
    import inspect
    import src.execution.dhan_contract_resolver as dcr
    import src.data.providers as dp

    dcr_src = inspect.getsource(dcr)
    dp_src = inspect.getsource(dp)

    assert '"IDX_I": [13, 21, 25]' in dcr_src or "'IDX_I': [13, 21, 25]" in dcr_src
    assert 'exchange_segment="IDX_I"' in dp_src
    assert 'instrument="INDEX"' in dp_src


# ─── 29. DATA_UNAVAILABLE AUTHORITATIVE PAYLOAD CANNOT EXPOSE NUMERICAL P&L ───
def test_data_unavailable_authoritative_payload_cannot_expose_numerical_unrealized_pnl(tmp_path):
    """
    Acceptance Test:
    When valuation_status == DATA_UNAVAILABLE:
    1. active_trade.unrealized_pnl MUST be null/None
    2. active_trade.gross_pnl MUST be null/None
    3. active_trade.net_pnl MUST be null/None
    4. Bot session P&L MUST NOT include stale unrealized P&L
    5. /api/status endpoint MUST return null for unrealized_pnl
    """
    import json
    from starlette.testclient import TestClient
    from src.monitoring.dashboard import app

    state_path = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(state_file=str(state_path),
                                    risk_engine=RiskEngine(kill_switch_file=Path(state_path).parent / "ks.json"))
    s1 = session.bot_states["Strategy 1: Apex VRP Engine"]
    s1["active_trade"] = {
        "id": "APEX-STALE-CHECK",
        "contract": "NIFTY STRANGLE",
        "call_security_id": "57023",
        "put_security_id": "56948",
        "side": "SELL",
        "entry_fill": 70.0,
        "qty": 65,
        "current_val": 67.95,
        "valuation_status": "DATA_UNAVAILABLE",
        "gross_pnl": 133.25,
        "net_pnl": 53.25,
        "unrealized_pnl": 53.25,
    }
    s1["net_pnl"] = 53.25

    # 1. Calling save_session sanitizes authoritative state before disk persistence
    session.save_session()

    saved_data = json.loads(state_path.read_text(encoding="utf-8"))
    t1_saved = saved_data["bot_states"]["Strategy 1: Apex VRP Engine"]["active_trade"]
    assert t1_saved["valuation_status"] == "DATA_UNAVAILABLE"
    assert t1_saved["unrealized_pnl"] is None, "Authoritative state unrealized_pnl must be null"
    assert t1_saved["gross_pnl"] is None, "Authoritative state gross_pnl must be null"
    assert t1_saved["net_pnl"] is None, "Authoritative state net_pnl must be null"
    assert saved_data["bot_states"]["Strategy 1: Apex VRP Engine"]["net_pnl"] == 0.0, "Bot net_pnl must not include stale open P&L"

    # 2. Test /api/status payload via TestClient with patched session file
    with patch("src.monitoring.dashboard.Path", return_value=state_path):
        client = TestClient(app)
        resp = client.get("/api/status")
        assert resp.status_code == 200
        payload = resp.json()
        api_t1 = payload["bot_states"]["Strategy 1: Apex VRP Engine"]["active_trade"]
        assert api_t1["unrealized_pnl"] is None, "/api/status must deliver null unrealized_pnl"
        assert api_t1["gross_pnl"] is None, "/api/status must deliver null gross_pnl"
        assert api_t1["net_pnl"] is None, "/api/status must deliver null net_pnl"
        assert payload["bot_states"]["Strategy 1: Apex VRP Engine"]["net_pnl"] == 0.0


# ─── 30. FINAL SETTLEMENT RECONCILES STRICTLY TO CLOSED TRADE LEDGER ───
def test_api_status_final_settlement_reconciles_strictly_to_closed_trade_ledger(tmp_path):
    """
    Verify top-level summary derived strictly from authoritative closed trades:
    total_realized_gross = sum(closed_trade.gross_pnl)
    total_statutory_friction = sum(closed_trade.statutory_friction)
    total_net_realized_pnl = sum(closed_trade.net_pnl)

    Must NOT include DATA_UNAVAILABLE open-position P&L.
    Must NOT include unrealized P&L in realized totals.
    For the current session trades (GAMMA-8585, VELOCITY-8585, SNIPER-LIVE-8585):
    Gross: 5674.50, Costs: 155.00, Net: 5519.50.
    """
    import json
    from starlette.testclient import TestClient
    from src.monitoring.dashboard import app

    state_path = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(state_file=str(state_path),
                                    risk_engine=RiskEngine(kill_switch_file=Path(state_path).parent / "ks.json"))

    # Bot with an open trade under DATA_UNAVAILABLE (must NOT be counted in realized totals)
    s1 = session.bot_states["Strategy 1: Apex VRP Engine"]
    s1["active_trade"] = {
        "id": "APEX-OPEN",
        "valuation_status": "DATA_UNAVAILABLE",
        "gross_pnl": None,
        "net_pnl": None,
        "unrealized_pnl": None,
    }

    # Populate the 3 closed trades from today's session
    s3 = session.bot_states["Strategy 3: Confluence Gamma Scalper"]
    s3["closed_trades"] = [
        {"id": "GAMMA-8585", "gross_pnl": -1189.50, "statutory_friction": 45.00, "net_pnl": -1234.50}
    ]
    s3["net_pnl"] = -1234.50

    s5 = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
    s5["closed_trades"] = [
        {"id": "VELOCITY-8585", "gross_pnl": 2863.25, "statutory_friction": 45.00, "net_pnl": 2818.25}
    ]
    s5["net_pnl"] = 2818.25

    s6 = session.bot_states["Strategy 6: Micro Momentum Sniper"]
    s6["closed_trades"] = [
        {"id": "SNIPER-LIVE-8585", "gross_pnl": 4000.75, "statutory_friction": 65.00, "net_pnl": 3935.75}
    ]
    s6["net_pnl"] = 3935.75

    session.save_session()

    # Verify saved session has correct final_settlement
    saved_data = json.loads(state_path.read_text(encoding="utf-8"))
    settlement = saved_data.get("final_settlement", {})
    assert settlement["total_realized_gross"] == 5674.50
    assert settlement["total_statutory_friction"] == 155.00
    assert settlement["total_net_realized_pnl"] == 5519.50
    assert settlement["total_closed_trades"] == 3

    # Verify /api/status payload delivers reconciled settlement
    with patch("src.monitoring.dashboard.Path", return_value=state_path):
        client = TestClient(app)
        resp = client.get("/api/status")
        assert resp.status_code == 200
        payload = resp.json()
        api_settlement = payload.get("final_settlement", {})
        assert api_settlement["total_realized_gross"] == 5674.50
        assert api_settlement["total_statutory_friction"] == 155.00
        assert api_settlement["total_net_realized_pnl"] == 5519.50
        assert api_settlement["total_closed_trades"] == 3




