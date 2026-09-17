"""
Live strategy adapter — binds the live paper session to the VALIDATED strategy
classes in src/strategies/ instead of re-implementing simplified inline rules.

Before this adapter the live session decided entries with ad-hoc thresholds
("spot moved 15 points since process start"), while the backtested edge lived in
strategy classes that the live path never imported. Signals now come from the
same code objects that the research pipeline validated, so live and backtest
share one implementation.

Fail-closed contract: when the authentic bar/VIX state cannot be assembled, or
the strategy yields no actionable signal, the adapter returns a LiveSignal with
direction 0 and a reason. It never invents a signal.

NOT MODELLED / KNOWN DIVERGENCE: the validated strategies were fitted on settled
DAILY bars. Live evaluation necessarily feeds them today's FORMING bar, whose
high/low/close evolve intraday. The adapter therefore reproduces the strategy
logic exactly but on a bar that is not yet final. This is disclosed on every
signal via `on_forming_bar=True` and must be accounted for when comparing live
results with backtests.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.live_market_bars import build_strategy_frame
from src.utils.logging import setup_logging

logger = setup_logging("execution.live_strategy")


@dataclass
class LiveSignal:
    """A signal produced by a real strategy class on live data."""
    strategy_name: str
    strategy_class: str
    direction: int          # 1 = bullish (CE), -1 = bearish (PE), 0 = no trade
    confidence: float
    underlying: str
    reason: str = ""
    on_forming_bar: bool = True
    bar_source: str = "UNKNOWN"
    evaluated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_actionable(self) -> bool:
        return self.direction != 0


# Bot label -> (module path, class name, underlying, needs VIX column)
STRATEGY_BINDINGS: Dict[str, Dict[str, Any]] = {
    "Strategy 1: Apex VRP Engine": {
        "module": "src.strategies.options_theta",
        "class": "NiftyWeeklyIronCondorStrategy",
        "underlying": "NIFTY",
        "require_vix": True,
        "require_rsi": True,
        "parity": "UNRESOLVED",
        "parity_note": (
            "Research generate_signals emits only a rangebound regime flag; the "
            "validated Iron Condor wings (wing_sd=2.4) are declared but never "
            "simulated, and the backtest uses a fabricated flat credit per lot. "
            "Live execution cannot be made faithful without inventing unvalidated "
            "strategy behaviour, so entries fail closed."
        ),
    },
    "Strategy 2: Zen Curvature Overnight": {
        "module": "src.strategies.curvature_credit_spread",
        "class": "CurvatureCreditSpreadStrategy",
        "underlying": "NIFTY",
        "require_vix": True,
        "require_rsi": True,
        "parity": "UNRESOLVED",
        "parity_note": (
            "Research generate_signals emits only `vix < max_vix`; the RSI-branched "
            "Bull Put / Bear Call / Condor selection and the overnight holding "
            "semantics exist only in prose and in a backtest-only simulator. The "
            "runtime's same-day vertical is materially different, so entries fail "
            "closed pending a strategy-owner decision."
        ),
    },
    "Strategy 3: Confluence Gamma Scalper": {
        "module": "src.strategies.confluence_scalper",
        "class": "ConfluenceGammaScalperStrategy",
        "parity": "PASS",
        "underlying": "NIFTY",
        "require_vix": False,
    },
    "Strategy 4: Golden Trend Runner": {
        "module": "src.strategies.golden_trend_buyer",
        "class": "GoldenTrendOptionBuyerStrategy",
        "parity": "PASS",
        "underlying": "NIFTY",
        "require_vix": False,
    },
    "Strategy 5: Velocity-5 Momentum Scalper": {
        "module": "src.strategies.active_momentum_scalper",
        "class": "ActiveMomentumOptionScalperStrategy",
        "parity": "PASS",
        "underlying": "NIFTY",
        "require_vix": False,
    },
    "Strategy 6: Micro Momentum Sniper": {
        "module": "src.strategies.micro_momentum_buyer",
        "class": "MicroMomentumBuyerStrategy",
        "parity": "PASS",
        "underlying": "NIFTY",
        "require_vix": True,
    },
}


class LiveStrategyAdapter:
    """
    Instantiates the validated strategy classes once and evaluates them against
    live bar state. Strategy parameters are left exactly as validated — this
    adapter never overrides a threshold, window or multiplier.
    """

    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self._frame_cache: Dict[str, pd.DataFrame] = {}

    def get_strategy(self, bot_name: str):
        """Lazily imports and instantiates the real strategy class for a bot."""
        if bot_name in self._instances:
            return self._instances[bot_name]
        binding = STRATEGY_BINDINGS.get(bot_name)
        if not binding:
            return None
        try:
            module = __import__(binding["module"], fromlist=[binding["class"]])
            cls = getattr(module, binding["class"])
            self._instances[bot_name] = cls()  # default (validated) parameters
            return self._instances[bot_name]
        except Exception as e:
            logger.error(f"Failed to load strategy class for {bot_name}: {e}")
            return None

    def reset_cycle(self) -> None:
        """Clears per-cycle frame caches so each cycle re-reads live state."""
        self._frame_cache.clear()

    def _frame_for(
        self,
        underlying: str,
        require_vix: bool,
        require_rsi: bool,
        min_bars: int,
        session_bar: Optional[Dict[str, float]],
        today_vix: Optional[float],
        trading_day: Optional[date],
    ) -> Optional[pd.DataFrame]:
        key = f"{underlying}_{require_vix}_{require_rsi}_{min_bars}"
        if key in self._frame_cache:
            return self._frame_cache[key]
        frame = build_strategy_frame(
            underlying,
            session_bar=session_bar,
            trading_day=trading_day,
            min_bars=min_bars,
            today_vix=today_vix,
            require_vix=require_vix,
            require_rsi=require_rsi,
        )
        if frame is not None:
            self._frame_cache[key] = frame
        return frame

    def evaluate(
        self,
        bot_name: str,
        session_bar: Optional[Dict[str, float]] = None,
        today_vix: Optional[float] = None,
        trading_day: Optional[date] = None,
    ) -> LiveSignal:
        """
        Runs the real strategy class and returns its signal for the latest bar.

        Any failure to assemble authentic state, load the strategy, or obtain an
        actionable signal yields direction 0 with an explicit reason.
        """
        binding = STRATEGY_BINDINGS.get(bot_name)
        if not binding:
            return LiveSignal(bot_name, "UNBOUND", 0, 0.0, "NIFTY",
                              reason="NO_STRATEGY_BINDING")

        # Parity gate: a bot whose live construction is materially different from
        # the validated research strategy must not trade. Making it "work" would
        # require inventing strategy behaviour that was never validated, so it
        # fails closed until the strategy owner resolves the divergence.
        if binding.get("parity") == "UNRESOLVED":
            return LiveSignal(
                bot_name, binding["class"], 0, 0.0, binding["underlying"],
                reason=f"STRATEGY_PARITY_UNRESOLVED: {binding.get('parity_note', '')}",
            )

        strategy = self.get_strategy(bot_name)
        if strategy is None:
            return LiveSignal(bot_name, binding["class"], 0, 0.0, binding["underlying"],
                              reason="STRATEGY_CLASS_UNAVAILABLE")

        min_bars = int(getattr(strategy, "min_data_points", 50))
        frame = self._frame_for(
            binding["underlying"], binding.get("require_vix", False),
            binding.get("require_rsi", False), min_bars,
            session_bar, today_vix, trading_day,
        )
        if frame is None or frame.empty:
            return LiveSignal(bot_name, binding["class"], 0, 0.0, binding["underlying"],
                              reason="DATA_UNAVAILABLE: authentic bar/VIX state unavailable")

        try:
            sig_df = strategy.generate_signals(frame)
        except Exception as e:
            logger.error(f"{bot_name}: strategy.generate_signals raised {e}")
            return LiveSignal(bot_name, binding["class"], 0, 0.0, binding["underlying"],
                              reason=f"STRATEGY_ERROR: {e}")

        if sig_df is None or len(sig_df) == 0 or "signal" not in sig_df.columns:
            return LiveSignal(bot_name, binding["class"], 0, 0.0, binding["underlying"],
                              reason="NO_SIGNAL: strategy returned no actionable rows")

        last = sig_df.iloc[-1]
        try:
            direction = int(last["signal"])
        except Exception:
            direction = 0
        confidence = float(last["confidence"]) if "confidence" in sig_df.columns else 0.0

        return LiveSignal(
            strategy_name=bot_name,
            strategy_class=binding["class"],
            direction=direction,
            confidence=confidence,
            underlying=binding["underlying"],
            reason="STRATEGY_SIGNAL" if direction != 0 else "NO_SIGNAL: strategy flat",
            on_forming_bar=bool(frame.attrs.get("is_forming_bar", True)),
            bar_source=str(frame.attrs.get("session_bar_source", "UNKNOWN")),
        )
