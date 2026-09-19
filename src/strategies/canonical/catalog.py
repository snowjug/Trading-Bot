"""
Canonical Strategy Catalog.
Instantiates all required canonical benchmark strategies from Sections 6-23
of the Canonical Indian Trading Strategy Benchmark Master Prompt.
"""
from typing import Dict, List
from src.strategies.canonical.models import (
    CanonicalStrategyDefinition,
    StrategyFamily,
    InstrumentClass,
)


def get_all_canonical_strategies() -> Dict[str, CanonicalStrategyDefinition]:
    """Returns the complete dictionary of canonical strategy definitions."""
    strategies: List[CanonicalStrategyDefinition] = [
        # ══════════════════════════════════════════════════════════════════════
        # 1. PRICE ACTION BENCHMARKS (Section 6)
        # ══════════════════════════════════════════════════════════════════════
        CanonicalStrategyDefinition(
            name="NIFTY_ORB_15_1R",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Toby Crabel / Classical Opening Range Breakout",
            economic_mechanism="Price discovery momentum in initial 15-minute range expansion",
            entry_rules={
                "or_start": "09:15",
                "or_end": "09:30",
                "long_trigger": "close > or_high",
                "short_trigger": "close < or_low",
                "entry_window": ("09:30", "14:30"),
                "max_attempts_per_day": 1
            },
            stop_rules={"type": "OPPOSITE_OR_LEVEL"},
            target_rules={"type": "FIXED_R", "multiple": 1.0},
            exit_rules={"type": "EOD_OR_STOP_OR_TARGET", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_ORB_15_1.5R",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Classical ORB Practitioner Literature",
            economic_mechanism="Intraday trend continuation beyond 15m range with 1.5R payoff",
            entry_rules={
                "or_start": "09:15",
                "or_end": "09:30",
                "long_trigger": "close > or_high",
                "short_trigger": "close < or_low",
                "entry_window": ("09:30", "14:30"),
                "max_attempts_per_day": 1
            },
            stop_rules={"type": "OPPOSITE_OR_LEVEL"},
            target_rules={"type": "FIXED_R", "multiple": 1.5},
            exit_rules={"type": "EOD_OR_STOP_OR_TARGET", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_ORB_15_2R",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Classical ORB Practitioner Literature",
            economic_mechanism="Asymmetric risk-reward continuation on range expansion",
            entry_rules={
                "or_start": "09:15",
                "or_end": "09:30",
                "long_trigger": "close > or_high",
                "short_trigger": "close < or_low",
                "entry_window": ("09:30", "14:30"),
                "max_attempts_per_day": 1
            },
            stop_rules={"type": "OPPOSITE_OR_LEVEL"},
            target_rules={"type": "FIXED_R", "multiple": 2.0},
            exit_rules={"type": "EOD_OR_STOP_OR_TARGET", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_ORB_15_EOD",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Arthur Merrill / Day-trend expansion",
            economic_mechanism="Full-session hold in breakout direction without early target capping",
            entry_rules={
                "or_start": "09:15",
                "or_end": "09:30",
                "long_trigger": "close > or_high",
                "short_trigger": "close < or_low",
                "entry_window": ("09:30", "14:30"),
                "max_attempts_per_day": 1
            },
            stop_rules={"type": "OPPOSITE_OR_LEVEL"},
            target_rules=None,
            exit_rules={"type": "EOD_AT_MARKET", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_ORB_30_1.5R",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Classical 30-minute ORB",
            economic_mechanism="Institutional opening auction resolution after 09:45",
            entry_rules={
                "or_start": "09:15",
                "or_end": "09:45",
                "long_trigger": "close > or_high",
                "short_trigger": "close < or_low",
                "entry_window": ("09:45", "14:30"),
                "max_attempts_per_day": 1
            },
            stop_rules={"type": "OPPOSITE_OR_LEVEL"},
            target_rules={"type": "FIXED_R", "multiple": 1.5},
            exit_rules={"type": "EOD_OR_STOP_OR_TARGET", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_VWAP_TREND",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Volume Weighted Average Price Institutional Benchmark",
            economic_mechanism="Institutional momentum when spot holds above/below session volume-weighted price",
            entry_rules={
                "long_trigger": "crosses_above(close, vwap) and close > open",
                "short_trigger": "crosses_below(close, vwap) and close < open",
                "entry_window": ("09:45", "14:30")
            },
            stop_rules={"type": "TRAILING_VWAP_CROSS"},
            target_rules=None,
            exit_rules={"type": "EOD_AT_MARKET", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_VWAP_MEAN_REVERSION",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="VWAP Standard Deviation Bands",
            economic_mechanism="Elastic mean reversion to volume-weighted fair value after extreme intraday stretch",
            entry_rules={
                "long_trigger": "close <= vwap - 2.0 * vwap_std",
                "short_trigger": "close >= vwap + 2.0 * vwap_std",
                "entry_window": ("10:00", "14:00")
            },
            stop_rules={"type": "ATR_MULTIPLE", "multiple": 1.0},
            target_rules={"type": "VWAP_MIDLINE"},
            exit_rules={"type": "TARGET_OR_STOP_OR_EOD", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_GAP_FADE",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Opening Gap Reversion Literature",
            economic_mechanism="Overnight inventory rebalancing fading excessive retail opening imbalances",
            entry_rules={
                "gap_condition": "abs(open_0915 - prev_close) >= 0.5 * daily_atr",
                "long_fade": "open_0915 < prev_close and close_0920 > open_0915",
                "short_fade": "open_0915 > prev_close and close_0920 < open_0915",
                "entry_time": "09:20"
            },
            stop_rules={"type": "ATR_MULTIPLE", "multiple": 0.5},
            target_rules={"type": "PREVIOUS_CLOSE"},
            exit_rules={"type": "TARGET_OR_STOP_OR_EOD", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="NIFTY_GAP_CONTINUATION",
            family=StrategyFamily.PRICE_ACTION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="5m",
            source="Opening Gap Continuation / Breakaway Gap",
            economic_mechanism="Order flow continuation following institutional opening gap drive",
            entry_rules={
                "gap_condition": "abs(open_0915 - prev_close) >= 0.5 * daily_atr",
                "long_continuation": "open_0915 > prev_close and close_0930 > high_0915_0930_open",
                "short_continuation": "open_0915 < prev_close and close_0930 < low_0915_0930_open",
                "entry_time": "09:30"
            },
            stop_rules={"type": "OPPOSITE_15M_OR_EXTREME"},
            target_rules={"type": "FIXED_R", "multiple": 1.5},
            exit_rules={"type": "TARGET_OR_STOP_OR_EOD", "eod_time": "15:10"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 150000.0}
        ),

        # ══════════════════════════════════════════════════════════════════════
        # 2. TREND-FOLLOWING BENCHMARKS (Section 7)
        # ══════════════════════════════════════════════════════════════════════
        CanonicalStrategyDefinition(
            name="FUT_MA_CROSS_20_50",
            family=StrategyFamily.TREND_FOLLOWING.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Classical Dual Moving Average Crossover",
            economic_mechanism="Persistent intermediate-term macro capital flow trend capture",
            entry_rules={
                "long_trigger": "ema_20 crosses_above ema_50",
                "short_trigger": "ema_20 crosses_below ema_50",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "REVERSE_CROSSOVER"},
            target_rules=None,
            exit_rules={"type": "ON_REVERSE_SIGNAL"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="FUT_MA_CROSS_50_200",
            family=StrategyFamily.TREND_FOLLOWING.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Golden Cross / Death Cross Benchmark",
            economic_mechanism="Long-term multi-month secular regime following",
            entry_rules={
                "long_trigger": "sma_50 crosses_above sma_200",
                "short_trigger": "sma_50 crosses_below sma_200",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "REVERSE_CROSSOVER"},
            target_rules=None,
            exit_rules={"type": "ON_REVERSE_SIGNAL"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="FUT_DONCHIAN_20D",
            family=StrategyFamily.TREND_FOLLOWING.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Richard Donchian / Turtle Trading System 1",
            economic_mechanism="Breakout of 20-day price channel capturing expanding trending regimes",
            entry_rules={
                "long_trigger": "close > max(high, 20)",
                "short_trigger": "close < min(low, 20)",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "OPPOSITE_CHANNEL_10D"},
            target_rules=None,
            exit_rules={"type": "CHANNEL_EXIT", "lookback": 10},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="FUT_DONCHIAN_55D",
            family=StrategyFamily.TREND_FOLLOWING.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Richard Donchian / Turtle Trading System 2",
            economic_mechanism="Longer-period channel breakout resistant to intermediate whipsaws",
            entry_rules={
                "long_trigger": "close > max(high, 55)",
                "short_trigger": "close < min(low, 55)",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "OPPOSITE_CHANNEL_20D"},
            target_rules=None,
            exit_rules={"type": "CHANNEL_EXIT", "lookback": 20},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="FUT_SUPERTREND_10_3",
            family=StrategyFamily.TREND_FOLLOWING.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Olivier Seban Supertrend Baseline",
            economic_mechanism="Adaptive volatility-banded trend continuation",
            entry_rules={
                "long_trigger": "close crosses_above supertrend(10, 3)",
                "short_trigger": "close crosses_below supertrend(10, 3)",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "TRAILING_SUPERTREND"},
            target_rules=None,
            exit_rules={"type": "ON_REVERSE_SIGNAL"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),

        # ══════════════════════════════════════════════════════════════════════
        # 3. MOMENTUM BENCHMARKS (Section 8)
        # ══════════════════════════════════════════════════════════════════════
        CanonicalStrategyDefinition(
            name="MOM_TS_NIFTY_FUT",
            family=StrategyFamily.MOMENTUM.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Moskowitz, Ooi, Pedersen (JFE 2012) Time Series Momentum",
            economic_mechanism="12-month sign predictability in macro index futures",
            entry_rules={
                "long_trigger": "ret_252d > 0",
                "short_trigger": "ret_252d < 0",
                "rebalance": "monthly_close"
            },
            stop_rules={"type": "MONTHLY_REBALANCE"},
            target_rules=None,
            exit_rules={"type": "MONTHLY_REBALANCE"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="MOM_CS_FUTSTK_20D",
            family=StrategyFamily.MOMENTUM.value,
            instrument="STOCK_FUT_PANEL",
            instrument_class=InstrumentClass.STOCK_FUTURE.value,
            timeframe="1d",
            source="Jegadeesh & Titman (1993) / Indian Stock Futures Panel",
            economic_mechanism="Cross-sectional relative strength persistence across 280+ F&O stocks over 1 month",
            entry_rules={
                "ranking_lookback": 20,
                "long_portfolio": "top_quintile_by_return",
                "short_portfolio": "bottom_quintile_by_return",
                "rebalance_frequency": "monthly_expiry_roll"
            },
            stop_rules={"type": "SCHEDULED_REBALANCE"},
            target_rules=None,
            exit_rules={"type": "SCHEDULED_REBALANCE"},
            capital_requirement={"rule": "PORTFOLIO_SPAN", "minimum_account": 500000.0}
        ),
        CanonicalStrategyDefinition(
            name="MOM_CS_FUTSTK_60D",
            family=StrategyFamily.MOMENTUM.value,
            instrument="STOCK_FUT_PANEL",
            instrument_class=InstrumentClass.STOCK_FUTURE.value,
            timeframe="1d",
            source="Quarterly Cross-Sectional Equity Momentum",
            economic_mechanism="Earnings drift and institutional accumulation persistence over 3 months",
            entry_rules={
                "ranking_lookback": 60,
                "long_portfolio": "top_quintile_by_return",
                "short_portfolio": "bottom_quintile_by_return",
                "rebalance_frequency": "monthly_expiry_roll"
            },
            stop_rules={"type": "SCHEDULED_REBALANCE"},
            target_rules=None,
            exit_rules={"type": "SCHEDULED_REBALANCE"},
            capital_requirement={"rule": "PORTFOLIO_SPAN", "minimum_account": 500000.0}
        ),
        CanonicalStrategyDefinition(
            name="MOM_CS_FUTSTK_120D",
            family=StrategyFamily.MOMENTUM.value,
            instrument="STOCK_FUT_PANEL",
            instrument_class=InstrumentClass.STOCK_FUTURE.value,
            timeframe="1d",
            source="Intermediate Cross-Sectional Momentum",
            economic_mechanism="6-month macro relative performance persistence",
            entry_rules={
                "ranking_lookback": 120,
                "long_portfolio": "top_quintile_by_return",
                "short_portfolio": "bottom_quintile_by_return",
                "rebalance_frequency": "monthly_expiry_roll"
            },
            stop_rules={"type": "SCHEDULED_REBALANCE"},
            target_rules=None,
            exit_rules={"type": "SCHEDULED_REBALANCE"},
            capital_requirement={"rule": "PORTFOLIO_SPAN", "minimum_account": 500000.0}
        ),

        # ══════════════════════════════════════════════════════════════════════
        # 4. MEAN REVERSION BENCHMARKS (Section 9)
        # ══════════════════════════════════════════════════════════════════════
        CanonicalStrategyDefinition(
            name="FUT_RSI_REVERSION_30_70",
            family=StrategyFamily.MEAN_REVERSION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="J. Welles Wilder RSI Classical Extremes",
            economic_mechanism="Over-extended momentum exhaustion reversion toward mean",
            entry_rules={
                "long_trigger": "rsi_14 < 30.0",
                "short_trigger": "rsi_14 > 70.0",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "ATR_MULTIPLE", "multiple": 2.0},
            target_rules={"type": "RSI_MIDLINE", "level": 50.0},
            exit_rules={"type": "TARGET_OR_MAX_HOLDING_DAYS", "max_days": 5},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="FUT_BOLLINGER_REVERSION_2SD",
            family=StrategyFamily.MEAN_REVERSION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="John Bollinger Bands Baseline",
            economic_mechanism="Statistical mean reversion from 2-standard-deviation price boundaries",
            entry_rules={
                "long_trigger": "close <= sma_20 - 2.0 * std_20",
                "short_trigger": "close >= sma_20 + 2.0 * std_20",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "ATR_MULTIPLE", "multiple": 2.0},
            target_rules={"type": "SMA_20_MIDLINE"},
            exit_rules={"type": "TARGET_OR_MAX_HOLDING_DAYS", "max_days": 5},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="FUT_ZSCORE_REVERSION_2SD",
            family=StrategyFamily.MEAN_REVERSION.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Statistical Arbitrage Z-Score Metric",
            economic_mechanism="Standardized price shock mean reversion",
            entry_rules={
                "long_trigger": "zscore_20 <= -2.0",
                "short_trigger": "zscore_20 >= 2.0",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "ATR_MULTIPLE", "multiple": 2.0},
            target_rules={"type": "ZSCORE_ZERO"},
            exit_rules={"type": "TARGET_OR_MAX_HOLDING_DAYS", "max_days": 5},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),

        # ══════════════════════════════════════════════════════════════════════
        # 5. OPTIONS STRUCTURE BENCHMARKS (Sections 11-19)
        # ══════════════════════════════════════════════════════════════════════
        CanonicalStrategyDefinition(
            name="OPT_ATM_STRADDLE_0DTE",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="5m",
            source="Intraday Expiry Day Gamma Scalping / Decay",
            economic_mechanism="Accelerated zero-DTE theta harvesting with independent call and put leg pricing",
            entry_rules={
                "dte": 0,
                "entry_time": "09:20",
                "legs": [
                    {"role": "short_call", "strike": "ATM", "side": "SELL"},
                    {"role": "short_put", "strike": "ATM", "side": "SELL"}
                ]
            },
            stop_rules={"type": "COMBINED_PREMIUM_STOP_PCT", "pct": 0.25},
            target_rules=None,
            exit_rules={"type": "EXPIRY_SETTLEMENT_OR_STOP", "time": "15:15"},
            capital_requirement={"rule": "EXCHANGE_SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_ATM_STRADDLE_WEEKLY",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="1d",
            source="Weekly Straddle Variance Risk Premium",
            economic_mechanism="Multi-day implied volatility premium over realized index variance",
            entry_rules={
                "dte_target": 5,
                "entry_day": "FRIDAY_OR_MONDAY",
                "legs": [
                    {"role": "short_call", "strike": "ATM", "side": "SELL"},
                    {"role": "short_put", "strike": "ATM", "side": "SELL"}
                ]
            },
            stop_rules={"type": "COMBINED_PREMIUM_STOP_PCT", "pct": 0.50},
            target_rules=None,
            exit_rules={"type": "EXPIRY_SETTLEMENT"},
            capital_requirement={"rule": "EXCHANGE_SPAN_MARGIN", "minimum_account": 180000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_STRANGLE_WEEKLY",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="1d",
            source="Weekly OTM Strangle Decay Literature (Durgia SSRN 5353404)",
            economic_mechanism="Selling out-of-the-money variance risk premium outside 1.5% weekly expected move",
            entry_rules={
                "dte_target": 5,
                "entry_day": "FRIDAY_OR_MONDAY",
                "legs": [
                    {"role": "short_call", "offset_pct": 0.015, "side": "SELL"},
                    {"role": "short_put", "offset_pct": -0.015, "side": "SELL"}
                ]
            },
            stop_rules={"type": "COMBINED_PREMIUM_STOP_PCT", "pct": 0.50},
            target_rules=None,
            exit_rules={"type": "EXPIRY_SETTLEMENT"},
            capital_requirement={"rule": "EXCHANGE_SPAN_MARGIN", "minimum_account": 180000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_BULL_PUT_SPREAD_WEEKLY",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="1d",
            source="Defined Risk Credit Spread Benchmark",
            economic_mechanism="Selling downside variance with explicit long put tail protection",
            entry_rules={
                "dte_target": 5,
                "legs": [
                    {"role": "short_put", "strike": "ATM_MINUS_100", "side": "SELL"},
                    {"role": "long_put", "strike": "ATM_MINUS_300", "side": "BUY"}
                ]
            },
            stop_rules={"type": "DEFINED_WING_WIDTH"},
            target_rules={"type": "MAX_PROFIT_CREDIT"},
            exit_rules={"type": "EXPIRY_SETTLEMENT"},
            capital_requirement={"rule": "DEFINED_MAX_LOSS", "minimum_account": 25000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_BEAR_CALL_SPREAD_WEEKLY",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="1d",
            source="Defined Risk Credit Spread Benchmark",
            economic_mechanism="Selling upside variance with explicit long call tail protection",
            entry_rules={
                "dte_target": 5,
                "legs": [
                    {"role": "short_call", "strike": "ATM_PLUS_100", "side": "SELL"},
                    {"role": "long_call", "strike": "ATM_PLUS_300", "side": "BUY"}
                ]
            },
            stop_rules={"type": "DEFINED_WING_WIDTH"},
            target_rules={"type": "MAX_PROFIT_CREDIT"},
            exit_rules={"type": "EXPIRY_SETTLEMENT"},
            capital_requirement={"rule": "DEFINED_MAX_LOSS", "minimum_account": 25000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_DEBIT_CALL_SPREAD_BREAKOUT",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="5m",
            source="Directional Vertical Debit Spread",
            economic_mechanism="Capped upside participation with theta-mitigated long call financing",
            entry_rules={
                "trigger": "NIFTY_ORB_15_LONG_BREAKOUT",
                "legs": [
                    {"role": "long_call", "strike": "ATM", "side": "BUY"},
                    {"role": "short_call", "strike": "ATM_PLUS_200", "side": "SELL"}
                ]
            },
            stop_rules={"type": "NET_DEBIT_OUTLAY"},
            target_rules={"type": "WING_WIDTH_MINUS_DEBIT"},
            exit_rules={"type": "EOD_OR_TARGET", "eod_time": "15:10"},
            capital_requirement={"rule": "NET_DEBIT_OUTLAY", "minimum_account": 20000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_DEBIT_PUT_SPREAD_BREAKDOWN",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="5m",
            source="Directional Vertical Debit Spread",
            economic_mechanism="Capped downside participation with theta-mitigated long put financing",
            entry_rules={
                "trigger": "NIFTY_ORB_15_SHORT_BREAKDOWN",
                "legs": [
                    {"role": "long_put", "strike": "ATM", "side": "BUY"},
                    {"role": "short_put", "strike": "ATM_MINUS_200", "side": "SELL"}
                ]
            },
            stop_rules={"type": "NET_DEBIT_OUTLAY"},
            target_rules={"type": "WING_WIDTH_MINUS_DEBIT"},
            exit_rules={"type": "EOD_OR_TARGET", "eod_time": "15:10"},
            capital_requirement={"rule": "NET_DEBIT_OUTLAY", "minimum_account": 20000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_IRON_CONDOR_WEEKLY",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="1d",
            source="Classical 4-Leg Defined Risk Iron Condor",
            economic_mechanism="Non-directional range bound theta harvesting with hard wing limits on both sides",
            entry_rules={
                "dte_target": 5,
                "legs": [
                    {"role": "long_put", "strike": "ATM_MINUS_350", "side": "BUY"},
                    {"role": "short_put", "strike": "ATM_MINUS_150", "side": "SELL"},
                    {"role": "short_call", "strike": "ATM_PLUS_150", "side": "SELL"},
                    {"role": "long_call", "strike": "ATM_PLUS_350", "side": "BUY"}
                ]
            },
            stop_rules={"type": "WING_WIDTH_BOUNDED"},
            target_rules={"type": "FULL_NET_CREDIT"},
            exit_rules={"type": "EXPIRY_SETTLEMENT"},
            capital_requirement={"rule": "DEFINED_MAX_LOSS", "minimum_account": 25000.0}
        ),
        CanonicalStrategyDefinition(
            name="OPT_IRON_FLY_0DTE",
            family=StrategyFamily.OPTIONS_SPREAD.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="5m",
            source="0DTE Iron Butterfly Benchmark",
            economic_mechanism="ATM straddle decay with symmetric OTM wing protection on expiry day",
            entry_rules={
                "dte": 0,
                "entry_time": "09:20",
                "legs": [
                    {"role": "long_put", "strike": "ATM_MINUS_200", "side": "BUY"},
                    {"role": "short_put", "strike": "ATM", "side": "SELL"},
                    {"role": "short_call", "strike": "ATM", "side": "SELL"},
                    {"role": "long_call", "strike": "ATM_PLUS_200", "side": "BUY"}
                ]
            },
            stop_rules={"type": "WING_WIDTH_BOUNDED"},
            target_rules={"type": "FULL_NET_CREDIT"},
            exit_rules={"type": "EXPIRY_SETTLEMENT_OR_1510", "time": "15:10"},
            capital_requirement={"rule": "DEFINED_MAX_LOSS", "minimum_account": 25000.0}
        ),

        # ══════════════════════════════════════════════════════════════════════
        # 6. VOLATILITY, PCR/OI, EXPIRY & OVERNIGHT BENCHMARKS (Sections 20-23)
        # ══════════════════════════════════════════════════════════════════════
        CanonicalStrategyDefinition(
            name="VOL_VRP_SHORT",
            family=StrategyFamily.OPTIONS_VOLATILITY.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="1d",
            source="Variance Risk Premium Literature (Carr & Wu 2009)",
            economic_mechanism="Systematically selling option implied variance when IV significantly exceeds RV(20)",
            entry_rules={
                "condition": "india_vix / realized_vol_20d >= 1.25",
                "structure": "IRON_CONDOR_WEEKLY"
            },
            stop_rules={"type": "WING_WIDTH_BOUNDED"},
            target_rules=None,
            exit_rules={"type": "EXPIRY_SETTLEMENT"},
            capital_requirement={"rule": "DEFINED_MAX_LOSS", "minimum_account": 25000.0}
        ),
        CanonicalStrategyDefinition(
            name="PCR_TREND_CONFIRMATION",
            family=StrategyFamily.PCR_OI.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="NSE Option Chain Open Interest Dynamics",
            economic_mechanism="Institutional put underwriting trend confirmation (High PCR precedes continuation)",
            entry_rules={
                "long_trigger": "pcr_oi > 1.10 and close > ema_20",
                "short_trigger": "pcr_oi < 0.80 and close < ema_20",
                "evaluation": "daily_close"
            },
            stop_rules={"type": "ATR_MULTIPLE", "multiple": 1.5},
            target_rules=None,
            exit_rules={"type": "PCR_CROSS_OR_TRAILING"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
        CanonicalStrategyDefinition(
            name="EXPIRY_0DTE_DECAY",
            family=StrategyFamily.EXPIRY.value,
            instrument="NIFTY_OPT",
            instrument_class=InstrumentClass.MULTI_LEG_OPTION.value,
            timeframe="5m",
            source="Zero-DTE Intraday Theta Decay",
            economic_mechanism="Pure terminal decay capture during expiry afternoon (12:30 -> 15:10)",
            entry_rules={
                "dte": 0,
                "entry_time": "12:30",
                "structure": "ATM_SHORT_STRADDLE"
            },
            stop_rules={"type": "PREMIUM_STOP_PCT", "pct": 0.30},
            target_rules=None,
            exit_rules={"type": "EOD_OR_SETTLEMENT", "eod_time": "15:10"},
            capital_requirement={"rule": "EXCHANGE_SPAN_MARGIN", "minimum_account": 150000.0}
        ),
        CanonicalStrategyDefinition(
            name="OVERNIGHT_FUT_DRIFT",
            family=StrategyFamily.OVERNIGHT.value,
            instrument="NIFTY_FUT",
            instrument_class=InstrumentClass.INDEX_FUTURE.value,
            timeframe="1d",
            source="Cliff, Cooper, Gulen (2008) Overnight Anomaly",
            economic_mechanism="Close-to-open global macro drift in near-month tradable index futures",
            entry_rules={
                "entry_time": "15:25",
                "side": "BUY"
            },
            stop_rules={"type": "NEXT_OPEN_EXIT"},
            target_rules=None,
            exit_rules={"type": "NEXT_SESSION_OPEN", "exit_time": "09:15"},
            capital_requirement={"rule": "SPAN_MARGIN", "minimum_account": 160000.0}
        ),
    ]

    return {s.name: s for s in strategies}
