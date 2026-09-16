"""
Event Study Engine.

Analyzes price behavior around specific events (earnings, policy
announcements, index rebalances, RBI decisions) to identify
systematic patterns and tradeable windows.

Event types:
1. Earnings announcements (quarterly results)
2. RBI monetary policy decisions
3. Index rebalancing (Nifty additions/removals)
4. Budget announcements
5. FII/DII flow extremes
6. Sector-specific events (drug approvals, spectrum auctions)
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from scipy import stats
from src.utils.logging import setup_logging

logger = setup_logging("events.study")


@dataclass
class EventWindow:
    """Price behavior around a single event."""
    event_date: pd.Timestamp
    event_type: str
    event_description: str
    symbol: str
    pre_event_returns: list[float]    # Returns in [-N, -1] window
    post_event_returns: list[float]   # Returns in [0, +N] window
    car: float                         # Cumulative Abnormal Return
    pre_drift: float                   # Pre-event drift
    post_drift: float                  # Post-event drift
    abnormal_volume: float             # Volume vs average at event
    metadata: dict = field(default_factory=dict)


@dataclass
class EventStudyResult:
    """Aggregated event study analysis."""
    event_type: str
    n_events: int
    avg_car: float                    # Average CAR across all events
    car_t_stat: float                 # T-statistic for avg CAR
    car_p_value: float                # P-value (two-sided)
    avg_pre_drift: float              # Average pre-event drift
    avg_post_drift: float             # Average post-event drift
    post_event_reversal: float        # Does the drift reverse?
    pct_positive_car: float           # % of events with positive CAR
    avg_abnormal_volume: float        # Average abnormal volume at event
    event_windows: list[EventWindow]
    # Statistical significance
    is_significant: bool              # p < 0.05
    economic_significance: bool       # |avg_car| > 1% (meaningful)


class EventStudyEngine:
    """
    Event study methodology following standard academic approach:

    1. Estimation window: [-260, -11] (one year ending 10 days before event)
    2. Event window: [-10, +10] (20 trading days around event)
    3. Normal return model: Market model (R_i = alpha + beta * R_m + epsilon)
    4. Abnormal return: AR_i = R_i - E[R_i]
    5. Cumulative abnormal return: CAR = sum(AR_i) over event window
    6. Statistical test: Cross-sectional t-test on CARs
    """

    def __init__(
        self,
        estimation_window: int = 250,    # ~1 year
        estimation_gap: int = 10,         # Gap between estimation and event
        pre_event_window: int = 10,       # Days before event
        post_event_window: int = 10,      # Days after event
        min_events: int = 5,              # Minimum for statistical validity
    ):
        self.estimation_window = estimation_window
        self.estimation_gap = estimation_gap
        self.pre_event_window = pre_event_window
        self.post_event_window = post_event_window
        self.min_events = min_events

    def _estimate_normal_return(
        self,
        stock_returns: pd.Series,
        market_returns: pd.Series,
    ) -> tuple[float, float]:
        """
        Estimate market model parameters using OLS.

        R_stock = alpha + beta * R_market

        Returns (alpha, beta)
        """
        # Align series
        aligned = pd.DataFrame({
            "stock": stock_returns,
            "market": market_returns,
        }).dropna()

        if len(aligned) < 30:
            return 0.0, 1.0  # Default: no alpha, beta=1

        x = aligned["market"].values
        y = aligned["stock"].values

        x_mean = x.mean()
        y_mean = y.mean()

        beta = np.sum((x - x_mean) * (y - y_mean)) / max(
            np.sum((x - x_mean) ** 2), 1e-10
        )
        alpha = y_mean - beta * x_mean

        return float(alpha), float(beta)

    def analyze_single_event(
        self,
        df: pd.DataFrame,
        market_df: pd.DataFrame,
        event_date: pd.Timestamp,
        event_type: str = "generic",
        event_desc: str = "",
        symbol: str = "",
    ) -> Optional[EventWindow]:
        """
        Analyze price behavior around a single event.

        Args:
            df: Stock OHLCV data with 'datetime' column
            market_df: Market index data (Nifty 50)
            event_date: Date of the event
            event_type: Type of event
            event_desc: Description
            symbol: Stock symbol

        Returns:
            EventWindow or None if insufficient data
        """
        # Find event index
        dates = pd.to_datetime(df["datetime"])
        event_idx = dates.searchsorted(event_date)

        if event_idx < self.estimation_window + self.estimation_gap + self.pre_event_window:
            logger.debug(f"Insufficient pre-event data for {event_date}")
            return None

        if event_idx + self.post_event_window >= len(df):
            logger.debug(f"Insufficient post-event data for {event_date}")
            return None

        # Stock returns
        stock_returns = df["close"].pct_change()

        # Market returns (aligned by date)
        market_returns = market_df.set_index("datetime")["close"].pct_change()
        market_returns = market_returns.reindex(dates).ffill()

        # Estimation window
        est_start = event_idx - self.estimation_window - self.estimation_gap
        est_end = event_idx - self.estimation_gap

        alpha, beta = self._estimate_normal_return(
            stock_returns.iloc[est_start:est_end],
            market_returns.iloc[est_start:est_end],
        )

        # Event window: compute abnormal returns
        event_start = event_idx - self.pre_event_window
        event_end = event_idx + self.post_event_window

        pre_ar = []
        post_ar = []

        for i in range(event_start, event_end + 1):
            if i >= len(stock_returns) or i >= len(market_returns):
                break

            actual = stock_returns.iloc[i]
            expected = alpha + beta * market_returns.iloc[i]
            ar = actual - expected

            if np.isnan(ar):
                ar = 0.0

            if i < event_idx:
                pre_ar.append(ar)
            else:
                post_ar.append(ar)

        # Cumulative abnormal return
        car = sum(pre_ar) + sum(post_ar)
        pre_drift = sum(pre_ar)
        post_drift = sum(post_ar)

        # Abnormal volume at event
        vol_mean = df["volume"].iloc[est_start:est_end].mean()
        event_vol = df["volume"].iloc[event_idx]
        abnormal_vol = event_vol / max(vol_mean, 1) if vol_mean > 0 else 1.0

        return EventWindow(
            event_date=event_date,
            event_type=event_type,
            event_description=event_desc,
            symbol=symbol,
            pre_event_returns=pre_ar,
            post_event_returns=post_ar,
            car=car,
            pre_drift=pre_drift,
            post_drift=post_drift,
            abnormal_volume=abnormal_vol,
        )

    def analyze_event_type(
        self,
        df: pd.DataFrame,
        market_df: pd.DataFrame,
        event_dates: list[pd.Timestamp],
        event_type: str = "generic",
        symbol: str = "",
    ) -> Optional[EventStudyResult]:
        """
        Analyze a set of events of the same type.

        Returns statistical summary of cumulative abnormal returns.
        """
        windows = []

        for event_date in event_dates:
            window = self.analyze_single_event(
                df, market_df, event_date, event_type, symbol=symbol,
            )
            if window is not None:
                windows.append(window)

        if len(windows) < self.min_events:
            logger.warning(
                f"Only {len(windows)} valid events for {event_type} "
                f"(need {self.min_events})"
            )
            return None

        # Aggregate
        cars = [w.car for w in windows]
        pre_drifts = [w.pre_drift for w in windows]
        post_drifts = [w.post_drift for w in windows]
        abnormal_volumes = [w.abnormal_volume for w in windows]

        avg_car = np.mean(cars)
        avg_pre = np.mean(pre_drifts)
        avg_post = np.mean(post_drifts)
        avg_vol = np.mean(abnormal_volumes)

        # T-test for average CAR
        if len(cars) > 1:
            t_stat, p_value = stats.ttest_1samp(cars, 0)
        else:
            t_stat, p_value = 0.0, 1.0

        # Post-event reversal: opposite sign of CAR after initial drift
        post_reversal = -avg_post / max(abs(avg_car), 1e-6) if avg_car != 0 else 0

        pct_positive = sum(1 for c in cars if c > 0) / len(cars)

        is_significant = bool(p_value < 0.05)
        economic_significance = bool(abs(avg_car) > 0.01)  # > 1%

        result = EventStudyResult(
            event_type=event_type,
            n_events=len(windows),
            avg_car=avg_car,
            car_t_stat=float(t_stat),
            car_p_value=float(p_value),
            avg_pre_drift=avg_pre,
            avg_post_drift=avg_post,
            post_event_reversal=float(post_reversal),
            pct_positive_car=pct_positive,
            avg_abnormal_volume=avg_vol,
            event_windows=windows,
            is_significant=is_significant,
            economic_significance=economic_significance,
        )

        logger.info(
            f"Event study [{event_type}]: N={len(windows)}, "
            f"avg CAR={avg_car:.4f}, t={t_stat:.2f}, p={p_value:.4f}, "
            f"significant={is_significant}"
        )

        return result

    def detect_earnings_dates(
        self,
        df: pd.DataFrame,
        volume_multiplier: float = 2.5,
        return_threshold: float = 0.03,
    ) -> list[pd.Timestamp]:
        """
        Heuristic detection of earnings announcement dates.

        Looks for days with:
        - Abnormally high volume (> 2.5x average)
        - Large absolute return (> 3%)
        - Occurring roughly quarterly
        """
        df = df.copy()
        df["return"] = df["close"].pct_change().abs()
        df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()

        # Candidate earnings dates
        candidates = df[
            (df["vol_ratio"] > volume_multiplier) &
            (df["return"] > return_threshold)
        ]

        if candidates.empty:
            return []

        # Filter to roughly quarterly (min 45 days between events)
        dates = pd.to_datetime(candidates["datetime"]).sort_values().tolist()
        filtered = [dates[0]]
        for d in dates[1:]:
            if (d - filtered[-1]).days > 45:
                filtered.append(d)

        return filtered

    def generate_report(self, result: EventStudyResult) -> str:
        """Generate formatted event study report."""
        lines = [
            f"=" * 60,
            f"EVENT STUDY: {result.event_type.upper()}",
            f"=" * 60,
            f"Number of Events:      {result.n_events}",
            f"Average CAR:           {result.avg_car:>+.4f} ({result.avg_car*100:>+.2f}%)",
            f"T-Statistic:           {result.car_t_stat:>8.3f}",
            f"P-Value:               {result.car_p_value:>8.4f}",
            f"Statistically Sig:     {'YES' if result.is_significant else 'NO'}",
            f"Economically Sig:      {'YES' if result.economic_significance else 'NO'}",
            "",
            f"Pre-Event Drift:       {result.avg_pre_drift:>+.4f}",
            f"Post-Event Drift:      {result.avg_post_drift:>+.4f}",
            f"Post-Event Reversal:   {result.post_event_reversal:>+.4f}",
            f"% Positive CAR:        {result.pct_positive_car:>8.1%}",
            f"Avg Abnormal Volume:   {result.avg_abnormal_volume:>8.1f}x",
            "",
        ]

        if result.is_significant and result.economic_significance:
            lines.append(
                "[ACTIONABLE] This event type shows statistically AND "
                "economically significant abnormal returns."
            )
        elif result.is_significant:
            lines.append(
                "[NOTABLE] Statistically significant but economically "
                "small abnormal returns. May not survive transaction costs."
            )
        else:
            lines.append(
                "[NO EDGE] No statistically significant abnormal returns "
                "detected for this event type."
            )

        lines.append(f"=" * 60)
        return "\n".join(lines)
