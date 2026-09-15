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

from src.config import Config
from src.utils.logging import setup_logging
from src.data.downloader import DataDownloader
from src.features.feature_store import FeatureStore
from src.regime.detector import RuleBasedRegimeDetector, RegimeState
from src.strategies.base import get_all_baseline_strategies, Strategy
from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.cost_model import CostScenario, IndianCostModel
from src.backtesting.validator import StrategyValidator, ValidationSuite
from src.strategies.competition import StrategyCompetition
from src.utils.experiment_tracker import ExperimentTracker
from src.risk.risk_engine import RiskEngine

logger = setup_logging("research_agent")


class ResearchAgent:
    """
    Autonomous quant research agent.
    Coordinates: data → features → regime → strategies → backtest →
    validation → competition → paper trading → monitoring.
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
        self.validator = StrategyValidator(Config.INITIAL_CAPITAL)
        self.competition = StrategyCompetition()
        self.tracker = ExperimentTracker()
        self.risk_engine = RiskEngine(initial_capital=Config.INITIAL_CAPITAL)

        self.strategies = get_all_baseline_strategies()
        self.universe_data = {}
        self.index_data = None
        self.featured_data = {}

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

            # Phase 3: Regime detection
            self._phase_regime_detection()

            # Phase 4: Baseline backtesting
            self._phase_baseline_backtesting()

            # Phase 5: Validation
            self._phase_validation()

            # Phase 6: Competition ranking
            self._phase_competition()

            # Phase 7: Generate report
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
    # PHASE 3: Regime Detection
    # ─────────────────────────────────────────────────────────
    def _phase_regime_detection(self):
        """Detect current market regime."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 3: REGIME DETECTION")
        logger.info("=" * 50)

        if self.index_data is not None and not self.index_data.empty:
            regime = self.regime_detector.current_regime(self.index_data)
            logger.info(f"Current market regime: {regime.to_dict()}")
        else:
            logger.warning("No index data — using default regime")

    # ─────────────────────────────────────────────────────────
    # PHASE 4: Baseline Backtesting
    # ─────────────────────────────────────────────────────────
    def _phase_baseline_backtesting(self):
        """Run all baseline strategies through backtesting."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 4: BASELINE BACKTESTING")
        logger.info("=" * 50)

        if not self.featured_data:
            logger.warning("No featured data — skipping backtesting")
            return

        # Use a representative liquid stock for single-instrument backtests
        test_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
        available_symbols = [s for s in test_symbols if s in self.featured_data]

        if not available_symbols:
            # Fallback to first available
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
                    logger.info(f"  {symbol}: insufficient data ({len(df)} < {strategy.min_data_points})")
                    continue

                try:
                    # Get regime for context
                    regime = self.regime_detector.current_regime(df) if len(df) > 200 else None

                    # Generate signals
                    signals = strategy.generate_signals(df, regime)
                    if signals.empty or signals["signal"].abs().sum() == 0:
                        logger.info(f"  {symbol}: no signals generated")
                        continue

                    # Run backtest
                    engine = BacktestEngine(
                        initial_capital=Config.INITIAL_CAPITAL,
                        cost_scenario=CostScenario.BASE,
                    )
                    result = engine.run(signals, df, f"{strategy.name}_{symbol}")

                    if result.total_trades == 0:
                        logger.info(f"  {symbol}: no trades")
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

            # Log best result per strategy
            if strategy_results:
                best_symbol, best_result = max(strategy_results, key=lambda x: x[1].sharpe_ratio)
                self.tracker.log_experiment(
                    backtest_result=best_result,
                    hypothesis=strategy.hypothesis,
                    change_description=f"Baseline {strategy.name} on {best_symbol}",
                    decision="BASELINE",
                )
                # Store for validation phase
                strategy._best_result = best_result
                strategy._best_symbol = best_symbol
                strategy._best_data = self.featured_data[best_symbol]

    # ─────────────────────────────────────────────────────────
    # PHASE 5: Validation
    # ─────────────────────────────────────────────────────────
    def _phase_validation(self):
        """Validate promising strategies through rigorous testing."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 5: VALIDATION")
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
    # PHASE 6: Competition
    # ─────────────────────────────────────────────────────────
    def _phase_competition(self):
        """Rank all strategies and identify paper trading candidates."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 6: STRATEGY COMPETITION")
        logger.info("=" * 50)

        rankings = self.competition.get_rankings()
        if not rankings:
            logger.info("No strategies to rank")
            return

        logger.info("\nFinal Rankings:")
        logger.info("-" * 100)
        logger.info(f"{'Rank':>4} {'Strategy':<25} {'Score':>8} {'Sharpe':>8} {'CAGR%':>8} "
                     f"{'MaxDD%':>8} {'PF':>8} {'Robust':>8} {'Status':<20}")
        logger.info("-" * 100)

        for r in rankings:
            logger.info(
                f"{r.rank:>4} {r.strategy_name:<25} {r.composite_score:>8.3f} "
                f"{r.sharpe:>8.2f} {r.cagr:>8.1f} {r.max_drawdown:>8.1f} "
                f"{r.profit_factor:>8.2f} {r.robustness_score:>8.2f} {r.status:<20}"
            )

        # Identify paper candidates
        candidates = self.competition.get_paper_candidates()
        logger.info(f"\nPaper trading candidates: {len(candidates)}")
        for c in candidates:
            logger.info(f"  → {c.strategy_name} (score={c.composite_score:.3f})")

        # Save competition results
        comp_df = self.competition.to_dataframe()
        if not comp_df.empty:
            comp_df.to_csv(Config.REPORTS_DIR / "strategy_rankings.csv", index=False)

    # ─────────────────────────────────────────────────────────
    # PHASE 7: Report Generation
    # ─────────────────────────────────────────────────────────
    def _phase_report(self):
        """Generate final research report."""
        logger.info("\n" + "=" * 50)
        logger.info("PHASE 7: REPORT GENERATION")
        logger.info("=" * 50)

        rankings = self.competition.get_rankings()

        report_lines = [
            "# Indian Quant Research Agent — Final Report",
            f"\nGenerated: {datetime.now().isoformat()}",
            f"\nLIVE_TRADING_ENABLED: **{Config.LIVE_TRADING_ENABLED}**",
            "",
            "## Summary",
            f"- Strategies tested: {len(self.strategies)}",
            f"- Symbols analyzed: {len(self.universe_data)}",
            f"- Experiments logged: {self.tracker._experiment_counter}",
            f"- Paper candidates: {len(self.competition.get_paper_candidates())}",
            "",
            "## Strategy Rankings",
            "",
        ]

        if rankings:
            report_lines.append("| Rank | Strategy | Score | Sharpe | CAGR% | MaxDD% | PF | Robust | Status |")
            report_lines.append("|------|----------|-------|--------|-------|--------|-----|--------|--------|")
            for r in rankings:
                report_lines.append(
                    f"| {r.rank} | {r.strategy_name} | {r.composite_score:.3f} | "
                    f"{r.sharpe:.2f} | {r.cagr:.1f} | {r.max_drawdown:.1f} | "
                    f"{r.profit_factor:.2f} | {r.robustness_score:.2f} | {r.status} |"
                )
        else:
            report_lines.append("*No strategies completed full validation.*")

        report_lines.extend([
            "",
            "## Cost Model",
            "",
            "All backtests include realistic Indian market friction:",
            "- Brokerage (₹20/order or 0.03%)",
            "- STT (0.1% delivery, 0.025% intraday)",
            "- Exchange charges (0.00345%)",
            "- GST (18% on brokerage + exchange)",
            "- SEBI charges (₹10/crore)",
            "- Stamp duty (0.015%)",
            "- Slippage (0.05% base scenario)",
            "",
            "## Validation Methods",
            "",
            "- Walk-forward validation (5 folds)",
            "- Monte Carlo simulation (1000 reshuffles)",
            "- Cost stress testing (4 scenarios: optimistic → stress)",
            "- Parameter sensitivity testing",
            "",
            "## Known Limitations",
            "",
            "- Daily data only (no intraday data available without broker API)",
            "- No options data tested",
            "- No real-time execution tested yet",
            "- News/event pipeline not yet active (requires RSS/API setup)",
            "- Survivorship bias: current NIFTY50 constituents only",
            "",
            "## Next Steps",
            "",
            "1. Obtain broker API credentials for intraday data",
            "2. Activate news/event pipeline",
            "3. Deploy top strategies to paper trading",
            "4. Run walk-forward on expanding window",
            "5. Add ML-assisted confidence layer",
            "",
            "---",
            f"*Report generated by Autonomous Indian Quant Research Agent v0.1*",
        ])

        report_path = Config.REPORTS_DIR / "FINAL_REPORT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        logger.info(f"Report saved to {report_path}")

    # ─────────────────────────────────────────────────────────
    # UTILITY
    # ─────────────────────────────────────────────────────────
    def data_only(self):
        """Download data only."""
        self._phase_data_acquisition()

    def backtest_only(self):
        """Run backtests only (assumes data exists)."""
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
        self._phase_report()


def main():
    parser = argparse.ArgumentParser(description="Autonomous Indian Quant Research Agent")
    parser.add_argument("--autonomous", action="store_true", help="Full autonomous mode")
    parser.add_argument("--data-only", action="store_true", help="Download data only")
    parser.add_argument("--backtest-only", action="store_true", help="Run backtests only")
    parser.add_argument("--dashboard", action="store_true", help="Start dashboard")
    parser.add_argument("--dry-run", action="store_true", help="Verify setup")
    args = parser.parse_args()

    # SAFETY
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
        logger.info("Setup verified ✓")
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
