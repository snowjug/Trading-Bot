"""
Unit tests for the Forward Paper Trading Engine.
Verifies fail-closed live trading prevention, multi-account capital gates,
per-leg P&L reconciliation, and slippage stress scaling.
"""
import pytest
from datetime import date
import pandas as pd

from src.config import Config
from src.execution.forward_paper_engine import ForwardPaperEngine, PaperLeg, PaperTrade


def test_fail_closed_live_trading_assertion(monkeypatch):
    monkeypatch.setattr(Config, "LIVE_TRADING_ENABLED", True)
    with pytest.raises(RuntimeError, match="FAIL CLOSED SAFETY VIOLATION"):
        ForwardPaperEngine()


def test_capital_insufficient_gate(tmp_path):
    engine = ForwardPaperEngine(state_dir=str(tmp_path / "test_paper"))
    # Verify default accounts
    assert "ACC_20K" in engine.accounts
    assert "ACC_50K" in engine.accounts
    assert "ACC_100K" in engine.accounts
    assert "ACC_250K" in engine.accounts
    assert "ACC_300K" in engine.accounts

    # Synthetic contracts df
    contracts = pd.DataFrame([
        {"FinInstrmId": "1001", "StrkPric": 25000.0, "OptnTp": "CE", "OpnPric": 100.0, "ClsPric": 50.0, "NewBrdLotQty": 75},
        {"FinInstrmId": "1002", "StrkPric": 25000.0, "OptnTp": "PE", "OpnPric": 100.0, "ClsPric": 50.0, "NewBrdLotQty": 75},
    ])

    res = engine.evaluate_session(
        current_date=date(2026, 9, 22),
        spot_open=25000.0,
        spot_close=25000.0,
        is_expiry=True,
        contracts_df=contracts,
        expiry_date_str="2026-09-22"
    )

    # 0DTE straddle requires 150k margin.
    # ACC_20K (60% = 12k < 150k): skipped
    # ACC_50K (60% = 30k < 150k): skipped
    # ACC_100K (60% = 60k < 150k): skipped
    # ACC_250K (60% = 150k == 150k): executed
    # ACC_300K (60% = 180k > 150k): executed
    assert engine.accounts["ACC_20K"].trades_skipped_capital == 1
    assert engine.accounts["ACC_20K"].trades_executed == 0

    assert engine.accounts["ACC_50K"].trades_skipped_capital == 1
    assert engine.accounts["ACC_50K"].trades_executed == 0

    assert engine.accounts["ACC_100K"].trades_skipped_capital == 1
    assert engine.accounts["ACC_100K"].trades_executed == 0

    assert engine.accounts["ACC_250K"].trades_executed == 1
    assert engine.accounts["ACC_300K"].trades_executed == 1


def test_per_leg_reconciliation(tmp_path):
    engine = ForwardPaperEngine(state_dir=str(tmp_path / "test_paper2"))
    contracts = pd.DataFrame([
        {"FinInstrmId": "2001", "StrkPric": 25000.0, "OptnTp": "CE", "OpnPric": 80.0, "ClsPric": 20.0, "NewBrdLotQty": 75},
        {"FinInstrmId": "2002", "StrkPric": 25000.0, "OptnTp": "PE", "OpnPric": 70.0, "ClsPric": 10.0, "NewBrdLotQty": 75},
    ])

    res = engine.evaluate_session(
        current_date=date(2026, 9, 22),
        spot_open=25000.0,
        spot_close=25000.0,
        is_expiry=True,
        contracts_df=contracts,
        expiry_date_str="2026-09-22"
    )

    trade = engine.trades[0]
    assert trade.status == "CLOSED"
    assert trade.reconciliation_verified is True
    leg_net_sum = sum(l.net_pnl for l in trade.legs)
    assert abs(trade.net_pnl - leg_net_sum) < 0.05
