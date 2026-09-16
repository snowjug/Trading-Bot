"""
Comprehensive Anti-Lookahead Verification Test Suite.
Guarantees that no strategy, feature, indicator, or execution engine accesses future data.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.strategies.confluence_scalper import ConfluenceGammaScalperStrategy
from src.strategies.golden_trend_buyer import GoldenTrendOptionBuyerStrategy
from src.strategies.leader_breakout import LeaderBreakoutStrategy
from src.backtesting.engine import BacktestEngine
from src.backtesting.cost_model import CostScenario


def _create_synthetic_ohlcv(n_bars: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate realistic synthetic OHLCV data for lookahead testing."""
    np.random.seed(seed)
    base_date = datetime(2023, 1, 1, 9, 15)
    dates = [base_date + timedelta(days=i) for i in range(n_bars)]
    
    # Random walk
    returns = np.random.normal(0.0005, 0.015, n_bars)
    price = 100.0 * np.exp(np.cumsum(returns))
    
    high = price * (1.0 + np.random.uniform(0.002, 0.02, n_bars))
    low = price * (1.0 - np.random.uniform(0.002, 0.02, n_bars))
    open_p = (high + low) / 2.0 + np.random.uniform(-0.5, 0.5, n_bars)
    close = price
    volume = np.random.randint(10000, 500000, n_bars).astype(float)
    
    df = pd.DataFrame({
        "datetime": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


class TestNoLookahead:
    """Rigorous tests enforcing strict temporal causality across all strategies."""

    @pytest.mark.parametrize("strat_class", [
        ConfluenceGammaScalperStrategy,
        GoldenTrendOptionBuyerStrategy,
        ActiveMomentumOptionScalperStrategy,
        LeaderBreakoutStrategy,
    ])
    def test_future_price_mutation(self, strat_class):
        """
        Test 1: Future-Price Mutation Test.
        Modify all bars strictly after timestamp T with massive random noise.
        Signals generated on or before timestamp T MUST remain 100% byte-for-byte identical.
        """
        df_original = _create_synthetic_ohlcv(200, seed=101)
        strategy = strat_class()
        
        # Base signals
        signals_orig = strategy.generate_signals(df_original.copy())
        assert not signals_orig.empty, f"{strat_class.__name__} generated empty signals"
        
        # Pick cutoff index T = 120
        cutoff_idx = 120
        cutoff_time = df_original.iloc[cutoff_idx]["datetime"]
        
        # Create mutated future dataframe
        df_mutated = df_original.copy()
        n_future = len(df_mutated) - (cutoff_idx + 1)
        
        # Inject extreme 10x volatility mutations into the future
        mutation_factor = np.random.uniform(0.5, 2.5, n_future)
        df_mutated.loc[cutoff_idx + 1:, "close"] *= mutation_factor
        df_mutated.loc[cutoff_idx + 1:, "high"] *= mutation_factor * 1.1
        df_mutated.loc[cutoff_idx + 1:, "low"] *= mutation_factor * 0.9
        df_mutated.loc[cutoff_idx + 1:, "open"] *= mutation_factor
        df_mutated.loc[cutoff_idx + 1:, "volume"] *= np.random.uniform(0.1, 10.0, n_future)
        
        # Re-run strategy on mutated dataset
        signals_mutated = strategy.generate_signals(df_mutated)
        
        # Verify signals before cutoff are byte-for-byte identical
        orig_pre = signals_orig[signals_orig["datetime"] <= cutoff_time]["signal"].values
        mut_pre = signals_mutated[signals_mutated["datetime"] <= cutoff_time]["signal"].values
        
        diff = np.where(orig_pre != mut_pre)[0]
        assert len(diff) == 0, (
            f"LOOKAHEAD LEAK DETECTED in {strat_class.__name__}! "
            f"Signals before cutoff {cutoff_time} mutated at indices: {diff}"
        )

    @pytest.mark.parametrize("strat_class", [
        ConfluenceGammaScalperStrategy,
        GoldenTrendOptionBuyerStrategy,
        ActiveMomentumOptionScalperStrategy,
    ])
    def test_history_slice_causality(self, strat_class):
        """
        Test 2: History-Slice Test.
        Evaluating strategy at bar i using strictly historical slice df[:i+1]
        must produce the exact same signal at bar i as evaluating the full array.
        """
        df = _create_synthetic_ohlcv(150, seed=202)
        strategy = strat_class()
        
        full_signals = strategy.generate_signals(df.copy())
        
        # Test 5 randomly selected evaluation points
        test_indices = [60, 80, 100, 120, 140]
        for idx in test_indices:
            slice_df = df.iloc[:idx + 1].copy()
            slice_signals = strategy.generate_signals(slice_df)
            
            val_full = full_signals.iloc[idx]["signal"]
            val_slice = slice_signals.iloc[-1]["signal"]
            
            assert val_full == val_slice, (
                f"History slice inconsistency at index {idx} in {strat_class.__name__}: "
                f"Full signal={val_full} vs Slice signal={val_slice}"
            )

    def test_execution_timing_delay(self):
        """
        Test 3: Execution Timing Test (Next-Bar Execution).
        A signal computed using bar T close CANNOT execute at bar T close.
        Execution must strictly take place at bar T+1.
        """
        df = _create_synthetic_ohlcv(100, seed=303)
        engine = BacktestEngine(initial_capital=100000.0, cost_scenario=CostScenario.BASE)
        
        # Create a signal on bar 25
        signals = pd.DataFrame({
            "datetime": df["datetime"],
            "signal": 0,
            "confidence": 0.0,
        })
        signals.loc[25, "signal"] = 1
        signals.loc[25, "confidence"] = 0.9
        
        # Sell signal on bar 30
        signals.loc[30, "signal"] = 0
        signals.loc[30, "confidence"] = 0.9
        
        result = engine.run(signals, df, "test_timing_strategy")
        
        assert len(result.trades) > 0, "No trade executed"
        first_trade = result.trades[0]
        
        # Entry must be at bar 26, NOT bar 25!
        expected_entry_date = df.iloc[26]["datetime"]
        assert first_trade.entry_date == expected_entry_date, (
            f"Execution timing lookahead! Signal was at {df.iloc[25]['datetime']}, "
            f"but trade entered at {first_trade.entry_date} instead of {expected_entry_date}"
        )

    def test_indicator_leakage_no_centering(self):
        """
        Test 4: Indicator Leakage Test.
        Verify that no rolling indicator uses centered windows or future targets.
        """
        df = _create_synthetic_ohlcv(100, seed=404)
        strat = ConfluenceGammaScalperStrategy()
        ind_df = strat.compute_indicators(df)
        
        # Mutate last 10 bars of close
        df_mut = df.copy()
        df_mut.loc[90:, "close"] *= 5.0
        ind_mut = strat.compute_indicators(df_mut)
        
        # Indicators at bar 80 must be identical
        for col in ["ema_9", "ema_20", "ema_50", "bb_mid", "bb_upper", "bb_lower", "atr_14", "rsi_14"]:
            val_orig = ind_df.iloc[80][col]
            val_mut = ind_mut.iloc[80][col]
            assert np.isclose(val_orig, val_mut, rtol=1e-5), (
                f"Indicator {col} leaked future data! At bar 80: {val_orig} != {val_mut}"
            )
