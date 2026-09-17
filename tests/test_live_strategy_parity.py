"""
Regression suite for blocker B1 — live/backtest strategy parity.

Before the fix the live session decided entries with inline threshold rules
("spot moved N points since process start") while the validated strategy classes
in src/strategies/ were never imported by the live path. These tests prove the
live path now delegates to the real strategy objects and refuses to trade when
those objects do not produce an actionable signal.
"""
from datetime import date, time as dtime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.execution import live_market_bars
from src.execution.live_strategy_adapter import (
    STRATEGY_BINDINGS,
    LiveSignal,
    LiveStrategyAdapter,
)
from src.execution.live_paper_session import MultiBotLiveSession
from src.risk.risk_engine import RiskEngine


EXPECTED_CLASSES = {
    "Strategy 1: Apex VRP Engine": "NiftyWeeklyIronCondorStrategy",
    "Strategy 2: Zen Curvature Overnight": "CurvatureCreditSpreadStrategy",
    "Strategy 3: Confluence Gamma Scalper": "ConfluenceGammaScalperStrategy",
    "Strategy 4: Golden Trend Runner": "GoldenTrendOptionBuyerStrategy",
    "Strategy 5: Velocity-5 Momentum Scalper": "ActiveMomentumOptionScalperStrategy",
    "Strategy 6: Micro Momentum Sniper": "MicroMomentumBuyerStrategy",
}

SESSION_BAR = {
    "open": 23201.6, "high": 23284.75, "low": 23116.1,
    "close": 23217.6, "volume": 250000.0, "source": "TEST_INTRADAY",
}


@pytest.fixture
def session(tmp_path):
    live_market_bars.clear_session_bar_cache()
    s = MultiBotLiveSession(
        state_file=str(tmp_path / "session.json"),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )
    yield s
    live_market_bars.clear_session_bar_cache()


def _mkt():
    return {
        "nifty": {"last": 23217.6, "open": 23201.6},
        "bank": {"last": 56292.4, "open": 56007.6},
        "vix": 13.2,
        "timestamp": pd.Timestamp("2026-09-17 11:00:00"),
    }


# ─── BINDING CORRECTNESS ───

def test_every_bot_binds_to_its_validated_strategy_class():
    """Each live bot must resolve to the real, validated strategy class."""
    adapter = LiveStrategyAdapter()
    for bot_name, expected_cls in EXPECTED_CLASSES.items():
        strategy = adapter.get_strategy(bot_name)
        assert strategy is not None, f"{bot_name} has no strategy instance"
        assert type(strategy).__name__ == expected_cls
        assert STRATEGY_BINDINGS[bot_name]["class"] == expected_cls


def test_strategy_instances_use_validated_default_parameters():
    """The adapter must not override any validated strategy parameter."""
    adapter = LiveStrategyAdapter()
    from src.strategies.confluence_scalper import ConfluenceGammaScalperStrategy
    from src.strategies.micro_momentum_buyer import MicroMomentumBuyerStrategy

    live_conf = adapter.get_strategy("Strategy 3: Confluence Gamma Scalper")
    ref_conf = ConfluenceGammaScalperStrategy()
    assert live_conf.bb_period == ref_conf.bb_period
    assert live_conf.bb_std == ref_conf.bb_std
    assert live_conf.squeeze_quantile == ref_conf.squeeze_quantile

    live_micro = adapter.get_strategy("Strategy 6: Micro Momentum Sniper")
    ref_micro = MicroMomentumBuyerStrategy()
    assert live_micro.max_vix == ref_micro.max_vix


def test_live_session_no_longer_contains_inline_threshold_rules():
    """The inline spot-vs-open threshold rules must be gone from the live path."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    for banned in ["n_open + 15.0", "n_open - 15.0", "n_open + 10.0",
                   "n_open - 25.0", "n_open + 25.0", "abs(n_last - n_open)"]:
        assert banned not in src, f"Inline threshold rule still present: {banned}"


def test_live_session_imports_the_strategy_adapter():
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    assert "from src.execution.live_strategy_adapter import" in src


# ─── THE LIVE PATH ACTUALLY CALLS THE STRATEGY ───

def test_evaluate_all_bots_invokes_real_generate_signals(session):
    """evaluate_all_bots must call generate_signals on the real classes."""
    called = []
    real_eval = session.strategy_adapter.evaluate

    def spy(bot_name, **kwargs):
        called.append(bot_name)
        return real_eval(bot_name, **kwargs)

    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR), \
         patch.object(session.strategy_adapter, "evaluate", side_effect=spy):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))

    assert set(called) == set(EXPECTED_CLASSES.keys()), "Every bot must be strategy-evaluated"


def test_strategy_class_is_published_to_state(session):
    """State must record the strategy class actually executing (dashboard truth)."""
    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))

    for bot_name, expected_cls in EXPECTED_CLASSES.items():
        assert session.bot_states[bot_name]["strategy_class"] == expected_cls
        assert "live_signal" in session.bot_states[bot_name]


def test_flat_strategy_signal_blocks_entry(session):
    """A flat strategy signal must produce no position, whatever the spot move."""
    flat = lambda bot, **kw: LiveSignal(bot, "X", 0, 0.0, "NIFTY", reason="NO_SIGNAL: strategy flat")
    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR), \
         patch.object(session.strategy_adapter, "evaluate", side_effect=flat):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))

    for bot_name in EXPECTED_CLASSES:
        assert session.bot_states[bot_name]["active_trade"] is None


def test_actionable_signal_reaches_contract_resolution(session):
    """A bullish strategy signal must drive the bot to resolve a CE contract."""
    bullish = lambda bot, **kw: LiveSignal(bot, "X", 1, 0.85, "NIFTY", reason="STRATEGY_SIGNAL")
    seen = []

    def fake_resolve(spot, vix, option_type, **kwargs):
        seen.append(option_type)
        return None  # fail closed after the call — we only assert it was reached

    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR), \
         patch.object(session.strategy_adapter, "evaluate", side_effect=bullish), \
         patch("src.execution.live_paper_session.DhanContractResolver.resolve_option_contract",
               side_effect=fake_resolve):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))

    assert "CE" in seen, "Bullish strategy signal must reach CE contract resolution"


def test_bearish_signal_selects_put_contract(session):
    """
    A bearish signal must route the directional bot to a PE contract, never a CE.
    Only Bot 5 is made actionable here; the multi-leg bots legitimately resolve
    both a CE and a PE leg, which would otherwise mask the assertion.
    """
    target = "Strategy 5: Velocity-5 Momentum Scalper"

    def bearish(bot, **kw):
        direction = -1 if bot == target else 0
        return LiveSignal(bot, "X", direction, 0.85, "NIFTY", reason="STRATEGY_SIGNAL")

    seen = []

    def fake_resolve(spot, vix, option_type, **kwargs):
        seen.append(option_type)
        return None

    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR), \
         patch.object(session.strategy_adapter, "evaluate", side_effect=bearish), \
         patch("src.execution.live_paper_session.DhanContractResolver.resolve_option_contract",
               side_effect=fake_resolve):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))

    assert "PE" in seen
    assert "CE" not in seen, "Bearish signal must not open a CE position"


# ─── FAIL-CLOSED ON MISSING STATE ───

def test_adapter_fails_closed_without_session_bar():
    adapter = LiveStrategyAdapter()
    with patch.object(live_market_bars, "get_today_session_bar", return_value=None):
        sig = adapter.evaluate("Strategy 3: Confluence Gamma Scalper", session_bar=None, today_vix=13.0)
    assert sig.direction == 0
    assert "DATA_UNAVAILABLE" in sig.reason


def test_adapter_fails_closed_without_vix_for_vix_dependent_strategy():
    """VIX-dependent strategies must not silently use a hardcoded default VIX."""
    adapter = LiveStrategyAdapter()
    sig = adapter.evaluate(
        "Strategy 6: Micro Momentum Sniper",
        session_bar=SESSION_BAR, today_vix=None, trading_day=date(2026, 9, 17),
    )
    assert sig.direction == 0
    assert "DATA_UNAVAILABLE" in sig.reason


def test_signal_discloses_forming_bar_semantics():
    """
    Live signals must disclose that they run on an unsettled forming bar.

    Uses Bot 6, the only strategy whose research semantics legitimately support
    forming-bar evaluation (H3); Bots 3/4/5 now refuse a partial bar outright.
    """
    adapter = LiveStrategyAdapter()
    sig = adapter.evaluate(
        "Strategy 6: Micro Momentum Sniper",
        session_bar=SESSION_BAR, today_vix=13.2, trading_day=date(2026, 9, 17),
    )
    assert sig.on_forming_bar is True
    assert sig.bar_source == "TEST_INTRADAY"
