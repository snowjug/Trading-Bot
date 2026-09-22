"""
The agent loop: state -> candidates -> decision -> structure -> risk -> (order).

This module wires the pieces together and does no thinking of its own. Every step
either delegates or records. It is deliberately boring, because the interesting
properties of this system are all "X cannot happen", and boring plumbing is how you
keep them true.

The order of operations is the safety argument:

  1  build the state          causality enforced in market_state
  2  detect candidates        deterministic; usually returns nothing and we stop here
  3  consult the decider      the ONLY place a model is involved
  4  build the structure      from a fixed catalogue with no naked-short builder
  5  price it authentically   a leg that did not trade makes the trade UNPRICEABLE
  6  risk-gate it             deterministic, 12 gates, computes `lots`
  7  hand to the executor     which asserts the verdict was approved

Nothing may skip a step and nothing may reorder them, so `AgentOutcome` records which
step ended the attempt for every single bar.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.agent.deciders import Decider, DecisionRecord
from src.agent.decision_schema import AgentDecision
from src.market.market_state import MarketState
from src.market.setups import CandidateSetup, detect, options_vol_setup
from src.options.structures import Leg, build
from src.risk.structure_risk import PricedLeg, RiskLimits, RiskVerdict, evaluate

# Every attempt ends at exactly one of these. A replay that cannot account for every
# bar with one of these labels has a hole in it.
STOP_NO_CANDIDATE = "NO_CANDIDATE"
STOP_DECIDER_SKIP = "DECIDER_SKIP"
STOP_STRUCTURE_ERROR = "STRUCTURE_ERROR"
STOP_UNPRICEABLE = "UNPRICEABLE"
STOP_RISK_REJECTED = "RISK_REJECTED"
STOP_APPROVED = "APPROVED"


@dataclass
class AgentOutcome:
    bar_time: datetime
    stopped_at: str
    state_hash: str = ""
    candidates: List[str] = field(default_factory=list)
    decision: Optional[AgentDecision] = None
    decision_source: str = ""
    decision_errors: List[str] = field(default_factory=list)
    legs: Optional[List[PricedLeg]] = None
    price_reason: str = ""
    verdict: Optional[RiskVerdict] = None

    @property
    def approved(self) -> bool:
        return self.stopped_at == STOP_APPROVED

    def summary(self) -> Dict[str, Any]:
        return {
            "bar_time": self.bar_time, "stopped_at": self.stopped_at,
            "state_hash": self.state_hash, "candidates": ",".join(self.candidates),
            "structure": (self.decision.structure if self.decision else ""),
            "direction": (self.decision.direction if self.decision else ""),
            "decision_source": self.decision_source,
            "price_reason": self.price_reason,
            "gate_failed": (self.verdict.gate_failed if self.verdict else ""),
            "lots": (self.verdict.lots if self.verdict else 0),
            "credit_pts": (self.verdict.net_credit_pts if self.verdict else 0.0),
            "max_loss_pts": (self.verdict.max_loss_pts if self.verdict else 0.0),
            "edge_pts": (self.verdict.expected_edge_pts if self.verdict else 0.0),
            "capital_at_risk": (self.verdict.capital_at_risk if self.verdict else 0.0),
        }


class TradingAgent:
    """
    One decision per call to `step`. Holds no market data and no position state —
    those belong to the replay engine and the executor respectively, so the agent
    itself is stateless and trivially reusable across REPLAY and PAPER.
    """

    def __init__(self, decider: Decider, limits: RiskLimits,
                 chain: Any, *, strike_step: float = 50.0,
                 width_steps: int = 4, otm_steps: int = 0,
                 setup_cfg: Optional[Dict[str, float]] = None,
                 risk_engine: Any = None):
        self.decider = decider
        self.limits = limits
        self.chain = chain
        self.strike_step = float(strike_step)
        self.width_steps = int(width_steps)
        self.otm_steps = int(otm_steps)
        self.setup_cfg = setup_cfg
        self.risk_engine = risk_engine

    # ── step 2 ────────────────────────────────────────────────────────────────
    def candidates(self, st: MarketState, sess: date, t: dtime) -> List[CandidateSetup]:
        cs = detect(st, self.setup_cfg)
        straddle = None
        if hasattr(self.chain, "atm_straddle"):
            try:
                straddle = self.chain.atm_straddle(sess, t)
            except Exception:                                  # noqa: BLE001
                straddle = None
        if straddle:
            ov = options_vol_setup(st, straddle, None, self.setup_cfg)
            if ov is not None:
                cs = cs + [ov]
        return cs

    # ── the whole pipeline ────────────────────────────────────────────────────
    def step(self, st: MarketState, equity: float, lot_size: int, *,
             now: Optional[datetime] = None, open_positions: int = 0,
             trades_today: int = 0, daily_pnl: float = 0.0,
             position_note: Optional[str] = None,
             live_trading_enabled: bool = False) -> AgentOutcome:
        sess = st.bar_time.date()
        t = st.bar_time.time()

        cs = self.candidates(st, sess, t)
        if not cs:
            return AgentOutcome(st.bar_time, STOP_NO_CANDIDATE)

        rec: DecisionRecord = self.decider.decide(
            st, cs, options_note=self._options_note(sess, t), position_note=position_note)
        out = AgentOutcome(st.bar_time, STOP_DECIDER_SKIP, rec.state_hash,
                           [c.kind for c in cs], rec.decision, rec.source, rec.errors)
        if not rec.decision.wants_entry:
            return out

        try:
            legs: List[Leg] = build(rec.decision.structure, st.spot,
                                    step=self.strike_step,
                                    width_steps=self.width_steps,
                                    otm_steps=self.otm_steps)
        except ValueError as e:
            out.stopped_at = STOP_STRUCTURE_ERROR
            out.price_reason = str(e)
            return out

        priced, reason = self._price(legs, sess, t)
        out.price_reason = reason
        if priced is None:
            out.stopped_at = STOP_UNPRICEABLE
            return out
        out.legs = priced

        v = evaluate(rec.decision, st, priced, equity, lot_size, self.limits,
                     now=(now or st.bar_time),
                     live_trading_enabled=live_trading_enabled,
                     open_positions=open_positions, trades_today=trades_today,
                     daily_pnl=daily_pnl, risk_engine=self.risk_engine)
        out.verdict = v
        out.stopped_at = STOP_APPROVED if v.approved else STOP_RISK_REJECTED
        return out

    # ── helpers ───────────────────────────────────────────────────────────────
    def _price(self, legs: List[Leg], sess: date, t: dtime
               ) -> Tuple[Optional[List[PricedLeg]], str]:
        if hasattr(self.chain, "price_legs"):
            try:
                import inspect
                sig = inspect.signature(self.chain.price_legs)
                if "sess" in sig.parameters:
                    return self.chain.price_legs(legs, sess, t,
                                                 min_volume=self.limits.min_leg_volume)
                return self.chain.price_legs(legs,
                                             min_volume=self.limits.min_leg_volume)
            except Exception as e:                             # noqa: BLE001
                return None, f"PRICING_ERROR:{type(e).__name__}:{e}"
        return None, "NO_CHAIN"

    def _options_note(self, sess: date, t: dtime) -> Optional[str]:
        if not hasattr(self.chain, "atm_straddle"):
            return None
        try:
            s = self.chain.atm_straddle(sess, t)
        except Exception:                                      # noqa: BLE001
            return None
        return None if not s else f"ATM straddle {s:.1f} pts"


# ════════════════════════════════════════════════════════════════════════════
# Position monitoring — deterministic exits that the model cannot veto
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class OpenPosition:
    entry_time: datetime
    structure: str
    legs: List[PricedLeg]
    lots: int
    lot_size: int
    entry_credit_pts: float
    max_loss_pts: float
    stop_pts: float                 # interpreted according to `stop_type`
    target_pts: float
    max_hold_minutes: int
    decision: AgentDecision
    entry_spot: float = 0.0         # needed to interpret an UNDERLYING stop
    stop_type: str = "PREMIUM_PTS"
    session_exit: dtime = dtime(15, 15)

    def minutes_held(self, now: datetime) -> float:
        return (now - self.entry_time).total_seconds() / 60.0

    def premium_pnl_pts(self, mark_pts: float) -> float:
        """P&L in PREMIUM points. Positive means the position has made money."""
        return self.entry_credit_pts - mark_pts

    def stop_in_premium_pts(self, spot: Optional[float]) -> Optional[float]:
        """
        The stop expressed in PREMIUM points, whatever unit it was declared in.

        This exists because of a real bug. The heuristic declares
        `stop_type="UNDERLYING_STRUCTURE"` with a value of 1.2 x ATR(5m), i.e. about
        13 INDEX points, and an earlier version of `hard_exit_reason` compared that
        number directly against the position's PREMIUM P&L. On a 102-point straddle
        that is a 13% premium stop, so 38 of 55 trades stopped out on noise while the
        average best excursion was only +10.6 points. Index points and premium points
        are not the same unit and must not be compared.

          PREMIUM_PTS / PREMIUM_PCT   already premium; used directly or scaled
          R_MULTIPLE                  a multiple of the structure's own max loss
          UNDERLYING_STRUCTURE        an INDEX distance; converted with the
                                      structure's net delta, and refused when that
                                      conversion is not meaningful
        """
        t = (self.stop_type or "").upper()
        if t in ("PREMIUM_PTS", ""):
            return abs(self.stop_pts) if self.stop_pts else None
        if t == "PREMIUM_PCT":
            base = abs(self.entry_credit_pts) or abs(self.max_loss_pts)
            return abs(self.stop_pts) * base if base else None
        if t == "R_MULTIPLE":
            return (abs(self.stop_pts) * abs(self.max_loss_pts)
                    if self.max_loss_pts else None)
        if t == "UNDERLYING_STRUCTURE":
            d = abs(self._net_delta())
            if d <= 0.05 or not self.stop_pts:
                return None          # not convertible; the caller must not guess
            return abs(self.stop_pts) * d
        return None

    def _net_delta(self) -> float:
        """
        Crude net delta from the leg mix: near-the-money legs count 0.5, the rest 0.35.

        Deliberately crude and deliberately NOT model-derived. It only has to convert
        an index distance into a premium distance to within a factor, and a
        Black-Scholes delta here would be a fabricated number dressed as precision.
        A long straddle nets about zero, which correctly means an UNDERLYING stop is
        not convertible and the position falls back to its max-loss bound.
        """
        tot = 0.0
        for p in self.legs:
            approx = 0.5 if abs(p.leg.strike - self.entry_spot) <= 60 else 0.35
            sign = 1.0 if p.leg.option_type == "CE" else -1.0
            tot += p.leg.qty_sign * sign * approx
        return tot


HARD_EXITS = ("MAX_HOLD", "SESSION_EXIT", "STOP_HIT", "TARGET_HIT",
              "DATA_LOSS", "MAX_LOSS_REACHED")


def hard_exit_reason(pos: OpenPosition, now: datetime,
                     mark_pts: Optional[float],
                     spot: Optional[float] = None) -> Optional[str]:
    """
    Deterministic exits, checked before the model is ever asked about a position.

    `mark_pts` is the position's current value in PREMIUM points, or None when the
    market cannot be marked. A position that cannot be marked is not left alone:
    DATA_LOSS is an exit reason, because an unmarkable position is an unmanaged one.

    The stop is converted to premium points according to its declared type (see
    `OpenPosition.stop_in_premium_pts`). When it cannot be converted — a
    delta-neutral structure carrying an underlying-distance stop — NO stop is applied
    and the position is bounded by its max loss and its holding time instead.
    Silently comparing mismatched units is worse than having no stop.

    The model can recommend HOLD all it likes; if this returns a reason, it closes.
    """
    if now.time() >= pos.session_exit:
        return "SESSION_EXIT"
    if pos.minutes_held(now) >= pos.max_hold_minutes:
        return "MAX_HOLD"
    if mark_pts is None:
        return "DATA_LOSS"
    pnl = pos.premium_pnl_pts(mark_pts)
    stop = pos.stop_in_premium_pts(spot)
    if stop is not None and stop > 0 and pnl <= -stop:
        return "STOP_HIT"
    if pos.target_pts > 0 and pnl >= abs(pos.target_pts):
        return "TARGET_HIT"
    if pos.max_loss_pts > 0 and pnl <= -abs(pos.max_loss_pts):
        return "MAX_LOSS_REACHED"
    return None


def needs_reassessment(pos: OpenPosition, st: MarketState, prev: Optional[MarketState],
                       mark_pts: Optional[float],
                       min_minutes_between: int = 15,
                       last_asked: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Whether the model should be consulted about an OPEN position.

    This is the other half of token efficiency. Re-asking every bar would cost more
    than the entry decisions do, so the model is consulted only on a material change,
    and never more often than `min_minutes_between`.
    """
    if last_asked is not None:
        if (st.bar_time - last_asked).total_seconds() / 60.0 < min_minutes_between:
            return False, "TOO_SOON"
    if prev is None:
        return True, "NO_PRIOR_STATE"
    if st.regime_trend != prev.regime_trend:
        return True, "REGIME_CHANGED"
    if st.regime_vol_bucket != prev.regime_vol_bucket:
        return True, "VOL_REGIME_CHANGED"
    pa, pb = st.views.get(st.primary_tf), prev.views.get(prev.primary_tf)
    if pa and pb and pa.structure != pb.structure:
        return True, "STRUCTURE_CHANGED"
    stop = pos.stop_in_premium_pts(st.spot)
    if mark_pts is not None and stop:
        if abs(pos.premium_pnl_pts(mark_pts)) >= 0.7 * abs(stop):
            return True, "NEAR_STOP_OR_TARGET"
    return False, "NO_MATERIAL_CHANGE"
