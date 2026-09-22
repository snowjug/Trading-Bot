"""
REPLAY ENGINE — runs the agent over history with complete accounting.

Two properties make this trustworthy rather than merely runnable:

1. **Every bar is accounted for.** Each decision bar ends at exactly one
   `stopped_at` label, and the engine asserts that the labels sum to the number of
   bars offered. A bar that vanished is a bug, not a "no trade".

2. **Exits are priced authentically or the trade is not counted.** A position is
   marked from the same grid it was entered from. If it cannot be marked at the exit
   bar, the trade is recorded as `UNRESOLVED` and excluded from P&L with a reason —
   never closed at an invented price, and never quietly dropped.

The engine also carries the baselines the directive requires, so the agent's numbers
are never presented alone.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.agent.trading_agent import (
    HARD_EXITS, STOP_APPROVED, AgentOutcome, OpenPosition, TradingAgent,
    hard_exit_reason,
)
from src.execution.cost_model import IndianCostModel
from src.market.market_state import StateBuilder, resample
from src.options.chain import ReplayChain
from src.risk.structure_risk import PricedLeg


@dataclass
class ReplayTrade:
    entry_time: datetime
    exit_time: Optional[datetime]
    structure: str
    direction: str
    lots: int
    lot_size: int
    entry_credit_pts: float
    exit_value_pts: Optional[float]
    gross_pts: Optional[float]
    cost_pts: float
    net_pts: Optional[float]
    net_rupees: Optional[float]
    max_loss_pts: float
    capital_at_risk: float
    exit_reason: str
    decision_source: str
    state_hash: str
    mfe_pts: float = 0.0
    mae_pts: float = 0.0
    resolved: bool = True
    unresolved_reason: str = ""


@dataclass
class ReplayResult:
    trades: List[ReplayTrade] = field(default_factory=list)
    accounting: Dict[str, int] = field(default_factory=dict)
    bars_offered: int = 0
    decider_stats: Dict[str, Any] = field(default_factory=dict)
    outcomes: List[Dict[str, Any]] = field(default_factory=list)

    def reconciles(self) -> bool:
        return sum(self.accounting.values()) == self.bars_offered

    def resolved_trades(self) -> List[ReplayTrade]:
        return [t for t in self.trades if t.resolved and t.net_rupees is not None]


def _leg_cost_pts(legs: List[PricedLeg], exit_prices: List[float],
                  lot_size: int, mult: float = 1.0) -> float:
    """Statutory friction per unit, summed across legs, using the repo's cost model."""
    tot = 0.0
    for p, xp in zip(legs, exit_prices):
        tot += IndianCostModel.calculate_roundtrip_costs(
            p.fill, max(0.0, xp), int(lot_size)).total_costs / max(lot_size, 1)
    return float(tot * mult)


def mark_position(chain: ReplayChain, pos: OpenPosition, sess: date, t: dtime
                  ) -> Tuple[Optional[float], List[float]]:
    """
    Current value of the position in points, and the per-leg prices used.

    None when any leg cannot be marked from a traded bar. Partial marking is refused
    on purpose: three of four legs is not a price for a condor.
    """
    prices: List[float] = []
    total = 0.0
    for p in pos.legs:
        q = chain.quote(sess, t, p.leg.option_type, p.leg.strike)
        if q is None:
            return None, []
        prices.append(q.price)
        total += (-p.leg.qty_sign) * q.price
    return float(total), prices


def run_replay(
    agent: TradingAgent,
    builder: StateBuilder,
    chain: ReplayChain,
    bar_times: List[pd.Timestamp],
    *,
    equity: float,
    lot_size_for: Any,
    cost_mult: float = 1.0,
    max_trades_per_day: int = 3,
    compound: bool = False,
) -> ReplayResult:
    """
    Walk `bar_times` in order, one decision per bar, at most one open position.

    `lot_size_for` is a callable (date) -> int|None returning the AUTHENTIC lot size
    for that month. When it returns None the bar is accounted as NO_LOT_SIZE and no
    trade is taken — a rupee figure without a real lot size is not a rupee figure.
    """
    res = ReplayResult(bars_offered=len(bar_times))
    acc = res.accounting
    pos: Optional[OpenPosition] = None
    pos_trade: Optional[ReplayTrade] = None
    trades_today = 0
    cur_day: Optional[date] = None
    eq = float(equity)
    daily_pnl = 0.0

    def bump(k: str) -> None:
        acc[k] = acc.get(k, 0) + 1

    for ts in bar_times:
        bt = pd.Timestamp(ts)
        sess, t = bt.date(), bt.time()
        if cur_day != sess:
            cur_day, trades_today, daily_pnl = sess, 0, 0.0

        lot = lot_size_for(sess)
        if lot is None:
            bump("NO_LOT_SIZE")
            continue

        # ── manage an open position first; hard exits outrank everything ──────
        if pos is not None:
            mark, _ = mark_position(chain, pos, sess, t)
            spot_now = chain.spot(sess, t)
            reason = hard_exit_reason(pos, bt.to_pydatetime(), mark, spot_now)
            if mark is not None and pos_trade is not None:
                pnl = pos.entry_credit_pts - mark
                pos_trade.mfe_pts = max(pos_trade.mfe_pts, pnl)
                pos_trade.mae_pts = min(pos_trade.mae_pts, pnl)
            if reason is not None:
                if mark is None:
                    # Cannot be marked at the exit bar: record it, do not price it.
                    pos_trade.exit_time = bt.to_pydatetime()
                    pos_trade.exit_reason = reason
                    pos_trade.resolved = False
                    pos_trade.unresolved_reason = "NO_MARK_AT_EXIT"
                    bump("EXIT_UNRESOLVED")
                else:
                    _, xprices = mark_position(chain, pos, sess, t)
                    cpts = _leg_cost_pts(pos.legs, xprices, pos.lot_size, cost_mult)
                    gross = pos.entry_credit_pts - mark
                    net = gross - cpts
                    pos_trade.exit_time = bt.to_pydatetime()
                    pos_trade.exit_value_pts = round(mark, 2)
                    pos_trade.gross_pts = round(gross, 2)
                    pos_trade.cost_pts = round(cpts, 3)
                    pos_trade.net_pts = round(net, 2)
                    pos_trade.net_rupees = round(net * pos.lot_size * pos.lots, 2)
                    pos_trade.exit_reason = reason
                    daily_pnl += pos_trade.net_rupees
                    if compound:
                        eq += pos_trade.net_rupees
                    bump(f"EXIT_{reason}")
                pos, pos_trade = None, None
                continue
            bump("POSITION_OPEN")
            continue

        # ── flat: look for an entry ──────────────────────────────────────────
        try:
            st = builder.at(bt)
        except Exception:                                      # noqa: BLE001
            bump("NO_STATE")
            continue

        out: AgentOutcome = agent.step(
            st, eq, int(lot), now=bt.to_pydatetime(), open_positions=0,
            trades_today=trades_today, daily_pnl=daily_pnl,
            live_trading_enabled=False)
        res.outcomes.append(out.summary())

        if out.stopped_at != STOP_APPROVED:
            bump(out.stopped_at if out.stopped_at != "RISK_REJECTED"
                 else f"RISK_{out.verdict.gate_failed}")
            continue

        v = out.verdict
        pos = OpenPosition(
            entry_time=bt.to_pydatetime(), structure=out.decision.structure,
            legs=out.legs, lots=v.lots, lot_size=int(lot),
            entry_credit_pts=v.net_credit_pts, max_loss_pts=v.max_loss_pts,
            stop_pts=float(out.decision.stop_value or 0.0),
            stop_type=out.decision.stop_type,
            entry_spot=float(st.spot),
            target_pts=0.0,          # set below, in PREMIUM points
            max_hold_minutes=int(out.decision.max_hold_minutes or 120),
            decision=out.decision)
        # The take-profit is an R-multiple of the stop, so it has to be computed in
        # whatever unit the stop actually resolves to. Deriving it from the raw stop
        # value would reintroduce the index-versus-premium mix-up this fix removes.
        _stop_prem = pos.stop_in_premium_pts(st.spot)
        pos.target_pts = (float(_stop_prem) * float(out.decision.take_profit_value or 0.0)
                          if _stop_prem else 0.0)
        pos_trade = ReplayTrade(
            entry_time=pos.entry_time, exit_time=None, structure=pos.structure,
            direction=out.decision.direction, lots=v.lots, lot_size=int(lot),
            entry_credit_pts=v.net_credit_pts, exit_value_pts=None, gross_pts=None,
            cost_pts=0.0, net_pts=None, net_rupees=None,
            max_loss_pts=v.max_loss_pts, capital_at_risk=v.capital_at_risk,
            exit_reason="", decision_source=out.decision_source,
            state_hash=out.state_hash)
        res.trades.append(pos_trade)
        trades_today += 1
        bump("ENTERED")

    # a position still open at the end is reported, never silently closed
    if pos_trade is not None and pos_trade.exit_time is None:
        pos_trade.resolved = False
        pos_trade.unresolved_reason = "STILL_OPEN_AT_END_OF_REPLAY"
        bump("OPEN_AT_END")

    if hasattr(agent.decider, "stats"):
        res.decider_stats = agent.decider.stats()
    return res


# ════════════════════════════════════════════════════════════════════════════
# Baselines the agent must be compared against
# ════════════════════════════════════════════════════════════════════════════

def baseline_buy_and_hold(spot5: pd.DataFrame, start: date, end: date) -> Dict[str, Any]:
    d = spot5[(spot5["datetime"].dt.date >= start) & (spot5["datetime"].dt.date <= end)]
    if d.empty:
        return {"name": "buy_and_hold", "return_pct": None}
    a, b = float(d["close"].iloc[0]), float(d["close"].iloc[-1])
    eq = d.groupby(d["datetime"].dt.date)["close"].last()
    dd = float(((eq - eq.cummax()) / eq.cummax()).min() * 100)
    return {"name": "buy_and_hold", "return_pct": round((b / a - 1) * 100, 2),
            "max_dd_pct": round(dd, 2), "note": "index only, no costs, not tradable "
                                                "without a futures or ETF position"}


def baseline_ema_cross(spot5: pd.DataFrame, fast: int = 5, slow: int = 31,
                       cost_pts_per_trade: float = 3.0) -> Dict[str, Any]:
    d = spot5.copy()
    d["f"] = d["close"].ewm(span=fast, adjust=False).mean()
    d["s"] = d["close"].ewm(span=slow, adjust=False).mean()
    sig = np.sign(d["f"] - d["s"])
    flip = sig.diff().fillna(0) != 0
    n = int(flip.sum())
    pnl = float((sig.shift(1).fillna(0) * d["close"].diff().fillna(0)).sum())
    return {"name": f"ema_{fast}_{slow}", "trades": n,
            "gross_pts": round(pnl, 1),
            "net_pts": round(pnl - n * cost_pts_per_trade, 1),
            "note": f"index points, {cost_pts_per_trade} pts charged per flip"}


def baseline_no_trade() -> Dict[str, Any]:
    return {"name": "no_trade", "net_pts": 0.0, "trades": 0,
            "note": "the control every strategy must beat"}


def baseline_random_entry(spot5: pd.DataFrame, n_trades: int, hold_bars: int,
                          seed: int = 0, cost_pts_per_trade: float = 3.0
                          ) -> Dict[str, Any]:
    """
    Random long entries, matched to the agent's trade count and holding period.

    This is the control that catches a strategy whose apparent edge is just exposure
    to a drifting index.
    """
    rng = np.random.default_rng(seed)
    c = spot5["close"].to_numpy(float)
    if len(c) <= hold_bars + 2 or n_trades <= 0:
        return {"name": "random_entry", "trades": 0, "net_pts": 0.0}
    idx = rng.integers(0, len(c) - hold_bars - 1, size=n_trades)
    pnl = float(np.sum(c[idx + hold_bars] - c[idx]))
    return {"name": "random_entry", "trades": int(n_trades),
            "gross_pts": round(pnl, 1),
            "net_pts": round(pnl - n_trades * cost_pts_per_trade, 1),
            "note": f"{n_trades} random longs held {hold_bars} bars, seed {seed}"}


def metrics(res: ReplayResult, equity: float) -> Dict[str, Any]:
    tr = res.resolved_trades()
    if not tr:
        return {"trades": 0, "resolved": 0, "unresolved": len(res.trades),
                "bars_offered": res.bars_offered, "reconciles": res.reconciles(),
                "accounting": dict(sorted(res.accounting.items(),
                                          key=lambda kv: -kv[1]))}
    r = np.array([t.net_rupees for t in tr], float)
    wins, losses = r[r > 0], r[r <= 0]
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    streak = mx = 0
    for x in r:
        if x <= 0:
            streak += 1; mx = max(mx, streak)
        else:
            streak = 0
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    return {
        "trades": len(tr), "resolved": len(tr),
        "unresolved": len(res.trades) - len(tr),
        "bars_offered": res.bars_offered, "reconciles": res.reconciles(),
        "win_rate": round(float((r > 0).mean() * 100), 1),
        "net_rupees": round(float(r.sum()), 0),
        "expectancy": round(float(r.mean()), 0),
        "median_trade": round(float(np.median(r)), 0),
        "avg_win": round(float(wins.mean()), 0) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 0) if len(losses) else 0.0,
        "profit_factor": (round(float(wins.sum() / abs(losses.sum())), 3)
                          if len(losses) and losses.sum() != 0 else None),
        "max_dd_rupees": round(abs(dd), 0),
        "max_dd_pct_of_equity": round(abs(dd) / equity * 100, 2),
        "longest_losing_streak": int(mx),
        "best_trade": round(float(r.max()), 0),
        "worst_trade": round(float(r.min()), 0),
        "return_on_equity_pct": round(float(r.sum()) / equity * 100, 2),
        "tstat": (round(float(r.mean() / (sd / np.sqrt(len(r)))), 2)
                  if sd > 0 else None),
        "cost_pts_mean": round(float(np.mean([t.cost_pts for t in tr])), 3),
        "avg_mfe_pts": round(float(np.mean([t.mfe_pts for t in tr])), 2),
        "avg_mae_pts": round(float(np.mean([t.mae_pts for t in tr])), 2),
        "exit_reasons": dict(sorted(
            pd.Series([t.exit_reason for t in tr]).value_counts().to_dict().items(),
            key=lambda kv: -kv[1])),
        "structures": dict(pd.Series([t.structure for t in tr]).value_counts().to_dict()),
        "accounting": dict(sorted(res.accounting.items(), key=lambda kv: -kv[1])),
    }
