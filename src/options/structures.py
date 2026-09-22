"""
The allowed option structures, as leg builders.

A structure is a pure function of (spot, strike step, width, direction) returning
`LegSpec`s. It resolves nothing and prices nothing — that is `chain.py`'s job — so
these stay testable without any market data.

NAKED SHORT VOLATILITY IS NOT HERE. Not disabled by a flag that could be flipped:
absent. An autonomous agent in this system cannot express undefined risk, because no
builder exists that would produce it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

STEP_DEFAULT = 50.0


@dataclass(frozen=True)
class Leg:
    role: str            # short_call | long_call | short_put | long_put
    option_type: str     # CE | PE
    side: str            # BUY | SELL
    strike: float

    @property
    def qty_sign(self) -> int:
        return 1 if self.side == "BUY" else -1


def _round_strike(x: float, step: float) -> float:
    return round(x / step) * step


def atm_strike(spot: float, step: float = STEP_DEFAULT) -> float:
    return _round_strike(spot, step)


def build(structure: str, spot: float, step: float = STEP_DEFAULT,
          width_steps: int = 4, otm_steps: int = 0) -> List[Leg]:
    """
    Legs for `structure` around `spot`.

    width_steps  distance from the short leg to its protective long leg
    otm_steps    how far the short/primary leg sits from the money

    Every credit structure returned here is DEFINED RISK: each short leg has a long
    leg on the same side, further out. That invariant is asserted by
    `validate_defined_risk` and pinned by a test.
    """
    s = structure.upper().strip()
    k = atm_strike(spot, step)
    w = width_steps * step
    o = otm_steps * step

    if s == "LONG_CALL":
        return [Leg("long_call", "CE", "BUY", k + o)]
    if s == "LONG_PUT":
        return [Leg("long_put", "PE", "BUY", k - o)]

    if s == "BULL_CALL_SPREAD":          # debit, bullish
        return [Leg("long_call", "CE", "BUY", k + o),
                Leg("short_call", "CE", "SELL", k + o + w)]
    if s == "BEAR_PUT_SPREAD":           # debit, bearish
        return [Leg("long_put", "PE", "BUY", k - o),
                Leg("short_put", "PE", "SELL", k - o - w)]

    if s == "BULL_PUT_SPREAD":           # credit, bullish
        return [Leg("short_put", "PE", "SELL", k - o),
                Leg("long_put", "PE", "BUY", k - o - w)]
    if s == "BEAR_CALL_SPREAD":          # credit, bearish
        return [Leg("short_call", "CE", "SELL", k + o),
                Leg("long_call", "CE", "BUY", k + o + w)]

    if s == "IRON_FLY":                  # credit, neutral, defined
        return [Leg("long_put", "PE", "BUY", k - w),
                Leg("short_put", "PE", "SELL", k),
                Leg("short_call", "CE", "SELL", k),
                Leg("long_call", "CE", "BUY", k + w)]
    if s == "IRON_CONDOR":               # credit, neutral, defined
        return [Leg("long_put", "PE", "BUY", k - o - w),
                Leg("short_put", "PE", "SELL", k - o),
                Leg("short_call", "CE", "SELL", k + o),
                Leg("long_call", "CE", "BUY", k + o + w)]

    if s == "LONG_STRADDLE":             # debit, neutral
        return [Leg("long_call", "CE", "BUY", k), Leg("long_put", "PE", "BUY", k)]
    if s == "LONG_STRANGLE":             # debit, neutral
        return [Leg("long_call", "CE", "BUY", k + max(o, step)),
                Leg("long_put", "PE", "BUY", k - max(o, step))]

    raise ValueError(f"unknown or disallowed structure: {structure!r}")


def validate_defined_risk(legs: List[Leg]) -> Optional[str]:
    """
    None if the payoff is bounded on every side. A string naming the offender otherwise.

    The condition that actually matters is per OPTION TYPE: a short leg is dangerous
    only when there is no long leg of the same type to cap it. WHICH SIDE the long
    leg sits on does not matter, and an earlier version of this function got that
    wrong by demanding the long leg be further out of the money:

      credit spread  short PE 22800 / long PE 22600  -> below 22600 the long caps it
      debit  spread  short PE 22700 / long PE 22900  -> as spot falls BOTH move, and
                                                        the long gains MORE than the
                                                        short loses; the worst case is
                                                        spot above 22900, where the
                                                        loss is just the debit paid

    Both are bounded. Only a short leg with no same-type long leg at all is not, so
    the test is a count: longs must at least match shorts, per type.
    """
    for opt in ("CE", "PE"):
        shorts = sum(1 for L in legs if L.side == "SELL" and L.option_type == opt)
        longs = sum(1 for L in legs if L.side == "BUY" and L.option_type == opt)
        if shorts > longs:
            return (f"{shorts} short {opt} leg(s) against {longs} long {opt} leg(s) — "
                    f"the excess short is uncapped, which is undefined risk")
    return None


def max_loss_points(legs: List[Leg], net_credit: float) -> float:
    """
    Worst-case loss in index points for a defined-risk structure.

    Widest short-to-protection distance, less the credit received. For a debit
    structure the credit is negative and the loss is simply the debit paid.
    """
    if net_credit < 0:
        return abs(net_credit)
    worst = 0.0
    for L in legs:
        if L.side != "SELL":
            continue
        same = [x for x in legs if x.side == "BUY" and x.option_type == L.option_type]
        if L.option_type == "CE":
            cand = [x for x in same if x.strike > L.strike]
            prot = min(cand, key=lambda x: x.strike, default=None)
        else:
            cand = [x for x in same if x.strike < L.strike]
            prot = max(cand, key=lambda x: x.strike, default=None)
        if prot is None:
            return float("inf")
        worst = max(worst, abs(prot.strike - L.strike))
    return max(0.0, worst - net_credit)


def structure_direction(structure: str) -> int:
    return {
        "LONG_CALL": 1, "BULL_CALL_SPREAD": 1, "BULL_PUT_SPREAD": 1,
        "LONG_PUT": -1, "BEAR_PUT_SPREAD": -1, "BEAR_CALL_SPREAD": -1,
        "IRON_FLY": 0, "IRON_CONDOR": 0, "LONG_STRADDLE": 0, "LONG_STRANGLE": 0,
    }.get(structure.upper().strip(), 0)


def is_credit(structure: str) -> bool:
    return structure.upper().strip() in {
        "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_FLY", "IRON_CONDOR"}
