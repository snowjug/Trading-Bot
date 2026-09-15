"""
Data validation pipeline.
Ensures data quality, detects anomalies, and normalizes format.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from src.utils.logging import setup_logging

logger = setup_logging("data.validator")


@dataclass
class ValidationReport:
    """Report from data validation."""
    symbol: str
    total_rows: int = 0
    duplicates_removed: int = 0
    missing_candles: int = 0
    ohlc_violations: int = 0
    volume_issues: int = 0
    timestamp_issues: int = 0
    quality_status: str = "UNKNOWN"  # GOOD, WARNING, POOR, FAILED
    issues: list = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[{self.quality_status}] {self.symbol}: "
            f"{self.total_rows} rows, {self.duplicates_removed} dups, "
            f"{self.missing_candles} missing, {self.ohlc_violations} OHLC violations"
        )


class DataValidator:
    """Validates and cleans OHLCV data."""

    def validate_and_clean(self, df: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, ValidationReport]:
        """
        Run full validation pipeline on OHLCV data.
        Returns cleaned DataFrame and validation report.
        """
        report = ValidationReport(symbol=symbol)

        if df.empty:
            report.quality_status = "FAILED"
            report.issues.append("Empty DataFrame")
            return df, report

        df = df.copy()
        report.total_rows = len(df)

        # Step 1: Validate and normalize timestamps
        df, report = self._validate_timestamps(df, report)

        # Step 2: Remove duplicates
        df, report = self._remove_duplicates(df, report)

        # Step 3: Validate OHLC relationships
        df, report = self._validate_ohlc(df, report)

        # Step 4: Validate volume
        df, report = self._validate_volume(df, report)

        # Step 5: Detect missing candles
        report = self._detect_missing_candles(df, report)

        # Step 6: Sort chronologically
        df = df.sort_values("datetime").reset_index(drop=True)

        # Determine quality status
        report.quality_status = self._assess_quality(report)
        report.total_rows = len(df)

        logger.info(report.summary())
        return df, report

    def _validate_timestamps(self, df: pd.DataFrame, report: ValidationReport) -> tuple[pd.DataFrame, ValidationReport]:
        """Ensure timestamps are valid and timezone-naive (IST assumed)."""
        if "datetime" not in df.columns:
            report.issues.append("No 'datetime' column found")
            report.timestamp_issues += 1
            return df, report

        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

        # Remove rows with invalid timestamps
        null_ts = df["datetime"].isna().sum()
        if null_ts > 0:
            report.timestamp_issues += null_ts
            report.issues.append(f"{null_ts} rows with invalid timestamps removed")
            df = df.dropna(subset=["datetime"])

        # Make timezone-naive (assume IST)
        if df["datetime"].dt.tz is not None:
            df["datetime"] = df["datetime"].dt.tz_localize(None)

        # Reject future dates
        future_mask = df["datetime"] > pd.Timestamp.now()
        future_count = future_mask.sum()
        if future_count > 0:
            report.issues.append(f"{future_count} future-dated rows removed")
            df = df[~future_mask]

        return df, report

    def _remove_duplicates(self, df: pd.DataFrame, report: ValidationReport) -> tuple[pd.DataFrame, ValidationReport]:
        """Remove duplicate timestamps, keeping last."""
        before = len(df)
        df = df.drop_duplicates(subset=["datetime"], keep="last")
        report.duplicates_removed = before - len(df)
        if report.duplicates_removed > 0:
            report.issues.append(f"{report.duplicates_removed} duplicate timestamps removed")
        return df, report

    def _validate_ohlc(self, df: pd.DataFrame, report: ValidationReport) -> tuple[pd.DataFrame, ValidationReport]:
        """Validate OHLC relationships: L <= O,C <= H and L <= H."""
        required = ["open", "high", "low", "close"]
        if not all(c in df.columns for c in required):
            report.issues.append("Missing OHLC columns")
            return df, report

        # High must be >= Open, Close, Low
        high_violations = (
            (df["high"] < df["open"]) |
            (df["high"] < df["close"]) |
            (df["high"] < df["low"])
        )

        # Low must be <= Open, Close, High
        low_violations = (
            (df["low"] > df["open"]) |
            (df["low"] > df["close"]) |
            (df["low"] > df["high"])
        )

        violations = high_violations | low_violations
        report.ohlc_violations = violations.sum()

        if report.ohlc_violations > 0:
            report.issues.append(f"{report.ohlc_violations} OHLC relationship violations")
            # Fix violations by adjusting H/L
            df.loc[high_violations, "high"] = df.loc[high_violations, ["open", "high", "low", "close"]].max(axis=1)
            df.loc[low_violations, "low"] = df.loc[low_violations, ["open", "high", "low", "close"]].min(axis=1)

        # Check for zero/negative prices
        zero_prices = (df[required] <= 0).any(axis=1).sum()
        if zero_prices > 0:
            report.issues.append(f"{zero_prices} rows with zero/negative prices removed")
            df = df[(df[required] > 0).all(axis=1)]

        return df, report

    def _validate_volume(self, df: pd.DataFrame, report: ValidationReport) -> tuple[pd.DataFrame, ValidationReport]:
        """Validate volume data."""
        if "volume" not in df.columns:
            return df, report

        # Negative volume
        neg_vol = (df["volume"] < 0).sum()
        if neg_vol > 0:
            report.volume_issues += neg_vol
            report.issues.append(f"{neg_vol} rows with negative volume (set to 0)")
            df.loc[df["volume"] < 0, "volume"] = 0

        # Zero volume days (may be valid for some instruments)
        zero_vol = (df["volume"] == 0).sum()
        if zero_vol > len(df) * 0.1:
            report.issues.append(f"High proportion of zero-volume bars: {zero_vol}/{len(df)}")

        return df, report

    def _detect_missing_candles(self, df: pd.DataFrame, report: ValidationReport) -> ValidationReport:
        """Detect missing trading days (for daily data)."""
        if len(df) < 2 or "datetime" not in df.columns:
            return report

        df_sorted = df.sort_values("datetime")
        date_diffs = df_sorted["datetime"].diff().dt.days

        # For daily data, gaps > 4 days (accounting for weekends + holidays)
        large_gaps = (date_diffs > 4).sum()
        report.missing_candles = large_gaps
        if large_gaps > 0:
            report.issues.append(f"{large_gaps} potential missing-data gaps (>4 calendar days)")

        return report

    def _assess_quality(self, report: ValidationReport) -> str:
        """Assess overall data quality."""
        if report.total_rows == 0:
            return "FAILED"

        dup_pct = report.duplicates_removed / max(report.total_rows, 1)
        ohlc_pct = report.ohlc_violations / max(report.total_rows, 1)

        if dup_pct > 0.1 or ohlc_pct > 0.05:
            return "POOR"
        elif report.missing_candles > 20 or ohlc_pct > 0.01:
            return "WARNING"
        else:
            return "GOOD"
