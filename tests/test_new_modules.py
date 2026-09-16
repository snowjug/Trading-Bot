"""
Tests for new modules:
- HMM Regime Detector
- Cross-Sectional Strategies
- Portfolio Optimizer
- Benchmark Engine
- Ablation Testing
- Event Study Engine
- Chart Generation
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path


# =========================================================================
# Test Fixtures
# =========================================================================


def make_ohlcv(
    n: int = 500,
    symbol: str = "TEST.NS",
    trend: float = 0.0005,
    vol: float = 0.02,
    start_price: float = 100.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with controllable properties."""
    rng = np.random.RandomState(seed)
    returns = trend + vol * rng.randn(n)
    prices = start_price * np.exp(np.cumsum(returns))

    dates = pd.date_range("2020-01-01", periods=n, freq="B")

    df = pd.DataFrame({
        "datetime": dates,
        "open": prices * (1 + 0.001 * rng.randn(n)),
        "high": prices * (1 + abs(0.01 * rng.randn(n))),
        "low": prices * (1 - abs(0.01 * rng.randn(n))),
        "close": prices,
        "volume": (1e6 * (1 + 0.5 * rng.randn(n))).clip(1e4),
        "symbol": symbol,
    })

    return df


def make_multi_stock_universe(
    n_stocks: int = 10,
    n_days: int = 500,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """Generate a universe of stocks with different trends."""
    rng = np.random.RandomState(seed)
    universe = {}

    symbols = [f"STOCK{i:02d}.NS" for i in range(n_stocks)]
    for i, sym in enumerate(symbols):
        trend = rng.uniform(-0.0002, 0.001)
        vol = rng.uniform(0.015, 0.035)
        universe[sym] = make_ohlcv(
            n=n_days, symbol=sym, trend=trend, vol=vol,
            seed=seed + i,
        )

    return universe


# =========================================================================
# HMM Regime Detector Tests
# =========================================================================


class TestHMMRegimeDetector:
    """Tests for HMM-based regime detection."""

    def test_hmm_initialization(self):
        """HMM detector initializes with correct parameters."""
        from src.regime.hmm_detector import HMMRegimeDetector

        hmm = HMMRegimeDetector(n_states=3)
        assert hmm.n_states == 3
        assert hmm.model is None

    def test_hmm_detection_with_data(self):
        """HMM can detect regimes on synthetic data."""
        from src.regime.hmm_detector import HMMRegimeDetector

        df = make_ohlcv(n=400, seed=42)
        hmm = HMMRegimeDetector(n_states=3, lookback_window=200)

        result = hmm.detect(df)
        assert "hmm_regime" in result.columns
        assert "hmm_state" in result.columns
        assert "hmm_confidence" in result.columns

    def test_hmm_current_regime(self):
        """HMM returns valid current regime state."""
        from src.regime.hmm_detector import HMMRegimeDetector
        from src.regime.detector import RegimeType

        df = make_ohlcv(n=400, seed=42)
        hmm = HMMRegimeDetector(n_states=3, lookback_window=200)

        state = hmm.current_regime(df)
        assert state.trend_regime in RegimeType
        assert 0 <= state.confidence <= 1

    def test_hmm_insufficient_data(self):
        """HMM handles insufficient data gracefully."""
        from src.regime.hmm_detector import HMMRegimeDetector

        df = make_ohlcv(n=50, seed=42)
        hmm = HMMRegimeDetector(n_states=3, lookback_window=200)

        result = hmm.detect(df)
        assert "hmm_regime" in result.columns

    def test_ensemble_detector(self):
        """Ensemble combines rule-based and HMM correctly."""
        from src.regime.hmm_detector import HMMRegimeDetector, EnsembleRegimeDetector
        from src.regime.detector import RuleBasedRegimeDetector

        df = make_ohlcv(n=400, seed=42)
        rule = RuleBasedRegimeDetector()
        hmm = HMMRegimeDetector(n_states=3, lookback_window=200)

        ensemble = EnsembleRegimeDetector(rule, hmm)
        state = ensemble.current_regime(df)

        assert state.confidence > 0
        assert state.trend_regime is not None


# =========================================================================
# Cross-Sectional Strategy Tests
# =========================================================================


class TestCrossSectionalStrategies:
    """Tests for cross-sectional and sector rotation strategies."""

    def test_cross_sectional_momentum_signals(self):
        """Cross-sectional momentum generates valid signals."""
        from src.strategies.cross_sectional import CrossSectionalMomentumStrategy

        df = make_ohlcv(n=500, seed=42)
        strat = CrossSectionalMomentumStrategy(
            formation_period=252, skip_period=21, holding_period=21,
        )

        signals = strat.generate_signals(df)
        assert not signals.empty
        assert "signal" in signals.columns
        assert "confidence" in signals.columns
        assert set(signals["signal"].unique()).issubset({-1, 0, 1})

    def test_cross_sectional_ranking(self):
        """Universe ranking works correctly."""
        from src.strategies.cross_sectional import CrossSectionalMomentumStrategy

        universe = make_multi_stock_universe(n_stocks=10, n_days=500)
        strat = CrossSectionalMomentumStrategy(
            formation_period=252, skip_period=21
        )

        as_of = pd.Timestamp("2021-06-01")
        ranking = strat.rank_universe(universe, as_of)

        if ranking is not None:
            assert ranking.n_stocks > 0
            assert len(ranking.long_basket) > 0
            assert len(ranking.rankings) == ranking.n_stocks

    def test_sector_rotation_signals(self):
        """Sector rotation generates valid signals."""
        from src.strategies.cross_sectional import SectorRotationStrategy

        df = make_ohlcv(n=300, seed=42)
        strat = SectorRotationStrategy(momentum_period=63)

        signals = strat.generate_signals(df)
        assert not signals.empty
        assert set(signals["signal"].unique()).issubset({-1, 0, 1})

    def test_stat_arb_spread_computation(self):
        """Statistical arbitrage spread computation works."""
        from src.strategies.cross_sectional import StatisticalArbitrageStrategy

        # Create co-integrated pair (B = A + noise)
        rng = np.random.RandomState(42)
        n = 300
        dates = pd.date_range("2020-01-01", periods=n, freq="B")
        base = 100 * np.exp(np.cumsum(0.001 + 0.02 * rng.randn(n)))

        df_a = pd.DataFrame({
            "datetime": dates, "close": base,
            "open": base, "high": base * 1.01, "low": base * 0.99,
            "volume": 1e6 + 1e5 * rng.randn(n),
        })
        df_b = pd.DataFrame({
            "datetime": dates,
            "close": base * 0.8 + 5 * rng.randn(n),
            "open": base, "high": base * 1.01, "low": base * 0.99,
            "volume": 1e6 + 1e5 * rng.randn(n),
        })

        strat = StatisticalArbitrageStrategy(lookback=60)
        spread = strat.compute_spread(df_a, df_b)

        assert not spread.empty
        assert "z_score" in spread.columns


# =========================================================================
# Portfolio Optimizer Tests
# =========================================================================


class TestPortfolioOptimizer:
    """Tests for portfolio optimization."""

    def _make_strategy_returns(self, n_strategies: int = 5, n_days: int = 500):
        """Create synthetic strategy returns."""
        rng = np.random.RandomState(42)
        returns = pd.DataFrame()
        for i in range(n_strategies):
            returns[f"strategy_{i}"] = rng.normal(0.0003, 0.015, n_days)
        returns.index = pd.date_range("2020-01-01", periods=n_days, freq="B")
        return returns

    def test_equal_weight(self):
        """Equal weight allocation sums to 1."""
        from src.portfolio.optimizer import PortfolioOptimizer

        opt = PortfolioOptimizer()
        alloc = opt.equal_weight(["a", "b", "c", "d"])

        assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6
        assert len(alloc.weights) == 4

    def test_inverse_volatility(self):
        """Inverse vol allocates more to low-vol strategies."""
        from src.portfolio.optimizer import PortfolioOptimizer

        returns = self._make_strategy_returns(3)
        # Make strategy 0 much lower vol
        returns["strategy_0"] *= 0.3

        opt = PortfolioOptimizer()
        alloc = opt.inverse_volatility(returns)

        assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6
        # Strategy 0 should have highest weight
        assert alloc.weights["strategy_0"] > alloc.weights["strategy_1"]

    def test_risk_parity(self):
        """Risk parity optimization produces valid weights."""
        from src.portfolio.optimizer import PortfolioOptimizer

        returns = self._make_strategy_returns(4)
        opt = PortfolioOptimizer()
        alloc = opt.risk_parity(returns)

        assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6
        assert all(w >= 0 for w in alloc.weights.values())

    def test_max_sharpe(self):
        """Max Sharpe optimization runs successfully."""
        from src.portfolio.optimizer import PortfolioOptimizer

        returns = self._make_strategy_returns(4)
        opt = PortfolioOptimizer()
        alloc = opt.max_sharpe(returns)

        assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6

    def test_min_variance(self):
        """Min variance optimization runs successfully."""
        from src.portfolio.optimizer import PortfolioOptimizer

        returns = self._make_strategy_returns(4)
        opt = PortfolioOptimizer()
        alloc = opt.min_variance(returns)

        assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6

    def test_fractional_kelly(self):
        """Fractional Kelly produces reasonable weights."""
        from src.portfolio.optimizer import PortfolioOptimizer

        returns = self._make_strategy_returns(3)
        opt = PortfolioOptimizer()
        alloc = opt.fractional_kelly(returns, fraction=0.25)

        assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6

    def test_optimize_all(self):
        """All optimization methods run without error."""
        from src.portfolio.optimizer import PortfolioOptimizer, AllocationMethod

        returns = self._make_strategy_returns(4)
        opt = PortfolioOptimizer()
        results = opt.optimize_all(returns)

        assert AllocationMethod.EQUAL_WEIGHT in results
        assert len(results) >= 4  # At least 4 methods should succeed

    def test_recommend(self):
        """Recommendation picks a valid allocation."""
        from src.portfolio.optimizer import PortfolioOptimizer

        returns = self._make_strategy_returns(4)
        opt = PortfolioOptimizer()
        alloc = opt.recommend(returns)

        assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6
        assert alloc.max_weight <= 0.26  # Within constraint tolerance


# =========================================================================
# Benchmark Engine Tests
# =========================================================================


class TestBenchmarkEngine:
    """Tests for benchmark comparisons."""

    def test_buy_and_hold(self):
        """Buy-and-hold returns correct metrics."""
        from src.backtesting.benchmarks import BuyAndHoldBenchmark

        df = make_ohlcv(n=500, trend=0.001, seed=42)
        result = BuyAndHoldBenchmark.compute(df)

        assert "cagr" in result
        assert "sharpe" in result
        assert "max_dd" in result
        assert result["cagr"] > 0  # Positive trend
        assert result["max_dd"] > 0  # Should have some drawdown

    def test_random_entry_benchmark(self):
        """Random entry benchmark produces valid distribution."""
        from src.backtesting.benchmarks import RandomEntryBenchmark

        df = make_ohlcv(n=500, seed=42)
        result = RandomEntryBenchmark.compute(
            df, n_simulations=100, seed=42
        )

        assert result["n_simulations"] == 100
        assert result["p5_return"] < result["p95_return"]
        assert result["mean_return"] is not None

    def test_risk_free_benchmark(self):
        """Risk-free benchmark computes correctly."""
        from src.backtesting.benchmarks import RiskFreeBenchmark

        result = RiskFreeBenchmark.compute(252, risk_free_rate=0.065)

        assert abs(result["cagr"] - 0.065) < 1e-6
        assert result["total_return"] > 0
        assert result["max_dd"] == 0


# =========================================================================
# Ablation Engine Tests
# =========================================================================


class TestAblationEngine:
    """Tests for parameter sensitivity analysis."""

    def test_ablation_basic(self):
        """Ablation runs on a simple strategy."""
        from src.backtesting.benchmarks import AblationEngine
        from src.strategies.base import MomentumStrategy
        from src.backtesting.engine import BacktestEngine, BacktestResult

        df = make_ohlcv(n=400, seed=42)
        strategy = MomentumStrategy(lookback=20)

        signals = strategy.generate_signals(df)
        engine = BacktestEngine()
        base_result = engine.run(signals, df, strategy_name="momentum")

        ablation = AblationEngine(
            perturbation_pcts=[-0.20, 0.20],
            min_sharpe_retention=0.5,
        )

        result = ablation.run_ablation(strategy, df, engine, base_result)

        assert result.strategy_name == "momentum"
        assert isinstance(result.is_robust, bool)
        assert 0 <= result.fragility_index <= 1

    def test_ablation_report(self):
        """Ablation report generates text."""
        from src.backtesting.benchmarks import AblationEngine, AblationResult

        result = AblationResult(
            strategy_name="test",
            base_params={"lookback": 20},
            base_sharpe=1.5,
            base_cagr=0.15,
            perturbations=[],
            sensitivity_scores={},
            is_robust=True,
            fragility_index=0.0,
        )

        engine = AblationEngine()
        report = engine.ablation_report(result)
        assert "ABLATION" in report
        assert "test" in report


# =========================================================================
# Event Study Tests
# =========================================================================


class TestEventStudy:
    """Tests for event study analysis."""

    def test_detect_earnings_dates(self):
        """Earnings date heuristic detects high-volume days."""
        from src.events.event_study import EventStudyEngine

        df = make_ohlcv(n=500, seed=42)
        # Inject artificial earnings events (high volume + big return)
        for idx in [100, 165, 230, 295, 360, 425]:
            df.loc[idx, "volume"] *= 5
            df.loc[idx, "close"] *= 1.05

        engine = EventStudyEngine()
        dates = engine.detect_earnings_dates(df)

        assert len(dates) > 0

    def test_event_study_analysis(self):
        """Event study produces valid results."""
        from src.events.event_study import EventStudyEngine

        df = make_ohlcv(n=500, seed=42)
        market = make_ohlcv(n=500, seed=99)

        # Create event dates
        event_dates = [pd.Timestamp("2020-12-01"), pd.Timestamp("2021-03-01"),
                       pd.Timestamp("2021-06-01"), pd.Timestamp("2021-09-01"),
                       pd.Timestamp("2021-12-01")]

        engine = EventStudyEngine(min_events=3)
        result = engine.analyze_event_type(
            df, market, event_dates, event_type="quarterly_earnings",
        )

        if result is not None:
            assert result.n_events >= 3
            assert result.car_p_value >= 0
            assert isinstance(result.is_significant, bool)

    def test_event_study_report(self):
        """Event study generates report text."""
        from src.events.event_study import EventStudyEngine, EventStudyResult

        result = EventStudyResult(
            event_type="test_event",
            n_events=10,
            avg_car=0.02,
            car_t_stat=2.5,
            car_p_value=0.03,
            avg_pre_drift=0.005,
            avg_post_drift=0.015,
            post_event_reversal=-0.3,
            pct_positive_car=0.7,
            avg_abnormal_volume=2.5,
            event_windows=[],
            is_significant=True,
            economic_significance=True,
        )

        engine = EventStudyEngine()
        report = engine.generate_report(result)
        assert "ACTIONABLE" in report
        assert "test_event" in report.lower()


# =========================================================================
# Chart Generation Tests
# =========================================================================


class TestCharts:
    """Tests for chart generation."""

    def test_equity_curve_chart(self):
        """Equity curve chart creates a figure."""
        from src.monitoring.charts import equity_curve_chart

        dates = pd.date_range("2020-01-01", periods=252, freq="B")
        curves = {
            "Strategy A": pd.Series(
                1e6 * np.exp(np.cumsum(np.random.randn(252) * 0.01)),
                index=dates,
            ),
            "Buy & Hold": pd.Series(
                1e6 * np.exp(np.cumsum(np.random.randn(252) * 0.008)),
                index=dates,
            ),
        }

        fig = equity_curve_chart(curves)
        assert fig is not None
        assert len(fig.data) == 2

    def test_portfolio_allocation_chart(self):
        """Portfolio allocation chart creates a figure."""
        from src.monitoring.charts import portfolio_allocation_chart

        allocs = {"Strategy A": 0.3, "Strategy B": 0.25, "Strategy C": 0.45}
        fig = portfolio_allocation_chart(allocs)
        assert fig is not None

    def test_return_distribution_chart(self):
        """Return distribution chart creates a figure."""
        from src.monitoring.charts import return_distribution_chart

        returns = pd.Series(np.random.randn(252) * 0.01)
        fig = return_distribution_chart(returns, strategy_name="Test")
        assert fig is not None

    def test_correlation_matrix_chart(self):
        """Correlation matrix chart creates a figure."""
        from src.monitoring.charts import correlation_matrix_chart

        returns = pd.DataFrame({
            "A": np.random.randn(100),
            "B": np.random.randn(100),
            "C": np.random.randn(100),
        })
        fig = correlation_matrix_chart(returns)
        assert fig is not None
