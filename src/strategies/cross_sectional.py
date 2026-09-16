"""
Cross-Sectional & Sector Rotation Strategies.

These strategies rank multiple stocks or sectors and trade
the top/bottom performers — a fundamentally different approach
from single-stock technical strategies.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from src.strategies.base import Strategy, SignalDirection
from src.regime.detector import RegimeState, RegimeType
from src.utils.logging import setup_logging

logger = setup_logging("strategies.cross_sectional")


@dataclass
class RankedUniverse:
    """Rankings for a universe of stocks at a point in time."""
    date: pd.Timestamp
    rankings: dict  # symbol -> rank (1 = best)
    scores: dict    # symbol -> raw score
    n_stocks: int
    long_basket: list[str] = field(default_factory=list)
    short_basket: list[str] = field(default_factory=list)


class CrossSectionalMomentumStrategy(Strategy):
    """
    Strategy: Cross-Sectional Momentum (Rank-Based)

    Hypothesis: Stocks with the highest relative momentum outperform
    those with the lowest relative momentum. This is one of the most
    well-documented anomalies in academic finance (Jegadeesh & Titman, 1993).

    Mechanism:
    - Rank all stocks in a universe by trailing N-month returns
    - Go long the top quintile, avoid/short the bottom quintile
    - Rebalance monthly
    - Skip the most recent month (short-term reversal avoidance)

    Indian market adaptation:
    - Long-only (shorting restrictions on most stocks)
    - Equal-weight within quintile
    - Skip micro-caps (illiquid)
    """

    name = "cross_sectional_momentum"
    hypothesis = (
        "Stocks with high relative momentum continue outperforming due to "
        "slow information diffusion, herding, and disposition effect."
    )
    strategy_type = "momentum"
    min_data_points = 252

    def __init__(
        self,
        formation_period: int = 252,  # ~12 months
        skip_period: int = 21,        # Skip most recent month
        holding_period: int = 21,     # Monthly rebalance
        top_pct: float = 0.2,         # Top 20%
        bottom_pct: float = 0.2,      # Bottom 20%
        long_only: bool = True,       # Indian market default
    ):
        self.formation_period = formation_period
        self.skip_period = skip_period
        self.holding_period = holding_period
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct
        self.long_only = long_only

    def rank_universe(
        self,
        universe_data: dict[str, pd.DataFrame],
        as_of_date: pd.Timestamp,
    ) -> Optional[RankedUniverse]:
        """
        Rank stocks by trailing momentum at a specific date.

        Args:
            universe_data: dict of symbol -> OHLCV DataFrame
            as_of_date: date to rank at

        Returns:
            RankedUniverse or None if insufficient data
        """
        scores = {}

        for symbol, df in universe_data.items():
            # Filter to data available up to as_of_date
            mask = df["datetime"] <= as_of_date
            available = df.loc[mask]

            if len(available) < self.formation_period + self.skip_period:
                continue

            # Momentum = return over formation period, skipping recent period
            end_idx = len(available) - self.skip_period - 1
            start_idx = end_idx - self.formation_period

            if start_idx < 0 or end_idx < 0:
                continue

            start_price = available.iloc[start_idx]["close"]
            end_price = available.iloc[end_idx]["close"]

            if start_price <= 0:
                continue

            momentum = (end_price / start_price) - 1.0
            scores[symbol] = momentum

        if len(scores) < 5:
            logger.warning(
                f"Only {len(scores)} stocks have enough data at {as_of_date}"
            )
            return None

        # Rank by momentum (highest = rank 1)
        sorted_symbols = sorted(scores.keys(), key=lambda s: scores[s], reverse=True)
        rankings = {sym: rank + 1 for rank, sym in enumerate(sorted_symbols)}

        n = len(sorted_symbols)
        n_top = max(1, int(n * self.top_pct))
        n_bottom = max(1, int(n * self.bottom_pct))

        long_basket = sorted_symbols[:n_top]
        short_basket = sorted_symbols[-n_bottom:] if not self.long_only else []

        return RankedUniverse(
            date=as_of_date,
            rankings=rankings,
            scores=scores,
            n_stocks=n,
            long_basket=long_basket,
            short_basket=short_basket,
        )

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate signals for a single stock based on its universe rank.
        Note: For cross-sectional strategies, call rank_universe first,
        then use this to generate entry/exit signals per symbol.
        """
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        mom_col = f"momentum_{self.formation_period}"

        if mom_col not in df.columns:
            df[mom_col] = df["close"].pct_change(self.formation_period)

        # Lagged momentum (skip recent month)
        df["lagged_momentum"] = df[mom_col].shift(self.skip_period)

        # Rebalance signal: only trade on rebalance dates
        df["bar_idx"] = range(len(df))
        df["rebalance"] = (df["bar_idx"] % self.holding_period) == 0

        # Signal: long if momentum > median (proxy for top quintile in single-stock mode)
        rolling_median = df["lagged_momentum"].rolling(
            self.formation_period, min_periods=60
        ).median()

        df["signal"] = 0
        long_mask = (df["lagged_momentum"] > rolling_median) & df["rebalance"]
        df.loc[long_mask, "signal"] = 1

        # Forward fill signal between rebalance dates
        df["signal"] = df["signal"].replace(0, np.nan)
        df.loc[df["rebalance"], "signal"] = df.loc[df["rebalance"], "signal"].fillna(0)
        df["signal"] = df["signal"].ffill().fillna(0).astype(int)

        # Confidence from momentum rank percentile
        df["confidence"] = df["lagged_momentum"].rolling(
            self.formation_period, min_periods=60
        ).rank(pct=True).fillna(0.5)

        # Reduce position in bear regimes
        if regime and regime.trend_regime in (
            RegimeType.STRONG_BEAR, RegimeType.WEAK_BEAR
        ):
            df["confidence"] *= 0.5

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {
            "formation_period": self.formation_period,
            "skip_period": self.skip_period,
            "holding_period": self.holding_period,
            "top_pct": self.top_pct,
            "bottom_pct": self.bottom_pct,
            "long_only": self.long_only,
        }


class SectorRotationStrategy(Strategy):
    """
    Strategy: Nifty Sector Rotation

    Hypothesis: Sector returns exhibit serial correlation. Sectors
    that have recently outperformed tend to continue outperforming
    over the intermediate term (1-6 months). At turning points,
    sector leadership shifts predictably (defensives lead in
    downturns, cyclicals lead in recoveries).

    Mechanism:
    - Track Nifty sector index returns (Bank Nifty, IT, Pharma, Auto, etc.)
    - Rank sectors by recent performance
    - Allocate to top N sectors
    - Regime-conditional: in bear markets, overweight defensives
    """

    name = "sector_rotation"
    hypothesis = (
        "Sector momentum reflects macroeconomic cycles and institutional "
        "rotation patterns. Leadership sectors persist until cycle turns."
    )
    strategy_type = "rotation"
    min_data_points = 126  # ~6 months

    # Nifty sector classification
    SECTOR_TICKERS = {
        "NIFTY_BANK": "^NSEBANK",
        "NIFTY_IT": "^CNXIT",
        "NIFTY_PHARMA": "^CNXPHARMA",
        "NIFTY_AUTO": "^CNXAUTO",
        "NIFTY_FMCG": "^CNXFMCG",
        "NIFTY_METAL": "^CNXMETAL",
        "NIFTY_REALTY": "^CNXREALTY",
        "NIFTY_ENERGY": "^CNXENERGY",
        "NIFTY_INFRA": "^CNXINFRA",
        "NIFTY_PSU_BANK": "^CNXPSUBANK",
    }

    # Defensive vs cyclical classification
    DEFENSIVE_SECTORS = {"NIFTY_PHARMA", "NIFTY_FMCG", "NIFTY_IT"}
    CYCLICAL_SECTORS = {"NIFTY_BANK", "NIFTY_AUTO", "NIFTY_METAL", "NIFTY_REALTY", "NIFTY_ENERGY"}

    def __init__(
        self,
        momentum_period: int = 63,     # ~3 months
        rebalance_period: int = 21,     # Monthly
        n_top_sectors: int = 3,
        defensive_tilt_bear: float = 0.3,  # Extra weight to defensives in bear
    ):
        self.momentum_period = momentum_period
        self.rebalance_period = rebalance_period
        self.n_top_sectors = n_top_sectors
        self.defensive_tilt_bear = defensive_tilt_bear

    def rank_sectors(
        self,
        sector_data: dict[str, pd.DataFrame],
        as_of_date: pd.Timestamp,
        regime: RegimeState | None = None,
    ) -> dict[str, float]:
        """
        Rank sectors by momentum, with optional regime tilt.

        Returns dict of sector -> allocation weight.
        """
        scores = {}

        for sector_name, df in sector_data.items():
            mask = df["datetime"] <= as_of_date
            available = df.loc[mask]

            if len(available) < self.momentum_period:
                continue

            # Sector momentum
            start_price = available.iloc[-self.momentum_period]["close"]
            end_price = available.iloc[-1]["close"]

            if start_price <= 0:
                continue

            momentum = (end_price / start_price) - 1.0

            # Risk-adjusted: penalize high-vol sectors
            daily_returns = available["close"].pct_change().tail(self.momentum_period)
            vol = daily_returns.std() * np.sqrt(252)
            risk_adj_mom = momentum / max(vol, 0.01)

            scores[sector_name] = risk_adj_mom

        if not scores:
            return {}

        # Sort by risk-adjusted momentum
        sorted_sectors = sorted(scores.keys(), key=lambda s: scores[s], reverse=True)

        # Regime tilt
        if regime and regime.trend_regime in (
            RegimeType.STRONG_BEAR, RegimeType.WEAK_BEAR
        ):
            # Boost defensive sectors
            for sector in self.DEFENSIVE_SECTORS:
                if sector in scores:
                    scores[sector] += self.defensive_tilt_bear
            sorted_sectors = sorted(
                scores.keys(), key=lambda s: scores[s], reverse=True
            )

        # Allocate equal weight to top N sectors
        top_sectors = sorted_sectors[: self.n_top_sectors]
        weight = 1.0 / max(len(top_sectors), 1)
        allocations = {sector: weight for sector in top_sectors}

        return allocations

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate signals for a single sector index.
        Uses relative momentum rank within the sector universe.
        """
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()

        # Compute sector momentum
        df["sector_mom"] = df["close"].pct_change(self.momentum_period)

        # Compute momentum rank percentile within rolling window
        df["mom_rank_pct"] = df["sector_mom"].rolling(
            252, min_periods=60
        ).rank(pct=True)

        # Rebalance flag
        df["bar_idx"] = range(len(df))
        df["rebalance"] = (df["bar_idx"] % self.rebalance_period) == 0

        # Signal: long if in top tercile of momentum
        df["signal"] = 0
        df.loc[(df["mom_rank_pct"] > 0.67) & df["rebalance"], "signal"] = 1

        # Forward fill between rebalance dates
        df["signal"] = df["signal"].replace(0, np.nan)
        df.loc[df["rebalance"], "signal"] = df.loc[df["rebalance"], "signal"].fillna(0)
        df["signal"] = df["signal"].ffill().fillna(0).astype(int)

        # Confidence from rank
        df["confidence"] = df["mom_rank_pct"].fillna(0.5)

        # Regime adjustment
        if regime and regime.trend_regime == RegimeType.STRONG_BEAR:
            df["confidence"] *= 0.3

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {
            "momentum_period": self.momentum_period,
            "rebalance_period": self.rebalance_period,
            "n_top_sectors": self.n_top_sectors,
            "defensive_tilt_bear": self.defensive_tilt_bear,
        }


class StatisticalArbitrageStrategy(Strategy):
    """
    Strategy: Pairs Trading / Statistical Arbitrage

    Hypothesis: Co-integrated stock pairs revert to their long-run
    equilibrium spread. Deviations represent temporary mispricings
    that correct as the economic relationship reasserts itself.

    Mechanism:
    - Identify co-integrated pairs (e.g., HDFC Bank vs ICICI Bank)
    - Compute z-score of the spread
    - Enter when z-score exceeds threshold (e.g., |z| > 2)
    - Exit when z-score reverts toward 0
    - Stop loss at extreme z-scores (|z| > 4)

    Indian market pairs:
    - Banking: HDFCBANK vs ICICIBANK, SBIN vs PNB
    - IT: TCS vs INFY, WIPRO vs HCLTECH
    - Oil: RELIANCE vs IOC
    """

    name = "statistical_arbitrage"
    hypothesis = (
        "Co-integrated stocks share common factors; deviations are temporary "
        "and revert, providing a mean-reversion edge."
    )
    strategy_type = "mean_reversion"
    min_data_points = 252

    COMMON_PAIRS = [
        ("HDFCBANK.NS", "ICICIBANK.NS"),
        ("TCS.NS", "INFY.NS"),
        ("SBIN.NS", "PNB.NS"),
        ("WIPRO.NS", "HCLTECH.NS"),
        ("RELIANCE.NS", "IOC.NS"),
    ]

    def __init__(
        self,
        lookback: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        stop_z: float = 4.0,
        hedge_ratio_window: int = 60,
    ):
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_z = stop_z
        self.hedge_ratio_window = hedge_ratio_window

    def compute_spread(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Compute the z-scored spread between two co-integrated assets.

        Uses rolling OLS hedge ratio to avoid lookahead bias.
        """
        # Align on datetime
        merged = pd.merge(
            df_a[["datetime", "close"]].rename(columns={"close": "price_a"}),
            df_b[["datetime", "close"]].rename(columns={"close": "price_b"}),
            on="datetime",
            how="inner",
        )

        if len(merged) < self.lookback:
            return pd.DataFrame()

        # Rolling hedge ratio (avoid lookahead)
        merged["log_a"] = np.log(merged["price_a"])
        merged["log_b"] = np.log(merged["price_b"])

        hedge_ratios = []
        for i in range(len(merged)):
            if i < self.hedge_ratio_window:
                hedge_ratios.append(np.nan)
                continue
            window = merged.iloc[i - self.hedge_ratio_window : i]
            # OLS: log_a = alpha + beta * log_b
            x = window["log_b"].values
            y = window["log_a"].values
            x_mean = x.mean()
            y_mean = y.mean()
            beta = np.sum((x - x_mean) * (y - y_mean)) / max(
                np.sum((x - x_mean) ** 2), 1e-10
            )
            hedge_ratios.append(beta)

        merged["hedge_ratio"] = hedge_ratios

        # Spread
        merged["spread"] = (
            merged["log_a"] - merged["hedge_ratio"] * merged["log_b"]
        )

        # Z-score of spread (rolling)
        spread_mean = merged["spread"].rolling(self.lookback).mean()
        spread_std = merged["spread"].rolling(self.lookback).std().replace(0, np.nan)
        merged["z_score"] = (merged["spread"] - spread_mean) / spread_std

        return merged

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate signals from pre-computed z-score spread.
        Expects df to have 'z_score' column (from compute_spread).
        """
        if "z_score" not in df.columns:
            logger.warning("z_score column missing — call compute_spread first")
            if not self.validate_inputs(df):
                return pd.DataFrame()
            # Fallback: compute momentum-based mean reversion on single stock
            df = df.copy()
            df["z_score"] = (
                (df["close"] - df["close"].rolling(self.lookback).mean())
                / df["close"].rolling(self.lookback).std().replace(0, np.nan)
            )

        df = df.copy()

        # Entry signals
        df["signal"] = 0
        # Long spread when z < -entry_z (spread too low, expect reversion up)
        df.loc[df["z_score"] < -self.entry_z, "signal"] = 1
        # Short spread when z > entry_z
        df.loc[df["z_score"] > self.entry_z, "signal"] = -1
        # Exit near zero
        df.loc[df["z_score"].abs() < self.exit_z, "signal"] = 0
        # Stop loss at extreme
        df.loc[df["z_score"].abs() > self.stop_z, "signal"] = 0

        # Confidence inversely proportional to z-score (more extreme = higher confidence)
        z_abs = df["z_score"].abs()
        df["confidence"] = ((z_abs - self.entry_z) / (self.stop_z - self.entry_z)).clip(0, 1)
        df.loc[df["signal"] == 0, "confidence"] = 0

        # Lower confidence in extreme volatility regimes
        if regime and regime.is_high_vol():
            df["confidence"] *= 0.6

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {
            "lookback": self.lookback,
            "entry_z": self.entry_z,
            "exit_z": self.exit_z,
            "stop_z": self.stop_z,
            "hedge_ratio_window": self.hedge_ratio_window,
        }


def get_cross_sectional_strategies() -> list[Strategy]:
    """Return all cross-sectional strategy instances."""
    return [
        CrossSectionalMomentumStrategy(
            formation_period=252, skip_period=21, holding_period=21
        ),
        SectorRotationStrategy(
            momentum_period=63, rebalance_period=21, n_top_sectors=3
        ),
        StatisticalArbitrageStrategy(
            lookback=60, entry_z=2.0, exit_z=0.5, stop_z=4.0
        ),
    ]
