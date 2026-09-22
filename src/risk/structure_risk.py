"""
THE RISK BOUNDARY. Deterministic, and the AI runs before it, never through it.

Every gate the directive lists is here, in order, each one able to reject on its own.
The AI's output is an INPUT to this function and has no privileged field: there is no
override, no force, no size, no confidence that buys leniency. `lots` is computed
here, from the account and the limits, and nowhere else.

Ordering is deliberate — the cheapest and most absolute checks first, so a rejection
costs nothing and the expensive pricing work only happens for a trade that could
actually be placed.

This layer delegates account-level questions (drawdown, daily and weekly loss limits,
kill switch) to the existing, already-audited `src/risk/risk_engine.RiskEngine`
rather than reimplementing them, because two implementations of a loss limit is how
a loss limit stops working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional

from src.agent.decision_schema import AgentDecision
from src.market.market_state import MarketState
from src.options.structures import (
    Leg, is_credit, max_loss_points, structure_direction, validate_defined_risk,
)

SESSION_OPEN = dtime(9, 15)
SESSION_CLOSE = dtime(15, 30)


@dataclass
class RiskLimits:
    """All of these are policy, loaded from configs/risk.yaml. None is AI-writable."""
    allow_naked_short: bool = False
    allowed_structures: List[str] = field(default_factory=lambda: [
        "LONG_CALL", "LONG_PUT", "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD",
        "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_FLY", "IRON_CONDOR",
        "LONG_STRADDLE", "LONG_STRANGLE"])
    risk_per_trade_pct: float = 0.01          # of equity, at risk on one trade
    max_deployed_pct: float = 0.60            # of equity, as margin/debit
    max_open_positions: int = 1
    max_trades_per_day: int = 3
    daily_loss_limit_pct: float = 0.03
    max_data_age_seconds: int = 300
    no_entry_after: dtime = dtime(15, 0)
    no_entry_before: dtime = dtime(9, 30)
    min_leg_volume: float = 1.0
    max_leg_spread_pct: float = 0.06          # of the leg's mid
    min_expected_edge_pts: float = 0.0        # must clear modelled cost
    max_lots: int = 10


@dataclass
class RiskVerdict:
    approved: bool
    lots: int = 0
    capital_at_risk: float = 0.0
    margin_or_debit: float = 0.0
    max_loss_pts: float = 0.0
    net_credit_pts: float = 0.0
    modelled_cost_pts: float = 0.0
    expected_edge_pts: float = 0.0
    rejections: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    gate_failed: str = ""

    def reject(self, gate: str, why: str) -> "RiskVerdict":
        self.approved = False
        self.gate_failed = gate
        self.rejections.append(f"[{gate}] {why}")
        return self


@dataclass
class PricedLeg:
    leg: Leg
    price: float             # traded / mid price
    fill: float              # price after half-spread + slippage, in the bad direction
    volume: float
    spread_pct: Optional[float] = None


def evaluate(
    decision: AgentDecision,
    state: MarketState,
    legs: List[PricedLeg],
    equity: float,
    lot_size: int,
    limits: RiskLimits,
    *,
    now: Optional[datetime] = None,
    live_trading_enabled: bool = False,
    open_positions: int = 0,
    trades_today: int = 0,
    daily_pnl: float = 0.0,
    risk_engine: Any = None,
) -> RiskVerdict:
    """
    The single decision point for whether a proposed structure may be placed.

    Returns a verdict carrying the computed `lots`. A caller that ignores `approved`
    and places an order anyway is a bug, and `agent_paper_executor` asserts on it.
    """
    v = RiskVerdict(approved=True)
    now = now or state.bar_time

    # ── 1. live trading is not a thing this system does ──────────────────────
    if live_trading_enabled:
        return v.reject("LIVE_DISABLED",
                        "LIVE_TRADING_ENABLED is true; this build refuses to place "
                        "orders in that mode")

    # ── 2. the decision must be a complete, executable intent ────────────────
    if not decision.wants_entry:
        return v.reject("NO_ENTRY_INTENT",
                        f"decision={decision.decision} action={decision.action}")

    # ── 3. structure must be permitted policy ────────────────────────────────
    s = decision.structure.upper().strip()
    if s not in {x.upper() for x in limits.allowed_structures}:
        return v.reject("STRUCTURE_NOT_ALLOWED", f"{s} is not in the allowed set")

    # ── 4. defined risk, checked independently of the builder ────────────────
    raw_legs = [p.leg for p in legs]
    if not raw_legs:
        return v.reject("NO_LEGS", "structure resolved to zero legs")
    undefined = validate_defined_risk(raw_legs)
    if undefined and not limits.allow_naked_short:
        return v.reject("UNDEFINED_RISK", undefined)

    # ── 5. data freshness ────────────────────────────────────────────────────
    age = (now - state.bar_time).total_seconds()
    if age > limits.max_data_age_seconds:
        return v.reject("STALE_DATA",
                        f"state is {age:.0f}s old, budget {limits.max_data_age_seconds}s")
    if age < 0:
        return v.reject("STALE_DATA", f"state is {-age:.0f}s in the future")

    # ── 6. session window ────────────────────────────────────────────────────
    t = now.time()
    if not (SESSION_OPEN <= t <= SESSION_CLOSE):
        return v.reject("OUT_OF_SESSION", f"{t} is outside NSE hours")
    if t < limits.no_entry_before:
        return v.reject("TOO_EARLY", f"{t} is before {limits.no_entry_before}")
    if t > limits.no_entry_after:
        return v.reject("TOO_LATE", f"{t} is after {limits.no_entry_after}")

    # ── 7. every leg must be genuinely tradable ──────────────────────────────
    for p in legs:
        if p.price <= 0:
            return v.reject("LEG_UNPRICEABLE",
                            f"{p.leg.option_type} {p.leg.strike:.0f} has no price")
        if p.volume < limits.min_leg_volume:
            return v.reject("LEG_ILLIQUID",
                            f"{p.leg.option_type} {p.leg.strike:.0f} traded "
                            f"{p.volume:g} < {limits.min_leg_volume:g}")
        if p.spread_pct is not None and p.spread_pct > limits.max_leg_spread_pct:
            return v.reject("LEG_SPREAD_TOO_WIDE",
                            f"{p.leg.option_type} {p.leg.strike:.0f} spread "
                            f"{p.spread_pct:.1%} > {limits.max_leg_spread_pct:.1%}")

    # ── 8. economics, in points, before any sizing ───────────────────────────
    net_credit = sum((-p.leg.qty_sign) * p.fill for p in legs)
    cost_pts = sum(abs(p.fill - p.price) for p in legs)
    v.net_credit_pts = round(net_credit, 2)
    v.modelled_cost_pts = round(cost_pts, 3)
    ml = max_loss_points(raw_legs, net_credit)
    if ml == float("inf"):
        return v.reject("UNDEFINED_RISK", "max loss is unbounded")
    v.max_loss_pts = round(ml, 2)

    # The edge test the directive insists on: an expected move that does not clear
    # the modelled friction is not a trade, however good the setup looked.
    #
    # A DEBIT structure must be judged on the move available over the ACTUAL holding
    # period, not over whatever horizon the estimate happened to be measured on. This
    # caught a real false positive: `options_vol_setup` reports the DAILY ATR (~250
    # points) as the expected move, and against a 94-point straddle that looked like
    # +30 points of edge — but `max_hold_minutes` was 120, so the position could only
    # ever see a fraction of a daily range. 47 of 66 replay trades were approved this
    # way and the strategy lost Rs 132,496.
    #
    # Moves scale with the square root of time, so the estimate is scaled by
    # sqrt(hold / horizon) and never scaled UP.
    hold = max(1.0, float(decision.max_hold_minutes or 0) or 1.0)
    horizon = max(1.0, float(getattr(decision, "expected_move_horizon_minutes", 0) or 0))
    scale = min(1.0, (hold / horizon) ** 0.5) if horizon > 0 else 0.0
    move_over_hold = float(decision.expected_move_points) * scale
    v.notes.append(f"expected move {decision.expected_move_points:.1f} pts over "
                   f"{horizon:.0f}min scaled to {move_over_hold:.1f} pts over the "
                   f"{hold:.0f}min hold (x{scale:.2f})")
    if is_credit(s):
        edge = net_credit - cost_pts
    else:
        edge = move_over_hold * 0.5 - abs(net_credit) - cost_pts
    v.expected_edge_pts = round(edge, 2)
    if edge <= limits.min_expected_edge_pts:
        return v.reject("NO_EDGE_AFTER_COST",
                        f"expected edge {edge:.2f} pts <= "
                        f"{limits.min_expected_edge_pts:.2f} after modelled friction")

    # ── 9. direction sanity ──────────────────────────────────────────────────
    want = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0}[decision.direction]
    got = structure_direction(s)
    if want != 0 and got != 0 and want != got:
        return v.reject("DIRECTION_MISMATCH",
                        f"{decision.direction} stated but {s} is direction {got:+d}")

    # ── 10. portfolio state ──────────────────────────────────────────────────
    if open_positions >= limits.max_open_positions:
        return v.reject("MAX_OPEN_POSITIONS",
                        f"{open_positions} open, limit {limits.max_open_positions}")
    if trades_today >= limits.max_trades_per_day:
        return v.reject("MAX_TRADES_PER_DAY",
                        f"{trades_today} today, limit {limits.max_trades_per_day}")
    if equity <= 0:
        return v.reject("NO_EQUITY", f"equity {equity}")
    if daily_pnl < 0 and abs(daily_pnl) / equity >= limits.daily_loss_limit_pct:
        return v.reject("DAILY_LOSS_LIMIT",
                        f"down {abs(daily_pnl):.0f} = "
                        f"{abs(daily_pnl)/equity:.1%} >= {limits.daily_loss_limit_pct:.1%}")

    # ── 11. the shared account-level engine has the last word on limits ──────
    if risk_engine is not None:
        try:
            if not risk_engine.can_trade(equity):
                st = risk_engine.get_state_summary()
                return v.reject("RISK_ENGINE_BLOCK", f"engine refuses: {st}")
        except Exception as e:                                 # noqa: BLE001
            return v.reject("RISK_ENGINE_ERROR",
                            f"engine unavailable ({type(e).__name__}); refusing to "
                            f"trade with unknown risk state")

    # ── 12. sizing — computed HERE, never supplied by the model ──────────────
    risk_per_lot = ml * lot_size
    if risk_per_lot <= 0:
        return v.reject("ZERO_RISK_PER_LOT", "max loss per lot computed as zero")
    budget = equity * limits.risk_per_trade_pct
    lots_by_risk = int(budget // risk_per_lot)

    deploy_per_lot = (risk_per_lot if is_credit(s) else abs(net_credit) * lot_size)
    if deploy_per_lot <= 0:
        deploy_per_lot = risk_per_lot
    lots_by_capital = int((equity * limits.max_deployed_pct) // deploy_per_lot)

    lots = max(0, min(lots_by_risk, lots_by_capital, limits.max_lots))
    if lots < 1:
        return v.reject("CAPITAL_INSUFFICIENT",
                        f"one lot risks Rs {risk_per_lot:,.0f} and deploys "
                        f"Rs {deploy_per_lot:,.0f}; at Rs {equity:,.0f} equity the "
                        f"{limits.risk_per_trade_pct:.1%} risk budget allows "
                        f"{lots_by_risk} lots and the "
                        f"{limits.max_deployed_pct:.0%} deployment cap allows "
                        f"{lots_by_capital}")

    v.lots = lots
    v.capital_at_risk = round(risk_per_lot * lots, 2)
    v.margin_or_debit = round(deploy_per_lot * lots, 2)
    v.notes.append(f"{lots} lot(s); risk Rs {v.capital_at_risk:,.0f} "
                   f"({v.capital_at_risk/equity:.2%} of equity); "
                   f"deployed Rs {v.margin_or_debit:,.0f}")
    return v
