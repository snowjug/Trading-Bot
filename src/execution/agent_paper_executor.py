"""
Paper executor for the agent. ONE execution path, shared with replay.

The parity claim in the architecture doc rests on this file being the only place an
agent order is constructed, in both REPLAY and PAPER. It therefore does as little as
possible of its own: it takes an already-approved `RiskVerdict`, builds the order
record, journals it, and tracks the position through the same deterministic exits the
replay engine uses.

Three refusals are hard-coded and unconditional:

  1. `LIVE_TRADING_ENABLED` true      -> refuse to do anything at all
  2. a verdict that is not approved   -> refuse, and raise, because arriving here
                                         with a rejected verdict is a control-flow bug
                                         and must be loud
  3. a leg count that does not match  -> refuse; a partially resolvable structure is
     what the decision asked for         not the structure

No Dhan order endpoint is imported, called or referenced. A sandbox executor, if one
is ever added, must sit behind the same `place` signature so that this file remains
the only order-construction site.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.agent.decision_schema import AgentDecision
from src.agent.trading_agent import OpenPosition, hard_exit_reason
from src.execution.cost_model import IndianCostModel
from src.risk.structure_risk import PricedLeg, RiskVerdict


class LiveTradingRefused(RuntimeError):
    """Raised if anything tries to execute while live trading is enabled."""


class UnapprovedOrderRefused(RuntimeError):
    """Raised if an order is attempted without an approved risk verdict."""


@dataclass
class PaperOrder:
    client_order_id: str
    strategy_id: str
    decision_id: str
    timestamp: datetime
    underlying: str
    structure: str
    legs: List[Dict[str, Any]]
    lots: int
    lot_size: int
    mode: str = "PAPER"
    status: str = "FILLED"          # paper fills are immediate and total, by definition
    reject_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class PaperFill:
    order_id: str
    leg_index: int
    option_type: str
    side: str
    strike: float
    quantity: int
    fill_price: float
    reference_price: float


@dataclass
class ExecutionState:
    """Everything the operator and the journal need, and nothing secret."""
    equity: float
    open_position: Optional[OpenPosition] = None
    open_order: Optional[PaperOrder] = None
    trades_today: int = 0
    daily_pnl: float = 0.0
    realised_pnl: float = 0.0
    session_date: Optional[Any] = None
    orders: List[PaperOrder] = field(default_factory=list)
    fills: List[PaperFill] = field(default_factory=list)
    journal: List[Dict[str, Any]] = field(default_factory=list)

    def roll_session(self, d: Any) -> None:
        if self.session_date != d:
            self.session_date = d
            self.trades_today = 0
            self.daily_pnl = 0.0


class AgentPaperExecutor:
    """
    Simulated execution with real accounting. No broker call of any kind.

    `strategy_id` and `prompt_version` are recorded on every order so a trade can
    always be traced back to the exact decision that produced it.
    """

    def __init__(self, equity: float, *, strategy_id: str = "AGENT_V1",
                 prompt_version: str = "agent-brief-v1",
                 live_trading_enabled: bool = False,
                 journal_path: Optional[str] = None,
                 session_exit: dtime = dtime(15, 15)):
        if live_trading_enabled:
            raise LiveTradingRefused(
                "AgentPaperExecutor refuses to construct while LIVE_TRADING_ENABLED "
                "is true; live execution is not implemented and must not be inferred")
        self.state = ExecutionState(equity=float(equity))
        self.strategy_id = strategy_id
        self.prompt_version = prompt_version
        self.journal_path = journal_path
        self.session_exit = session_exit

    # ── entry ────────────────────────────────────────────────────────────────
    def place(self, decision: AgentDecision, verdict: RiskVerdict,
              legs: List[PricedLeg], *, now: datetime, lot_size: int,
              spot: float, state_hash: str = "",
              live_trading_enabled: bool = False) -> PaperOrder:
        if live_trading_enabled:
            raise LiveTradingRefused("refusing to place an order in live mode")
        if not verdict.approved or verdict.lots < 1:
            raise UnapprovedOrderRefused(
                f"place() reached with an unapproved verdict "
                f"(gate={verdict.gate_failed!r}, lots={verdict.lots}); this is a "
                f"control-flow bug, not a trading decision")
        if self.state.open_position is not None:
            raise UnapprovedOrderRefused("a position is already open")

        self.state.roll_session(now.date())
        oid = f"AG-{uuid.uuid4().hex[:12]}"
        leg_records: List[Dict[str, Any]] = []
        for i, p in enumerate(legs):
            qty = verdict.lots * lot_size * p.leg.qty_sign
            leg_records.append({
                "leg_index": i, "role": p.leg.role,
                "option_type": p.leg.option_type, "side": p.leg.side,
                "strike": p.leg.strike, "quantity": qty,
                "reference_price": p.price, "fill_price": p.fill,
                "volume_at_entry": p.volume, "spread_pct": p.spread_pct})
            self.state.fills.append(PaperFill(
                oid, i, p.leg.option_type, p.leg.side, p.leg.strike, qty,
                p.fill, p.price))

        order = PaperOrder(
            client_order_id=oid, strategy_id=self.strategy_id,
            decision_id=(state_hash or uuid.uuid4().hex[:12]), timestamp=now,
            underlying=decision.underlying, structure=decision.structure,
            legs=leg_records, lots=verdict.lots, lot_size=int(lot_size))
        self.state.orders.append(order)
        self.state.open_order = order

        self.state.open_position = OpenPosition(
            entry_time=now, structure=decision.structure, legs=legs,
            lots=verdict.lots, lot_size=int(lot_size),
            entry_credit_pts=verdict.net_credit_pts,
            max_loss_pts=verdict.max_loss_pts,
            stop_pts=float(decision.stop_value or 0.0),
            stop_type=decision.stop_type, entry_spot=float(spot),
            target_pts=0.0,
            max_hold_minutes=int(decision.max_hold_minutes or 120),
            decision=decision, session_exit=self.session_exit)
        stop_prem = self.state.open_position.stop_in_premium_pts(spot)
        self.state.open_position.target_pts = (
            float(stop_prem) * float(decision.take_profit_value or 0.0)
            if stop_prem else 0.0)

        self.state.trades_today += 1
        self._journal("ENTRY", now, {
            "order_id": oid, "structure": decision.structure,
            "direction": decision.direction, "lots": verdict.lots,
            "lot_size": lot_size, "credit_pts": verdict.net_credit_pts,
            "max_loss_pts": verdict.max_loss_pts,
            "capital_at_risk": verdict.capital_at_risk,
            "edge_pts": verdict.expected_edge_pts,
            "reason_codes": decision.reason_codes,
            "decision_id": order.decision_id,
            "prompt_version": self.prompt_version,
            "risk_notes": verdict.notes})
        return order

    # ── management ───────────────────────────────────────────────────────────
    def check_exit(self, now: datetime, mark_pts: Optional[float],
                   spot: Optional[float]) -> Optional[str]:
        """The deterministic exit check. The model is not consulted here."""
        pos = self.state.open_position
        if pos is None:
            return None
        return hard_exit_reason(pos, now, mark_pts, spot)

    def close(self, now: datetime, mark_pts: Optional[float], exit_prices: List[float],
              reason: str, cost_mult: float = 1.0) -> Dict[str, Any]:
        """
        Close the open position at an authentic mark, or record it as unresolved.

        An unmarkable position is NOT closed at an invented price. It is recorded,
        the position is released, and the P&L is left absent with a reason — which is
        the only honest option and keeps the failure visible in the journal.
        """
        pos = self.state.open_position
        if pos is None:
            return {"closed": False, "reason": "no open position"}

        if mark_pts is None:
            rec = {"closed": True, "resolved": False, "reason": reason,
                   "unresolved_reason": "NO_MARK_AT_EXIT", "net_rupees": None}
            self._journal("EXIT_UNRESOLVED", now, rec)
            self.state.open_position, self.state.open_order = None, None
            return rec

        cost_pts = 0.0
        for p, xp in zip(pos.legs, exit_prices):
            cost_pts += IndianCostModel.calculate_roundtrip_costs(
                p.fill, max(0.0, xp), int(pos.lot_size)).total_costs / max(pos.lot_size, 1)
        cost_pts *= cost_mult
        gross_pts = pos.premium_pnl_pts(mark_pts)
        net_pts = gross_pts - cost_pts
        net_rupees = net_pts * pos.lot_size * pos.lots

        self.state.realised_pnl += net_rupees
        self.state.daily_pnl += net_rupees
        self.state.equity += net_rupees

        rec = {"closed": True, "resolved": True, "reason": reason,
               "held_minutes": round(pos.minutes_held(now), 1),
               "entry_credit_pts": pos.entry_credit_pts,
               "exit_value_pts": round(mark_pts, 2),
               "gross_pts": round(gross_pts, 2), "cost_pts": round(cost_pts, 3),
               "net_pts": round(net_pts, 2), "net_rupees": round(net_rupees, 2),
               "equity_after": round(self.state.equity, 2)}
        self._journal("EXIT", now, rec)
        self.state.open_position, self.state.open_order = None, None
        return rec

    # ── journal ──────────────────────────────────────────────────────────────
    def _journal(self, event: str, ts: datetime, payload: Dict[str, Any]) -> None:
        row = {"event": event, "ts": ts.isoformat(), "strategy_id": self.strategy_id,
               "mode": "PAPER", **payload}
        self.state.journal.append(row)
        if self.journal_path:
            os.makedirs(os.path.dirname(self.journal_path) or ".", exist_ok=True)
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")

    def summary(self) -> Dict[str, Any]:
        return {"mode": "PAPER", "strategy_id": self.strategy_id,
                "equity": round(self.state.equity, 2),
                "realised_pnl": round(self.state.realised_pnl, 2),
                "daily_pnl": round(self.state.daily_pnl, 2),
                "trades_today": self.state.trades_today,
                "orders": len(self.state.orders),
                "position_open": self.state.open_position is not None}
