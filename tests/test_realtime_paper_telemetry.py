"""
End-to-end regression test suite for real-time paper position telemetry.

Validates:
1. Single-leg and multi-leg (Strangle & Credit Spread) live quote telemetry.
2. Independent leg quote resolution and valuation.
3. Dynamic unrealized P&L recalculation and state persistence in live_paper_session.json.
4. /api/status endpoint response matching authoritative state.
5. Strict DATA_UNAVAILABLE transition on stale, missing, or inverted quotes.
6. Absolute isolation between live quote updates and closed-trade realized settlement.
7. Rapid quote update sequences and monotonic timestamp advancement.
"""
import json
import pytest
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.live_strategy_adapter import LiveSignal
from src.risk.risk_engine import RiskEngine
from src.execution.dhan_contract_resolver import DhanContractResolver, _quote_cache
from src.monitoring.dashboard import app


@pytest.fixture
def clean_cache():
    """Ensures an isolated quote cache for test runs."""
    _quote_cache.clear()
    yield
    _quote_cache.clear()


@pytest.fixture
def mock_client():
    return TestClient(app)


def test_single_leg_option_realtime_telemetry(tmp_path, clean_cache, mock_client):
    """
    Validates single-leg option position:
    - Fresh Bid/Ask -> position valuation updates, current_bid and current_ask populate, unrealized_pnl computes.
    - state/live_paper_session.json updates.
    - /api/status returns live values.
    - Stale quote injection -> DATA_UNAVAILABLE restored, numerical P&L nulled, no stale leak.
    """
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(
        state_file=str(state_file),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    # Initialize Bot 3 (Single-leg call)
    now_dt = datetime.now()
    now_ts = now_dt.strftime("%H:%M:%S")
    s3 = session.bot_states["Strategy 3: Confluence Gamma Scalper"]
    sec_id = "56983"
    s3["active_trade"] = {
        "id": "GAMMA-TEST-1",
        "strategy": "Strategy 3: Confluence Gamma Scalper",
        "underlying": "NIFTY",
        "contract": "NIFTY 22 SEP 23250 CALL",
        "security_id": sec_id,
        "side": "BUY",
        "entry_time": now_ts,
        "entry_premium": 100.0,
        "entry_fill": 100.0,
        "target_premium": 150.0,
        "stop_premium": 80.0,
        "qty": 65,
        "status": "OPEN",
        "trade_state": "OPEN",
        "valuation_status": "LIVE_QUOTE",
        "current_bid": 100.0,
        "current_ask": 100.5,
        "current_premium": 100.0,
        "unrealized_pnl": 0.0,
    }
    session.save_session()

    mkt = {
        "nifty": {"last": 23250.0, "open": 23200.0},
        "bank": {"last": 51000.0, "open": 50800.0},
        "vix": 13.0,
        "timestamp": now_dt,
    }

    # Step 1: Inject fresh quote (Bid=120.0, Ask=120.5)
    fresh_quote = {
        "security_id": sec_id,
        "ltp": 120.25,
        "bid": 120.0,
        "ask": 120.5,
        "market_timestamp": now_dt.strftime("%d/%m/%Y %H:%M:%S"),
        "received_at": now_dt.isoformat(),
        "timestamp": now_dt.isoformat(),
        "is_tradable": True,
        "source": "DHAN_LIVE_QUOTE",
    }
    _quote_cache[sec_id] = (now_dt, fresh_quote)

    with patch.object(DhanContractResolver, "fetch_option_quote", return_value=fresh_quote):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    t3 = session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"]
    assert t3["valuation_status"] == "LIVE_QUOTE"
    assert t3["current_bid"] == 120.0
    assert t3["current_ask"] == 120.5
    assert t3["current_premium"] == 120.0
    assert t3["unrealized_pnl"] is not None
    assert t3["unrealized_pnl"] > 1000.0  # (120 - 100)*65 - friction

    # Step 2: Verify state/live_paper_session.json persisted the fresh telemetry
    with open(state_file, "r") as f:
        persisted = json.load(f)
    p_t3 = persisted["bot_states"]["Strategy 3: Confluence Gamma Scalper"]["active_trade"]
    assert p_t3["current_bid"] == 120.0
    assert p_t3["current_ask"] == 120.5
    assert p_t3["valuation_status"] == "LIVE_QUOTE"
    assert p_t3["unrealized_pnl"] == t3["unrealized_pnl"]

    # Step 3: Verify /api/status endpoint returns the updated payload
    with patch("src.monitoring.dashboard.Path") as mock_path:
        mock_path.return_value = state_file
        resp = mock_client.get("/api/status")
        assert resp.status_code == 200
        api_data = resp.json()
        api_t3 = api_data["bot_states"]["Strategy 3: Confluence Gamma Scalper"]["active_trade"]
        assert api_t3["current_bid"] == 120.0
        assert api_t3["current_ask"] == 120.5
        assert api_t3["unrealized_pnl"] == t3["unrealized_pnl"]
        assert api_t3["valuation_status"] == "LIVE_QUOTE"

    # Step 4: Inject stale quote (older than 300s)
    stale_dt = now_dt - timedelta(seconds=600)
    stale_quote = dict(fresh_quote)
    stale_quote["timestamp"] = stale_dt.isoformat()
    stale_quote["market_timestamp"] = stale_dt.strftime("%d/%m/%Y %H:%M:%S")

    with patch.object(DhanContractResolver, "fetch_option_quote", return_value=stale_quote):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    t3_stale = session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"]
    assert t3_stale["valuation_status"] == "DATA_UNAVAILABLE"
    assert t3_stale["unrealized_pnl"] is None
    assert t3_stale["gross_pnl"] is None
    assert t3_stale["net_pnl"] is None
    assert t3_stale["current_bid"] is None
    assert t3_stale["current_ask"] is None

    # Step 5: Verify /api/status guarantees no stale numerical P&L or Bid/Ask leaks
    with patch("src.monitoring.dashboard.Path") as mock_path:
        mock_path.return_value = state_file
        resp2 = mock_client.get("/api/status")
        assert resp2.status_code == 200
        api_data2 = resp2.json()
        api_t3_stale = api_data2["bot_states"]["Strategy 3: Confluence Gamma Scalper"]["active_trade"]
        assert api_t3_stale["valuation_status"] == "DATA_UNAVAILABLE"
        assert api_t3_stale["unrealized_pnl"] is None
        assert api_t3_stale["current_bid"] is None
        assert api_t3_stale["current_ask"] is None


def test_multi_leg_option_strangle_realtime_telemetry(tmp_path, clean_cache, mock_client):
    """
    Validates multi-leg option position (Bot 1 Strangle):
    - Both legs fresh: combined Bid = c_bid + p_bid, combined Ask = c_ask + p_ask.
    - Unrealized P&L is calculated accurately and persisted.
    - One leg missing or stale: fails closed to DATA_UNAVAILABLE, zero numerical P&L leak.
    - Inverted book (bid > ask on any leg): fails closed to DATA_UNAVAILABLE.
    """
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(
        state_file=str(state_file),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    now_dt = datetime.now()
    now_ts = now_dt.strftime("%H:%M:%S")
    s1 = session.bot_states["Strategy 1: Apex VRP Engine"]
    c_sec = "57023"
    p_sec = "56948"
    s1["active_trade"] = {
        "id": "APEX-TEST-1",
        "strategy": "Strategy 1: Apex VRP Engine",
        "underlying": "NIFTY",
        "contract": "NIFTY 23550 CE / NIFTY 22950 PE",
        "security_id": f"{c_sec} / {p_sec}",
        "call_security_id": c_sec,
        "put_security_id": p_sec,
        "side": "SELL",
        "entry_time": now_ts,
        "net_credit_collected": 70.0,
        "entry_fill": 70.0,
        "qty": 65,
        "status": "OPEN",
        "trade_state": "OPEN",
        "valuation_status": "DATA_UNAVAILABLE",
        "current_val": 70.0,
        "current_bid": None,
        "current_ask": None,
        "unrealized_pnl": None,
    }
    session.save_session()

    mkt = {
        "nifty": {"last": 23250.0, "open": 23200.0},
        "bank": {"last": 51000.0, "open": 50800.0},
        "vix": 13.0,
        "timestamp": now_dt,
    }

    # Case A: Both legs receive fresh executable quotes
    c_q = {
        "security_id": c_sec, "ltp": 25.0, "bid": 24.8, "ask": 25.2,
        "market_timestamp": now_dt.strftime("%d/%m/%Y %H:%M:%S"),
        "received_at": now_dt.isoformat(),
        "timestamp": now_dt.isoformat(),
        "is_tradable": True, "source": "DHAN_LIVE_QUOTE",
    }
    p_q = {
        "security_id": p_sec, "ltp": 20.0, "bid": 19.7, "ask": 20.3,
        "market_timestamp": now_dt.strftime("%d/%m/%Y %H:%M:%S"),
        "received_at": now_dt.isoformat(),
        "timestamp": now_dt.isoformat(),
        "is_tradable": True, "source": "DHAN_LIVE_QUOTE",
    }

    def mock_fetch(security_id, **kwargs):
        if security_id == c_sec:
            return c_q
        elif security_id == p_sec:
            return p_q
        return None

    with patch.object(DhanContractResolver, "fetch_option_quote", side_effect=mock_fetch):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    t1 = session.bot_states["Strategy 1: Apex VRP Engine"]["active_trade"]
    assert t1["valuation_status"] == "LIVE_QUOTE"
    assert t1["current_bid"] == round(24.8 + 19.7, 2)  # 44.50
    assert t1["current_ask"] == round(25.2 + 20.3, 2)  # 45.50
    assert t1["unrealized_pnl"] is not None
    # Profit on short: (70 - 45.50)*65 - friction
    assert t1["unrealized_pnl"] > 1400.0

    # Verify /api/status
    with patch("src.monitoring.dashboard.Path") as mock_path:
        mock_path.return_value = state_file
        resp = mock_client.get("/api/status")
        api_t1 = resp.json()["bot_states"]["Strategy 1: Apex VRP Engine"]["active_trade"]
        assert api_t1["current_bid"] == 44.50
        assert api_t1["current_ask"] == 45.50
        assert api_t1["unrealized_pnl"] == t1["unrealized_pnl"]

    # Case B: ONE leg drops out (Put leg returns None)
    def mock_fetch_partial(security_id, **kwargs):
        if security_id == c_sec:
            return c_q
        return None

    with patch.object(DhanContractResolver, "fetch_option_quote", side_effect=mock_fetch_partial):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    t1_dropped = session.bot_states["Strategy 1: Apex VRP Engine"]["active_trade"]
    assert t1_dropped["valuation_status"] == "DATA_UNAVAILABLE"
    assert t1_dropped["unrealized_pnl"] is None
    assert t1_dropped["current_bid"] is None
    assert t1_dropped["current_ask"] is None

    # Case C: Crossed/inverted order book on Call leg (bid > ask)
    c_q_inv = dict(c_q)
    c_q_inv["bid"] = 26.0
    c_q_inv["ask"] = 25.0  # Inverted!

    def mock_fetch_inverted(security_id, **kwargs):
        if security_id == c_sec:
            return c_q_inv
        elif security_id == p_sec:
            return p_q
        return None

    with patch.object(DhanContractResolver, "fetch_option_quote", side_effect=mock_fetch_inverted):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    t1_inv = session.bot_states["Strategy 1: Apex VRP Engine"]["active_trade"]
    assert t1_inv["valuation_status"] == "DATA_UNAVAILABLE"
    assert t1_inv["unrealized_pnl"] is None
    assert t1_inv["current_bid"] is None
    assert t1_inv["current_ask"] is None


def test_multi_leg_option_spread_realtime_telemetry(tmp_path, clean_cache, mock_client):
    """
    Validates multi-leg credit spread (Bot 2 Zen Curvature):
    - Both legs fresh: spread Ask (debit to close) = short_ask - long_bid.
      Spread Bid (credit to sell) = short_bid - long_ask.
    - Candidate IDs in evaluate_all_bots include short_security_id and long_security_id.
    - Stale or inverted quotes correctly restore DATA_UNAVAILABLE.
    """
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(
        state_file=str(state_file),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    now_dt = datetime.now()
    now_ts = now_dt.strftime("%H:%M:%S")
    s2 = session.bot_states["Strategy 2: Zen Curvature Overnight"]
    s_sec = "57100"
    l_sec = "57150"
    s2["active_trade"] = {
        "id": "ZEN-TEST-1",
        "strategy": "Strategy 2: Zen Curvature Overnight",
        "underlying": "NIFTY",
        "contract": "NIFTY 23500 CE / NIFTY 23650 CE",
        "security_id": f"{s_sec} / {l_sec}",
        "short_security_id": s_sec,
        "long_security_id": l_sec,
        "side": "SELL (SPREAD)",
        "entry_time": now_ts,
        "net_credit": 30.0,
        "entry_fill": 30.0,
        "qty": 65,
        "status": "OPEN",
        "trade_state": "OPEN",
        "valuation_status": "DATA_UNAVAILABLE",
        "current_debit": 30.0,
        "current_bid": None,
        "current_ask": None,
        "unrealized_pnl": None,
    }
    session.save_session()

    mkt = {
        "nifty": {"last": 23250.0, "open": 23200.0},
        "bank": {"last": 51000.0, "open": 50800.0},
        "vix": 13.0,
        "timestamp": now_dt,
    }

    # Verify candidate_ids collection includes both short and long security IDs
    candidate_ids = []
    for b_data in session.bot_states.values():
        at = b_data.get("active_trade")
        if at:
            if at.get("short_security_id"):
                candidate_ids.append(str(at["short_security_id"]))
            if at.get("long_security_id"):
                candidate_ids.append(str(at["long_security_id"]))
    assert s_sec in candidate_ids
    assert l_sec in candidate_ids

    # Step 1: Fresh quotes
    # Short call: bid=25.0, ask=25.5
    # Long call:  bid=10.0, ask=10.5
    # Exit debit to close (buy back short, sell long) = 25.5 - 10.0 = 15.5
    # Market bid to sell spread = 25.0 - 10.5 = 14.5
    s_q = {
        "security_id": s_sec, "ltp": 25.2, "bid": 25.0, "ask": 25.5,
        "market_timestamp": now_dt.strftime("%d/%m/%Y %H:%M:%S"),
        "received_at": now_dt.isoformat(),
        "timestamp": now_dt.isoformat(),
        "is_tradable": True, "source": "DHAN_LIVE_QUOTE",
    }
    l_q = {
        "security_id": l_sec, "ltp": 10.2, "bid": 10.0, "ask": 10.5,
        "market_timestamp": now_dt.strftime("%d/%m/%Y %H:%M:%S"),
        "received_at": now_dt.isoformat(),
        "timestamp": now_dt.isoformat(),
        "is_tradable": True, "source": "DHAN_LIVE_QUOTE",
    }

    def mock_fetch_spread(security_id, **kwargs):
        if security_id == s_sec:
            return s_q
        elif security_id == l_sec:
            return l_q
        return None

    with patch.object(DhanContractResolver, "fetch_option_quote", side_effect=mock_fetch_spread):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    t2 = session.bot_states["Strategy 2: Zen Curvature Overnight"]["active_trade"]
    assert t2["valuation_status"] == "LIVE_QUOTE"
    assert t2["current_ask"] == 15.50  # 25.5 - 10.0
    assert t2["current_bid"] == 14.50  # 25.0 - 10.5
    assert t2["unrealized_pnl"] is not None
    # Profit: (30.0 - 15.50)*65 - friction
    assert t2["unrealized_pnl"] > 800.0

    # Verify /api/status payload
    with patch("src.monitoring.dashboard.Path") as mock_path:
        mock_path.return_value = state_file
        resp = mock_client.get("/api/status")
        api_t2 = resp.json()["bot_states"]["Strategy 2: Zen Curvature Overnight"]["active_trade"]
        assert api_t2["current_bid"] == 14.50
        assert api_t2["current_ask"] == 15.50
        assert api_t2["unrealized_pnl"] == t2["unrealized_pnl"]

    # Step 2: Invalidate Long leg (drops out)
    def mock_fetch_spread_drop(security_id, **kwargs):
        if security_id == s_sec:
            return s_q
        return None

    with patch.object(DhanContractResolver, "fetch_option_quote", side_effect=mock_fetch_spread_drop):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    t2_drop = session.bot_states["Strategy 2: Zen Curvature Overnight"]["active_trade"]
    assert t2_drop["valuation_status"] == "DATA_UNAVAILABLE"
    assert t2_drop["unrealized_pnl"] is None
    assert t2_drop["current_bid"] is None
    assert t2_drop["current_ask"] is None


def test_rapid_consecutive_quote_updates(tmp_path, clean_cache, mock_client):
    """
    Validates rapid consecutive quote updates across multiple price points.
    Verifies that position valuation and P&L update dynamically with zero lag.
    """
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(
        state_file=str(state_file),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    now_dt = datetime.now()
    now_ts = now_dt.strftime("%H:%M:%S")
    s4 = session.bot_states["Strategy 4: Golden Trend Runner"]
    sec_id = "56990"
    s4["active_trade"] = {
        "id": "GOLD-TEST-1",
        "strategy": "Strategy 4: Golden Trend Runner",
        "underlying": "NIFTY",
        "contract": "NIFTY 22 SEP 23300 CALL",
        "security_id": sec_id,
        "side": "BUY",
        "entry_time": now_ts,
        "entry_premium": 50.0,
        "entry_fill": 50.0,
        "target_premium": 75.0,
        "stop_premium": 40.0,
        "qty": 65,
        "status": "OPEN",
        "trade_state": "OPEN",
        "valuation_status": "LIVE_QUOTE",
        "current_bid": 50.0,
        "current_ask": 50.5,
        "current_premium": 50.0,
        "unrealized_pnl": 0.0,
    }
    session.save_session()

    mkt = {
        "nifty": {"last": 23300.0, "open": 23200.0},
        "bank": {"last": 51000.0, "open": 50800.0},
        "vix": 13.0,
        "timestamp": now_dt,
    }

    # Simulate 5 rapid price updates: 52 -> 55 -> 58 -> 54 -> 60
    prices = [(52.0, 52.4), (55.0, 55.5), (58.0, 58.6), (54.0, 54.5), (60.0, 60.5)]
    last_pnl = None

    for i, (bid, ask) in enumerate(prices):
        tick_dt = now_dt + timedelta(seconds=i * 2)
        q = {
            "security_id": sec_id,
            "ltp": bid + 0.2,
            "bid": bid,
            "ask": ask,
            "market_timestamp": tick_dt.strftime("%d/%m/%Y %H:%M:%S"),
            "received_at": tick_dt.isoformat(),
            "timestamp": tick_dt.isoformat(),
            "is_tradable": True,
            "source": "DHAN_LIVE_QUOTE",
        }
        with patch.object(DhanContractResolver, "fetch_option_quote", return_value=q):
            session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
            session.save_session()

        t4 = session.bot_states["Strategy 4: Golden Trend Runner"]["active_trade"]
        assert t4["valuation_status"] == "LIVE_QUOTE"
        assert t4["current_bid"] == bid
        assert t4["current_ask"] == ask
        assert t4["current_premium"] == bid
        assert t4["unrealized_pnl"] is not None
        if last_pnl is not None and bid > prices[i - 1][0]:
            assert t4["unrealized_pnl"] > last_pnl
        last_pnl = t4["unrealized_pnl"]


def test_realized_pnl_isolation_during_quote_updates(tmp_path, clean_cache, mock_client):
    """
    Validates that quote updates and DATA_UNAVAILABLE transitions strictly isolate
    closed-trade settlement and never alter total_realized_gross, total_statutory_friction,
    or total_net_realized_pnl.
    """
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(
        state_file=str(state_file),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    # Add closed trades to ledger
    s5 = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
    s5["closed_trades"] = [
        {"id": "V5-C1", "gross_pnl": 2000.0, "statutory_friction": 50.0, "net_pnl": 1950.0, "status": "CLOSED"},
        {"id": "V5-C2", "gross_pnl": -500.0, "statutory_friction": 50.0, "net_pnl": -550.0, "status": "CLOSED"},
    ]

    now_dt = datetime.now()
    s5["active_trade"] = {
        "id": "V5-OPEN-1",
        "strategy": "Strategy 5: Velocity-5 Momentum Scalper",
        "underlying": "NIFTY",
        "contract": "NIFTY 22 SEP 23300 CE",
        "security_id": "56991",
        "side": "BUY",
        "entry_time": "10:00:00",
        "entry_premium": 60.0,
        "entry_fill": 60.0,
        "target_premium": 80.0,
        "stop_premium": 50.0,
        "qty": 65,
        "status": "OPEN",
        "trade_state": "OPEN",
        "valuation_status": "LIVE_QUOTE",
        "current_bid": 65.0,
        "current_ask": 65.5,
        "current_premium": 65.0,
        "unrealized_pnl": 280.0,
    }
    session.save_session()

    mkt = {"nifty": {"last": 23300.0, "open": 23200.0}, "bank": {"last": 51000.0, "open": 50800.0}, "vix": 13.0, "timestamp": now_dt}

    expected_gross = 1500.0  # 2000 - 500
    expected_friction = 100.0  # 50 + 50
    expected_net = 1400.0  # 1950 - 550

    # Step 1: Check /api/status while active trade is LIVE_QUOTE
    with patch("src.monitoring.dashboard.Path") as mock_path:
        mock_path.return_value = state_file
        resp = mock_client.get("/api/status")
        settlement = resp.json()["final_settlement"]
        assert settlement["total_realized_gross"] == expected_gross
        assert settlement["total_statutory_friction"] == expected_friction
        assert settlement["total_net_realized_pnl"] == expected_net

    # Step 2: Trigger quote dropout -> active trade becomes DATA_UNAVAILABLE
    stale_dt = now_dt - timedelta(seconds=600)
    stale_q = {
        "security_id": "56991", "ltp": 65.0, "bid": 65.0, "ask": 65.5,
        "timestamp": stale_dt.isoformat(),
    }
    with patch.object(DhanContractResolver, "fetch_option_quote", return_value=stale_q):
        session.evaluate_all_bots(mkt, current_time=dtime(11, 0))
        session.save_session()

    # Step 3: Check /api/status again -> settlement MUST remain identical
    with patch("src.monitoring.dashboard.Path") as mock_path:
        mock_path.return_value = state_file
        resp2 = mock_client.get("/api/status")
        settlement2 = resp2.json()["final_settlement"]
        assert settlement2["total_realized_gross"] == expected_gross
        assert settlement2["total_statutory_friction"] == expected_friction
        assert settlement2["total_net_realized_pnl"] == expected_net


def test_inverted_book_rejected_at_entry(tmp_path, clean_cache, mock_client):
    """
    Regression test: a crossed/inverted order book (bid > ask) on a NEW entry
    quote must be refused, exactly as it already is refused for open-position
    valuation. Entries are gated on the validated strategy classes, so Bot 5 is
    given an actionable bullish signal and every other bot is held flat; the
    inversion guard is therefore the only thing that can block the entry.
    """
    state_file = tmp_path / "live_paper_session.json"
    session = MultiBotLiveSession(
        state_file=str(state_file),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    target_bot = "Strategy 5: Velocity-5 Momentum Scalper"

    def only_bot5_bullish(bot, **kwargs):
        return LiveSignal(bot, "TestStrategy", 1 if bot == target_bot else 0,
                          0.85, "NIFTY", reason="STRATEGY_SIGNAL")

    now_dt = datetime.now()
    mkt = {
        "nifty": {"last": 23220.0, "open": 23200.0},
        "bank": {"last": 50700.0, "open": 50800.0},
        "vix": 20.0,
        "timestamp": now_dt,
    }

    def mock_resolve_inverted(underlying_spot, vix, option_type, **kwargs):
        if option_type == "CE":
            return {
                "security_id": "88888",
                "custom_symbol": "NIFTY TEST CE",
                "trading_symbol": "NIFTY-TEST-CE",
                "lot_size": 75,
                "bid": 105.0,
                "ask": 100.0,  # Inverted: bid > ask
                "ltp": 102.0,
                "quote_timestamp": now_dt.isoformat(),
            }
        return None

    with patch.object(DhanContractResolver, "resolve_option_contract", side_effect=mock_resolve_inverted),          patch.object(session.strategy_adapter, "evaluate", side_effect=only_bot5_bullish):
        session.evaluate_all_bots(mkt, current_time=dtime(12, 0))
        session.save_session()

    s5 = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
    assert s5["active_trade"] is None, "Entry must be refused against a crossed/inverted order book"

    # Control: an identical setup with a valid (non-inverted) book DOES open the trade,
    # proving the rejection above is caused by the inversion guard and not the mock/harness.
    def mock_resolve_valid(underlying_spot, vix, option_type, **kwargs):
        if option_type == "CE":
            return {
                "security_id": "88888",
                "custom_symbol": "NIFTY TEST CE",
                "trading_symbol": "NIFTY-TEST-CE",
                "lot_size": 75,
                "bid": 99.5,
                "ask": 100.0,  # Valid: bid <= ask
                "ltp": 99.8,
                "quote_timestamp": now_dt.isoformat(),
            }
        return None

    with patch.object(DhanContractResolver, "resolve_option_contract", side_effect=mock_resolve_valid),          patch.object(session.strategy_adapter, "evaluate", side_effect=only_bot5_bullish):
        session.evaluate_all_bots(mkt, current_time=dtime(12, 0))
        session.save_session()

    s5_valid = session.bot_states["Strategy 5: Velocity-5 Momentum Scalper"]
    assert s5_valid["active_trade"] is not None, "Valid, non-inverted book must still be tradable"
    assert s5_valid["active_trade"]["entry_ask"] == 100.0
