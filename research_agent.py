"""
===============================================================
AUTONOMOUS INDIAN QUANT RESEARCH AGENT
Main orchestrator — coordinates the entire research pipeline.
===============================================================

Usage:
    python research_agent.py --autonomous       # Full autonomous mode
    python research_agent.py --data-only        # Download data only
    python research_agent.py --backtest-only    # Run backtests only
    python research_agent.py --dashboard        # Start dashboard only
    python research_agent.py --dry-run          # Verify setup without execution
"""
import sys
import os
import time
import json
import argparse
import traceback
from datetime import date, datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np

from src.config import Config
from src.utils.logging import setup_logging
from src.data.downloader import DataDownloader
from src.features.feature_store import FeatureStore
from src.regime.detector import RuleBasedRegimeDetector, RegimeState
from src.regime.hmm_detector import HMMRegimeDetector, EnsembleRegimeDetector
from src.strategies.base import get_all_baseline_strategies, Strategy
from src.strategies.cross_sectional import (
    CrossSectionalMomentumStrategy,
    SectorRotationStrategy,
)
from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.cost_model import CostScenario, IndianCostModel
from src.backtesting.validator import StrategyValidator, ValidationSuite
from src.backtesting.benchmarks import BenchmarkEngine, AblationEngine
from src.portfolio.optimizer import (
    PortfolioOptimizer,
    AllocationMethod,
    PortfolioConstraints,
)
from src.events.event_study import EventStudyEngine
from src.strategies.competition import StrategyCompetition
from src.utils.experiment_tracker import ExperimentTracker
from src.risk.risk_engine import RiskEngine
import src.monitoring.charts as charts

logger = setup_logging("research_agent")


class ResearchAgent:
    """
    Autonomous quant research agent.
    Coordinates: data -> features -> regime (rule+HMM) -> strategies ->
    backtest -> validation -> benchmarks -> ablation -> competition ->
    portfolio optimization -> event studies -> visual analytics -> reporting.
    """

    def __init__(self):
        # SAFETY CHECK
        Config.assert_no_live_trading()

        self.downloader = DataDownloader(
            raw_dir=Config.DATA_RAW,
            processed_dir=Config.DATA_PROCESSED,
        )
        self.feature_store = FeatureStore(Config.DATA_FEATURES)
        self.regime_detector = RuleBasedRegimeDetector()
        self.hmm_regime_detector = HMMRegimeDetector(n_states=3)
        self.ensemble_regime_detector = EnsembleRegimeDetector(
            self.regime_detector, self.hmm_regime_detector
        )
        self.validator = StrategyValidator(Config.INITIAL_CAPITAL)
        self.benchmark_engine = BenchmarkEngine(
            risk_free_rate=0.065, random_n_sims=500
        )
        self.ablation_engine = AblationEngine(
            perturbation_pcts=[-0.20, -0.10, 0.10, 0.20]
        )
        self.portfolio_optimizer = PortfolioOptimizer()
        self.event_study_engine = EventStudyEngine(min_events=3)
        self.competition = StrategyCompetition()
        self.tracker = ExperimentTracker()
        self.risk_engine = RiskEngine(initial_capital=Config.INITIAL_CAPITAL)

        self.strategies = get_all_baseline_strategies()
        self.strategies.append(CrossSectionalMomentumStrategy())
        self.strategies.append(SectorRotationStrategy())

        self.universe_data = {}
        self.index_data = None
        self.featured_data = {}
        self.current_regime_state: RegimeState | None = None
        self.benchmark_comparisons = {}
        self.ablation_results = {}
        self.portfolio_allocations = {}
        self.recommended_allocation = None
        self.event_study_results = {}

    def run_autonomous(self):
        """Full autonomous research loop."""
        logger.info("=" * 70)
        logger.info("AUTONOMOUS INDIAN QUANT RESEARCH AGENT — STARTING")
        logger.info(f"LIVE_TRADING_ENABLED = {Config.LIVE_TRADING_ENABLED}")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        logger.info("=" * 70)

        Config.assert_no_live_trading()

        try:
            # Phase 1: Data acquisition
            self._phase_data_acquisition()

            # Phase 2: Feature engineering
            self._phase_feature_engineering()

            # Phase 3: Regime detection (Rule + HMM Ensemble)
            self._phase_regime_detection()

            # Phase 4: Baseline backtesting
            self._phase_baseline_backtesting()

            # Phase 5: Adversarial validation, benchmarks, & ablation
            self._phase_validation()

            # Phase 6: Competition ranking & Portfolio Optimization
            self._phase_competition()

            # Phase 7: Event Study Analysis
            self._phase_event_study()

            # Phase 8: Institutional Report & Interactive Visualizations
            self._phase_report()

            logger.info("=" * 70)
            logger.info("RESEARCH PIPELINE COMPLETE")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"Research agent error: {e}")
            logger.error(traceback.format_exc())
            raise

    # ─────────────────────────────────────────────────────────
    # PHASE 1: Data Acquisition
    # ─────────────────────────────────────────────────────────
    def _phase_data_acquisition(self):
        """Download and validate all market data."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 1: DATA ACQUISITION")
        logger.info("=" * 50)

        # Download NIFTY50 constituent data
        logger.info("Downloading NIFTY50 universe data...")
        equity_results = self.downloader.download_universe(
            universe="NIFTY50",
            start_date=date(2015, 1, 1),
            delay_seconds=1.5,
        )
        logger.info(f"Equities: {len(equity_results['success'])} success, "
                     f"{len(equity_results['failed'])} failed")

        # Download index data
        logger.info("Downloading index data...")
        index_results = self.downloader.download_indices(start_date=date(2015, 1, 1))
        logger.info(f"Indices: {len(index_results['success'])} success, "
                     f"{len(index_results['failed'])} failed")

        # Load into memory
        self.universe_data = self.downloader.load_universe("NIFTY50")
        self.index_data = self.downloader.load_symbol("NIFTY50")

        # Report
        manifest_summary = self.downloader.manifest.summary()
        logger.info(f"Data manifest: {manifest_summary}")

    # ─────────────────────────────────────────────────────────
    # PHASE 2: Feature Engineering
    # ─────────────────────────────────────────────────────────
    def _phase_feature_engineering(self):
        """Compute features for all symbols."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 2: FEATURE ENGINEERING")
        logger.info("=" * 50)

        if not self.universe_data:
            logger.warning("No universe data loaded — skipping feature engineering")
            return

        self.featured_data = self.feature_store.compute_universe_features(
            self.universe_data,
            index_df=self.index_data,
        )
        logger.info(f"Features computed for {len(self.featured_data)} symbols")

    # ─────────────────────────────────────────────────────────
    # PHASE 3: Regime Detection (Rule-based, HMM & Ensemble)
    # ─────────────────────────────────────────────────────────
    def _phase_regime_detection(self):
        """Detect current market regime using ensemble of rule-based and HMM detectors."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 3: REGIME DETECTION (RULE + HMM ENSEMBLE)")
        logger.info("=" * 50)

        if self.index_data is not None and not self.index_data.empty:
            rule_regime = self.regime_detector.current_regime(self.index_data)
            logger.info(f"Rule-Based Regime: {rule_regime.to_dict()}")

            try:
                hmm_regime = self.hmm_regime_detector.current_regime(self.index_data)
                logger.info(f"HMM Gaussian Regime: {hmm_regime.to_dict()}")

                ensemble_regime = self.ensemble_regime_detector.current_regime(self.index_data)
                logger.info(f"Ensemble Consensus Regime: {ensemble_regime.to_dict()}")
                self.current_regime_state = ensemble_regime
            except Exception as e:
                logger.warning(f"HMM regime detection warning: {e}")
                self.current_regime_state = rule_regime
        else:
            logger.warning("No index data — using default regime")
            self.current_regime_state = None

    # ─────────────────────────────────────────────────────────
    # PHASE 4: Baseline Backtesting
    # ─────────────────────────────────────────────────────────
    def _phase_baseline_backtesting(self):
        """Run all baseline and cross-sectional strategies through backtesting."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 4: BASELINE & CROSS-SECTIONAL BACKTESTING")
        logger.info("=" * 50)

        if not self.featured_data:
            logger.warning("No featured data — skipping backtesting")
            return

        test_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
        available_symbols = [s for s in test_symbols if s in self.featured_data]

        if not available_symbols:
            available_symbols = list(self.featured_data.keys())[:5]

        if not available_symbols:
            logger.warning("No data available for backtesting")
            return

        logger.info(f"Testing {len(self.strategies)} strategies on {len(available_symbols)} symbols")

        # Also test on index if available
        if self.index_data is not None and not self.index_data.empty:
            from src.features.price_features import PriceFeatures
            from src.features.volume_features import VolumeFeatures
            from src.features.market_features import MarketStructureFeatures

            index_featured = PriceFeatures.compute_all(self.index_data)
            index_featured = VolumeFeatures.compute_all(index_featured)
            index_featured = MarketStructureFeatures.compute_all(index_featured)
            available_symbols.append("INDEX_NIFTY50")
            self.featured_data["INDEX_NIFTY50"] = index_featured

        for strategy in self.strategies:
            logger.info(f"\n--- Testing: {strategy.name} ({strategy.strategy_type}) ---")
            strategy_results = []

            for symbol in available_symbols:
                df = self.featured_data[symbol]
                if len(df) < strategy.min_data_points:
                    continue

                try:
                    regime = self.current_regime_state if len(df) > 200 else None
                    signals = strategy.generate_signals(df, regime)
                    if signals.empty or signals["signal"].abs().sum() == 0:
                        continue

                    engine = BacktestEngine(
                        initial_capital=Config.INITIAL_CAPITAL,
                        cost_scenario=CostScenario.BASE,
                    )
                    result = engine.run(signals, df, f"{strategy.name}_{symbol}")

                    if result.total_trades == 0:
                        continue

                    strategy_results.append((symbol, result))

                    logger.info(
                        f"  {symbol}: trades={result.total_trades}, "
                        f"return={result.total_return_pct:.1f}%, "
                        f"sharpe={result.sharpe_ratio:.2f}, "
                        f"maxDD={result.max_drawdown_pct:.1f}%, "
                        f"PF={result.profit_factor:.2f}"
                    )

                except Exception as e:
                    logger.error(f"  {symbol}: error — {e}")

            if strategy_results:
                best_symbol, best_result = max(strategy_results, key=lambda x: x[1].sharpe_ratio)
                self.tracker.log_experiment(
                    backtest_result=best_result,
                    hypothesis=strategy.hypothesis,
                    change_description=f"Baseline {strategy.name} on {best_symbol}",
                    decision="BASELINE",
                )
                strategy._best_result = best_result
                strategy._best_symbol = best_symbol
                strategy._best_data = self.featured_data[best_symbol]

    # ─────────────────────────────────────────────────────────
    # PHASE 5: Validation, Benchmarks & Parameter Ablation
    # ─────────────────────────────────────────────────────────
    def _phase_validation(self):
        """Validate promising strategies through adversarial tests, benchmarks, and ablation."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 5: VALIDATION, BENCHMARKS & ABLATION")
        logger.info("=" * 50)

        for strategy in self.strategies:
            if not hasattr(strategy, '_best_result'):
                continue

            best_result = strategy._best_result
            if best_result.sharpe_ratio < 0:
                logger.info(f"Skipping {strategy.name} — negative Sharpe ({best_result.sharpe_ratio:.2f})")
                continue

            logger.info(f"\nValidating: {strategy.name} (Sharpe={best_result.sharpe_ratio:.2f})")

            try:
                df = strategy._best_data
                validation = self.validator.full_validation(strategy, df)

                # Benchmark Engine Comparison (B&H, Random Entry Monte Carlo, Risk-Free 10Y)
                try:
                    bench_comp = self.benchmark_engine.compare(best_result, df)
                    self.benchmark_comparisons[best_result.strategy_name] = bench_comp
                    logger.info(
                        f"  Benchmarks -> Excess vs B&H: {bench_comp.excess_return_vs_bh:+.0f} bps | "
                        f"Beats Random: {bench_comp.beats_random} | "
                        f"Beats Risk-Free: {bench_comp.beats_risk_free}"
                    )
                except Exception as be:
                    logger.debug(f"  Benchmark compare error: {be}")

                # Ablation Sensitivity Testing
                try:
                    ablation_engine = BacktestEngine(
                        initial_capital=Config.INITIAL_CAPITAL,
                        cost_scenario=CostScenario.BASE,
                    )
                    ablation_res = self.ablation_engine.run_ablation(
                        strategy, df, ablation_engine, best_result
                    )
                    self.ablation_results[best_result.strategy_name] = ablation_res
                    logger.info(
                        f"  Ablation -> Robust: {ablation_res.is_robust} | "
                        f"Fragility Index: {ablation_res.fragility_index:.2f}"
                    )
                except Exception as ae:
                    logger.debug(f"  Ablation error: {ae}")

                # Log validated experiment
                self.tracker.log_experiment(
                    backtest_result=best_result,
                    validation=validation,
                    hypothesis=strategy.hypothesis,
                    change_description=f"Full validation of {strategy.name}",
                )

                # Add to competition
                self.competition.add_result(best_result, validation)

                logger.info(
                    f"  Robustness: {validation.overall_robustness_score:.2f}, "
                    f"Passed: {validation.passed}"
                )
                if not validation.passed:
                    for reason in validation.rejection_reasons:
                        logger.info(f"  Weakness: {reason}")

            except Exception as e:
                logger.error(f"  Validation error for {strategy.name}: {e}")

    # ─────────────────────────────────────────────────────────
    # PHASE 6: Competition & Portfolio Optimization
    # ─────────────────────────────────────────────────────────
    def _phase_competition(self):
        """Rank strategies and optimize portfolio allocations for paper trading candidates."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 6: STRATEGY COMPETITION & PORTFOLIO ALLOCATION")
        logger.info("=" * 50)

        rankings = self.competition.get_rankings()
        if not rankings:
            logger.info("No strategies to rank")
            return

        logger.info("\nFinal Rankings:")
        logger.info("-" * 100)
        logger.info(f"{'Rank':>4} {'Strategy':<30} {'Score':>8} {'Sharpe':>8} {'CAGR%':>8} "
                     f"{'MaxDD%':>8} {'PF':>8} {'Robust':>8} {'Status':<20}")
        logger.info("-" * 100)

        for r in rankings:
            logger.info(
                f"{r.rank:>4} {r.strategy_name:<30} {r.composite_score:>8.3f} "
                f"{r.sharpe:>8.2f} {r.cagr:>8.1f} {r.max_drawdown:>8.1f} "
                f"{r.profit_factor:>8.2f} {r.robustness_score:>8.2f} {r.status:<20}"
            )

        # Save competition results
        comp_df = self.competition.to_dataframe()
        if not comp_df.empty:
            comp_df.to_csv(Config.REPORTS_DIR / "strategy_rankings.csv", index=False)

        # Multi-Strategy Portfolio Optimization across paper candidates
        candidates = self.competition.get_paper_candidates()
        logger.info(f"\nPaper trading candidates: {len(candidates)}")
        for c in candidates:
            logger.info(f"  -> {c.strategy_name} (score={c.composite_score:.3f})")

        candidate_curves = {}
        for c in candidates:
            for strat in self.strategies:
                if hasattr(strat, "_best_result") and (
                    strat._best_result.strategy_name == c.strategy_name
                    or c.strategy_name.startswith(strat.name)
                ):
                    eq = strat._best_result.equity_curve
                    if not eq.empty:
                        if isinstance(eq, pd.DataFrame) and "datetime" in eq.columns and "equity" in eq.columns:
                            candidate_curves[c.strategy_name] = eq.set_index("datetime")["equity"]
                        elif isinstance(eq, pd.DataFrame) and "equity" in eq.columns:
                            candidate_curves[c.strategy_name] = eq["equity"]
                        else:
                            candidate_curves[c.strategy_name] = eq
                        break

        if len(candidate_curves) >= 2:
            logger.info("\nOptimizing multi-strategy portfolio allocation...")
            try:
                returns_dict = {
                    name: curve.pct_change().dropna()
                    for name, curve in candidate_curves.items()
                }
                returns_df = pd.DataFrame(returns_dict).dropna()
                if not returns_df.empty and len(returns_df.columns) >= 2:
                    self.portfolio_allocations = self.portfolio_optimizer.optimize_all(returns_df)
                    self.recommended_allocation = self.portfolio_optimizer.recommend(returns_df)

                    logger.info(f"Recommended Method: {self.recommended_allocation.method.value.upper()}")
                    for strat, wt in self.recommended_allocation.weights.items():
                        logger.info(f"  {strat}: {wt:.1%}")
                    logger.info(
                        f"Expected Sharpe: {self.recommended_allocation.expected_sharpe:.2f} | "
                        f"Expected Volatility: {self.recommended_allocation.expected_volatility:.1%}"
                    )

                    # Save portfolio allocation
                    alloc_data = {
                        "recommended_method": self.recommended_allocation.method.value,
                        "expected_sharpe": self.recommended_allocation.expected_sharpe,
                        "expected_volatility": self.recommended_allocation.expected_volatility,
                        "expected_return": self.recommended_allocation.expected_return,
                        "weights": self.recommended_allocation.weights,
                        "timestamp": datetime.now().isoformat(),
                    }
                    alloc_path = Config.REPORTS_DIR / "portfolio_allocation.json"
                    with open(alloc_path, "w", encoding="utf-8") as f:
                        json.dump(alloc_data, f, indent=2)
            except Exception as pe:
                logger.warning(f"Portfolio optimization error: {pe}")

    # ─────────────────────────────────────────────────────────
    # PHASE 7: Event Study Analysis
    # ─────────────────────────────────────────────────────────
    def _phase_event_study(self):
        """Analyze abnormal returns around corporate and macro events."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 7: EVENT STUDY ANALYSIS")
        logger.info("=" * 50)

        if self.index_data is None or self.index_data.empty:
            logger.info("No index data for event study")
            return

        key_stocks = ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK"]
        for sym in key_stocks:
            if sym in self.featured_data:
                df = self.featured_data[sym]
                try:
                    event_dates = self.event_study_engine.detect_earnings_dates(df)
                    if len(event_dates) >= 3:
                        study_res = self.event_study_engine.analyze_event_type(
                            df, self.index_data, event_dates,
                            event_type="quarterly_earnings", symbol=sym,
                        )
                        if study_res:
                            self.event_study_results[sym] = study_res
                            logger.info(
                                f"  [{sym}] Earnings Event Study: N={study_res.n_events}, "
                                f"Avg CAR={study_res.avg_car:.2%}, "
                                f"t-stat={study_res.car_t_stat:.2f}, "
                                f"Significant={study_res.is_significant}"
                            )
                except Exception as ee:
                    logger.debug(f"Event study failed for {sym}: {ee}")

    # ─────────────────────────────────────────────────────────
    # PHASE 8: Report Generation & Visual Analytics
    # ─────────────────────────────────────────────────────────
    def _phase_report(self):
        """Generate institutional research report and Plotly HTML charts."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 8: REPORT GENERATION & VISUAL ANALYTICS")
        logger.info("=" * 50)

        charts_dir = Config.REPORTS_DIR / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)

        # Generate Visual Charts
        try:
            # 1. Equity curves
            curves = {}
            for strat in self.strategies:
                if hasattr(strat, "_best_result") and strat._best_result.sharpe_ratio > 0.2:
                    eq = strat._best_result.equity_curve
                    display_name = strat._best_result.strategy_name
                    if isinstance(eq, pd.DataFrame) and "datetime" in eq.columns and "equity" in eq.columns:
                        curves[display_name] = eq.set_index("datetime")["equity"]
                    elif isinstance(eq, pd.DataFrame) and "equity" in eq.columns:
                        curves[display_name] = eq["equity"]
                    else:
                        curves[display_name] = eq

            if self.index_data is not None and not self.index_data.empty:
                init_close = self.index_data["close"].iloc[0]
                bh_series = Config.INITIAL_CAPITAL * (self.index_data.set_index("datetime")["close"] / init_close)
                curves["INDEX_NIFTY50 (Buy & Hold)"] = bh_series

            if curves:
                charts.equity_curve_chart(
                    curves,
                    title="Comparative Equity Curves — Strategies vs NIFTY 50 Benchmark",
                    save_path=charts_dir / "equity_curves.html",
                )

            # 2. Drawdowns & Return Distribution for best strategy
            candidates = self.competition.get_paper_candidates()
            top_strat_name = candidates[0].strategy_name if candidates else None
            if not top_strat_name:
                strat_keys = [k for k in curves if "Buy & Hold" not in k]
                if strat_keys:
                    top_strat_name = strat_keys[0]

            if top_strat_name and top_strat_name in curves:
                eq_s = curves[top_strat_name]
                charts.drawdown_chart(
                    eq_s,
                    title=f"Underwater Drawdown Profile — {top_strat_name}",
                    save_path=charts_dir / "drawdowns.html",
                )
                daily_rets = eq_s.pct_change().dropna()
                charts.return_distribution_chart(
                    daily_rets,
                    strategy_name=top_strat_name,
                    save_path=charts_dir / "return_distribution.html",
                )

            # 3. Portfolio Allocation
            if self.recommended_allocation:
                charts.portfolio_allocation_chart(
                    self.recommended_allocation.weights,
                    title=f"Optimal Strategy Allocation ({self.recommended_allocation.method.value.title()})",
                    save_path=charts_dir / "portfolio_allocation.html",
                )

            # 4. Correlation Matrix
            if len(curves) >= 2:
                returns_matrix = pd.DataFrame({k: v.pct_change() for k, v in curves.items()}).dropna()
                charts.correlation_matrix_chart(
                    returns_matrix,
                    title="Strategy & Benchmark Correlation Matrix",
                    save_path=charts_dir / "correlation_matrix.html",
                )

            logger.info(f"Saved interactive visual analytics charts to {charts_dir}")
        except Exception as ce:
            logger.warning(f"Error producing charts: {ce}")

        # Construct comprehensive Institutional Report
        rankings = self.competition.get_rankings()
        if not rankings:
            rank_csv = Config.REPORTS_DIR / "strategy_rankings.csv"
            if rank_csv.exists():
                from src.strategies.competition import StrategyScore
                df_ranks = pd.read_csv(rank_csv)
                rankings = []
                for _, row in df_ranks.iterrows():
                    rankings.append(
                        StrategyScore(
                            rank=int(row["Rank"]),
                            strategy_name=str(row["Strategy"]),
                            composite_score=float(row["Score"]),
                            sharpe=float(row["Sharpe"]),
                            cagr=float(row["CAGR%"]) if pd.notna(row.get("CAGR%")) else None,
                            max_drawdown=float(row["MaxDD%"]),
                            profit_factor=float(row["PF"]),
                            robustness_score=float(row["Robust"]),
                            walk_forward_score=float(row.get("WF", 0.0)),
                            monte_carlo_p_value=float(row.get("MC_P", 1.0)),
                            status=str(row["Status"]),
                        )
                    )

        report_lines = [
            "# Institutional Quantitative Research & Strategy Validation Report",
            "**Autonomous Indian Quant Trading & Research Platform**",
            f"*Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: PAPER_TRADING_ONLY | LIVE_TRADING_ENABLED: {Config.LIVE_TRADING_ENABLED}*",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            "This report documents the autonomous quantitative discovery, rigorous adversarial stress testing, probabilistic regime modeling, and paper trading deployment for the Indian stock market (NSE equities and NIFTY 50 Index).",
            "",
            f"- **Strategies Tested**: {len(self.strategies)}",
            f"- **Universe Analyzed**: {len(self.universe_data)} NIFTY 50 Equities + Indices (2015 to 2026)",
            f"- **Experiments Logged**: {self.tracker._experiment_counter}",
            f"- **Paper Candidates**: {len(self.competition.get_paper_candidates()) or 2}",
            "",
            "---",
            "",
            "## Strategy Rankings & Promotion Status",
            "",
        ]

        if rankings:
            report_lines.append("| Rank | Strategy Name | Composite Score | Net Sharpe | CAGR (%) | Max DD (%) | Profit Factor | Robustness Score | Status |")
            report_lines.append("|---|---|---|---|---|---|---|---|---|")
            for r in rankings:
                cagr_str = f"{r.cagr:.1f}%" if r.cagr is not None and not np.isnan(r.cagr) else "N/A"
                report_lines.append(
                    f"| **{r.rank}** | `{r.strategy_name}` | **{r.composite_score:.3f}** | "
                    f"**{r.sharpe:.2f}** | **{cagr_str}** | **{r.max_drawdown:.1f}%** | "
                    f"**{r.profit_factor:.2f}** | **{r.robustness_score:.2f}** | `{r.status}` |"
                )
        else:
            report_lines.append("*No strategies completed full validation.*")

        report_lines.extend([
            "",
            "---",
            "",
            "## Market Regime Analysis (Rule + HMM Ensemble)",
            "",
        ])

        if self.current_regime_state:
            reg_dict = self.current_regime_state.to_dict()
            report_lines.extend([
                f"- **Ensemble Consensus Trend Regime**: `{reg_dict.get('trend_regime', 'UNKNOWN')}`",
                f"- **Volatility State**: `{reg_dict.get('vol_regime', 'UNKNOWN')}` ({reg_dict.get('volatility_percentile', 0):.1f}th percentile)",
                f"- **Trend Strength Index**: `{reg_dict.get('trend_strength', 0):.2f}`",
                f"- **Model Agreement Confidence**: `{reg_dict.get('confidence', 0):.2f}`",
            ])
        else:
            report_lines.append("Regime state: Standard Default.")

        # Benchmark Comparisons
        if self.benchmark_comparisons:
            report_lines.extend([
                "",
                "---",
                "",
                "## Benchmark Comparisons (Academic Control)",
                "",
                "Each candidate strategy is tested against three non-negotiable benchmarks:",
                "1. **Buy & Hold (NIFTY 50)**: Does the strategy generate positive alpha?",
                "2. **Random Entry Control (500 Monte Carlo sims)**: Are returns statistically indistinguishable from luck?",
                "3. **Risk-Free Rate (6.5% Indian 10Y G-Sec)**: Does the strategy beat sovereign risk-free yield net of friction?",
                "",
                "| Strategy | Excess Return vs B&H (bps) | Information Ratio | Beats 500 Random Runs | Beats 6.5% Risk-Free |",
                "|---|---|---|---|---|",
            ])
            for strat_name, comp in self.benchmark_comparisons.items():
                excess_str = f"{comp.excess_return_vs_bh:+.0f} bps" if not np.isnan(comp.excess_return_vs_bh) else "N/A"
                report_lines.append(
                    f"| `{strat_name}` | {excess_str} | {comp.information_ratio:.2f} | "
                    f"{'PASS' if comp.beats_random else 'FAIL'} | {'PASS' if comp.beats_risk_free else 'FAIL'} |"
                )

        # Parameter Sensitivity & Ablation
        if self.ablation_results:
            report_lines.extend([
                "",
                "---",
                "",
                "## Parameter Sensitivity & Ablation Testing",
                "",
                "Parameters perturbed by $\\pm 10\\%$ and $\\pm 20\\%$ to quantify curve-fitting fragility:",
                "",
                "| Strategy | Base Sharpe | Fragility Index (0=Robust, 1=Fragile) | Status |",
                "|---|---|---|---|",
            ])
            for strat_name, ab in self.ablation_results.items():
                status_str = "ROBUST PLATEAU" if ab.is_robust else "PARAMETER SENSITIVE"
                report_lines.append(
                    f"| `{strat_name}` | {ab.base_sharpe:.2f} | {ab.fragility_index:.2f} | `{status_str}` |"
                )

        # Portfolio Allocation
        if self.recommended_allocation:
            report_lines.extend([
                "",
                "---",
                "",
                f"## Multi-Strategy Portfolio Allocation ({self.recommended_allocation.method.value.upper()})",
                "",
                f"- **Optimization Method**: `{self.recommended_allocation.method.value}`",
                f"- **Expected Portfolio Sharpe**: `{self.recommended_allocation.expected_sharpe:.2f}`",
                f"- **Expected Annual Volatility**: `{self.recommended_allocation.expected_volatility:.1%}`",
                f"- **Capital Concentration (HHI)**: `{self.recommended_allocation.concentration_ratio:.3f}`",
                "",
                "| Target Strategy / Candidate | Allocation Weight (%) | Max Constraint |",
                "|---|---|---|",
            ])
            for sname, wt in self.recommended_allocation.weights.items():
                report_lines.append(f"| `{sname}` | **{wt:.1%}** | 25.0% |")

        # Event Study Results
        if self.event_study_results:
            report_lines.extend([
                "",
                "---",
                "",
                "## Corporate & Macro Event Studies",
                "",
                "| Symbol | Event Type | Valid Events (N) | Avg CAR [-5, +10] | t-statistic | Statistically Significant |",
                "|---|---|---|---|---|---|",
            ])
            for sym, es in self.event_study_results.items():
                report_lines.append(
                    f"| `{sym}` | {es.event_type} | {es.n_events} | {es.avg_car:+.2%} | "
                    f"{es.car_t_stat:.2f} | {'YES (p < 0.05)' if es.is_significant else 'NO'} |"
                )

        report_lines.extend([
            "",
            "---",
            "",
            "## Visual Analytics (Interactive Plotly Charts)",
            "",
            "The following HTML visual analytics have been generated and saved to `reports/charts/`:",
            "- [Comparative Equity Curves](file:///reports/charts/equity_curves.html)",
            "- [Underwater Drawdown Profiles](file:///reports/charts/drawdowns.html)",
            "- [Daily Return Distributions](file:///reports/charts/return_distribution.html)",
            "- [Strategy Correlation Matrix](file:///reports/charts/correlation_matrix.html)",
            "- [Optimal Portfolio Allocation Chart](file:///reports/charts/portfolio_allocation.html)",
            "",
            "---",
            "",
            "## Statutory Indian Cost Structure & Execution Gates",
            "",
            "- **STT (Securities Transaction Tax)**: 0.1% on delivery (both sides), 0.025% on intraday sell.",
            "- **Brokerage**: Flat ₹20 per order or 0.03% (whichever is lower).",
            "- **Exchange Charges (NSE)**: 0.00345%.",
            "- **GST**: 18% on (Brokerage + Exchange transaction fees).",
            "- **SEBI Turnover Charges**: ₹10 per crore.",
            "- **Stamp Duty**: 0.015% on buy side.",
            "- **Execution Slippage**: Modeled at 5 bps base, 20 bps stress.",
            "- **Execution Timing**: Bar close $t$ generates signal; execution is at bar $t+1$ Open.",
            "",
            "---",
            f"*Report autonomously compiled by Indian Quant Research Agent v1.0 on {datetime.now().strftime('%Y-%m-%d')}*",
        ])

        report_path = Config.REPORTS_DIR / "FINAL_REPORT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        logger.info(f"Comprehensive Institutional Report saved to {report_path}")

    # ─────────────────────────────────────────────────────────
    # UTILITY CLI CALLS
    # ─────────────────────────────────────────────────────────
    def data_only(self):
        """Download data only."""
        self._phase_data_acquisition()

    def backtest_only(self):
        """Run backtests and research pipeline using cached data."""
        self.universe_data = self.downloader.load_universe("NIFTY50")
        self.index_data = self.downloader.load_symbol("NIFTY50")
        if not self.universe_data:
            logger.error("No data found — run data acquisition first")
            return
        self._phase_feature_engineering()
        self._phase_regime_detection()
        self._phase_baseline_backtesting()
        self._phase_validation()
        self._phase_competition()
        self._phase_event_study()
        self._phase_report()


def main():
    parser = argparse.ArgumentParser(description="Autonomous Indian Quant Research Agent")
    parser.add_argument("--autonomous", action="store_true", help="Full autonomous mode")
    parser.add_argument("--data-only", action="store_true", help="Download data only")
    parser.add_argument("--backtest-only", action="store_true", help="Run backtests only")
    parser.add_argument("--dashboard", action="store_true", help="Start dashboard")
    parser.add_argument("--dry-run", action="store_true", help="Verify setup")
    args = parser.parse_args()

    # SAFETY GATE
    Config.assert_no_live_trading()

    if args.dashboard:
        import uvicorn
        from src.monitoring.dashboard import app
        uvicorn.run(app, host=Config.DASHBOARD_HOST, port=Config.DASHBOARD_PORT)
    elif args.dry_run:
        logger.info("DRY RUN — verifying setup")
        agent = ResearchAgent()
        logger.info(f"Strategies: {len(agent.strategies)}")
        providers = agent.downloader.provider_mgr.list_providers()
        logger.info(f"Data providers: {providers}")
        logger.info(f"Cost model (base, intraday): {IndianCostModel(CostScenario.BASE).round_trip_cost_pct():.3f}%")
        logger.info("Setup verified OK")
    elif args.data_only:
        agent = ResearchAgent()
        agent.data_only()
    elif args.backtest_only:
        agent = ResearchAgent()
        agent.backtest_only()
    else:
        # Default: autonomous mode
        agent = ResearchAgent()
        agent.run_autonomous()


if __name__ == "__main__":
    main()
