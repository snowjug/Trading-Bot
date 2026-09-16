"""
Intrabar Path Dependency Simulator.
Resolves whether Stop Loss or Profit Target was reached first during an OHLC bar
under three rigorous statistical regimes:
1. CONSERVATIVE (Worst-Case): Stop Loss is assumed to be hit first.
2. OPTIMISTIC (Best-Case): Profit Target is assumed to be hit first.
3. RANDOMIZED: 50/50 stochastic path branching with Monte Carlo seed.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Tuple
import numpy as np


class IntrabarMode(Enum):
    CONSERVATIVE = "conservative"  # Stop loss hit first whenever ambiguous
    OPTIMISTIC = "optimistic"      # Target hit first
    RANDOMIZED = "randomized"      # 50/50 stochastic resolution


@dataclass
class IntrabarResolution:
    exit_price: float
    exit_reason: str
    is_stop: bool
    is_target: bool


class IntrabarSimulator:
    """
    Rigorously resolves intraday trade exits on OHLC bars
    without lookahead or optimistic target-favoring biases.
    """

    @staticmethod
    def resolve_exit(
        is_long: bool,
        entry_price: float,
        target_pts: float,
        stop_pts: float,
        high: float,
        low: float,
        close: float,
        mode: IntrabarMode = IntrabarMode.CONSERVATIVE,
        random_seed: int = 42,
    ) -> IntrabarResolution:
        """
        Determine trade exit on bar with entry_price, target, and stop.
        """
        if is_long:
            max_fav = high - entry_price
            max_adv = entry_price - low
            target_spot = entry_price + target_pts
            stop_spot = entry_price - stop_pts
        else:
            max_fav = entry_price - low
            max_adv = high - entry_price
            target_spot = entry_price - target_pts
            stop_spot = entry_price + stop_pts

        target_reached = max_fav >= target_pts
        stop_reached = max_adv >= stop_pts

        # Case 1: Both Target AND Stop fell within the same bar!
        # This is the ambiguous intrabar zone.
        if target_reached and stop_reached:
            if mode == IntrabarMode.CONSERVATIVE:
                # Worst-case: Stop loss triggered before target
                return IntrabarResolution(
                    exit_price=stop_spot,
                    exit_reason="STOP_CONSERVATIVE",
                    is_stop=True,
                    is_target=False,
                )
            elif mode == IntrabarMode.OPTIMISTIC:
                # Best-case: Target triggered before stop
                return IntrabarResolution(
                    exit_price=target_spot,
                    exit_reason="TARGET_OPTIMISTIC",
                    is_stop=False,
                    is_target=True,
                )
            else:  # RANDOMIZED
                np.random.seed(random_seed + int(entry_price * 10))
                stop_first = np.random.choice([True, False], p=[0.5, 0.5])
                if stop_first:
                    return IntrabarResolution(
                        exit_price=stop_spot,
                        exit_reason="STOP_RANDOMIZED",
                        is_stop=True,
                        is_target=False,
                    )
                else:
                    return IntrabarResolution(
                        exit_price=target_spot,
                        exit_reason="TARGET_RANDOMIZED",
                        is_stop=False,
                        is_target=True,
                    )

        # Case 2: Only Stop reached
        if stop_reached:
            return IntrabarResolution(
                exit_price=stop_spot,
                exit_reason="STOP_LOSS",
                is_stop=True,
                is_target=False,
            )

        # Case 3: Only Target reached
        if target_reached:
            return IntrabarResolution(
                exit_price=target_spot,
                exit_reason="TARGET_HIT",
                is_stop=False,
                is_target=True,
            )

        # Case 4: Neither reached -> EOD Market Close
        return IntrabarResolution(
            exit_price=close,
            exit_reason="EOD_CLOSE",
            is_stop=False,
            is_target=False,
        )
