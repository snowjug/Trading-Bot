"""
Multi-leg paper execution engine.

A local simulated broker. It never talks to a broker mutation endpoint; the only
external data it consumes is read-only market data supplied by the caller.

WHAT IT GUARANTEES
  * A position is opened ONLY from an executable two-sided quote. A missing,
    stale, zero, inverted or absurdly wide quote is refused and the reason is
    recorded — there is no LTP fallback and no assumed price.
  * BUY fills at the ASK plus slippage, SELL fills at the BID minus slippage.
    Never the mid, never the last traded price.
  * Every leg carries its own real identity: security id, trading symbol, strike,
    expiry, option type, side, quantity, and the bid/ask it was filled against.
  * Marking uses the side a position would actually be CLOSED at: a long leg marks
    at the bid, a short leg at the ask. That is deliberately the conservative side.
  * Costs come from IndianCostModel, charged per leg, on entry and on exit.
  * PAPER and SHADOW ledgers are separate objects and are never merged.

WHAT IT DOES NOT DO
  * It does not invent an exit. If no executable quote exists at square-off time
    the position is marked UNRESOLVED and left open with a null realised P&L,
    rather than being closed at a fabricated price.
"""

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel
from src.utils.logging import setup_logging

logger = setup_logging("execution.paper_engine")

# Quote acceptance limits. A quote failing any of these is not executable.
MAX_QUOTE_AGE_SEC = 30.0
MAX_SPREAD_PCT = 0.06          # 6% of mid; wider than this is not a real market
DEFAULT_SLIPPAGE = 0.50        # points, charged against the trader on both sides
TICK_SIZE = 0.05               # NSE option tick


@dataclass
class LegSpec:
    """What the strategy asked for, before any quote was seen."""
    role: str                  # e.g. short_call, long_put, leg
    option_type: str           # CE | PE
    side: str                  # BUY | SELL
    strike_offset: int = 0     # strikes from ATM; ignored when `strike` is given
    strike: Optional[float] = None


@dataclass
class PaperLeg:
    """One filled leg. Every field here came from a real contract and a real quote."""
    role: str
    security_id: str
    trading_symbol: str
    custom_symbol: str
    strike: float
    expiry: str
    option_type: str
    side: str
    qty: int
    entry_bid: float
    entry_ask: float
    entry_fill: float
    slippage: float
    entry_costs: float
    current_bid: Optional[float] = None
    current_ask: Optional[float] = None
    current_mark: Optional[float] = None
    exit_bid: Optional[float] = None
    exit_ask: Optional[float] = None
    exit_fill: Optional[float] = None
    exit_costs: float = 0.0

    @property
    def direction(self) -> float:
        return 1.0 if self.side == "BUY" else -1.0

    def mark_price(self, bid: Optional[float], ask: Optional[float]) -> Optional[float]:
        """
        The price this leg could actually be CLOSED at.

        A long leg is closed by selling into the bid; a short leg by buying at the
        ask. Marking at the mid would flatter every open position by half a spread.
        """
        return bid if self.side == "BUY" else ask

    def unrealized(self) -> Optional[float]:
        if self.current_mark is None:
            return None
        return self.direction * (self.current_mark - self.entry_fill) * self.qty

    def realized(self) -> Optional[float]:
        if self.exit_fill is None:
            return None
        return self.direction * (self.exit_fill - self.entry_fill) * self.qty


@dataclass
class PaperPosition:
    """A whole structure: one leg for a directional trade, four for a condor."""
    position_id: str
    bot: str
    strategy: str
    underlying: str
    entry_time: str
    entry_spot: float
    legs: List[PaperLeg] = field(default_factory=list)
    ledger: str = "PAPER"                 # PAPER | SHADOW — never mixed
    status: str = "OPEN"                  # OPEN | CLOSED | UNRESOLVED
    exit_time: Optional[str] = None
    exit_spot: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None
    unrealized_pnl: float = 0.0
    mae: float = 0.0                      # most adverse excursion, rupees
    mfe: float = 0.0                      # most favourable excursion, rupees
    peak_unrealized: float = 0.0          # for trailing logic
    target_pnl: Optional[float] = None
    stop_pnl: Optional[float] = None
    trail_trigger: Optional[float] = None
    trail_giveback: Optional[float] = None
    flat_by: Optional[str] = None         # "HH:MM" hard square-off
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def entry_costs(self) -> float:
        return sum(l.entry_costs for l in self.legs)

    @property
    def exit_costs(self) -> float:
        return sum(l.exit_costs for l in self.legs)

    @property
    def total_costs(self) -> float:
        return self.entry_costs + self.exit_costs

    @property
    def net_credit_points(self) -> float:
        """Positive when the structure was opened for a credit."""
        return sum((-l.direction) * l.entry_fill for l in self.legs)

    def holding_seconds(self, now: Optional[datetime] = None) -> float:
        try:
            t0 = datetime.strptime(self.entry_time, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return 0.0
        end = now or datetime.now()
        if self.exit_time:
            try:
                end = datetime.strptime(self.exit_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        return max(0.0, (end - t0).total_seconds())

    def to_row(self) -> Dict[str, Any]:
        """Flat record for the ledger, with every field the audit trail needs."""
        return {
            "position_id": self.position_id, "ledger": self.ledger,
            "bot": self.bot, "strategy": self.strategy, "underlying": self.underlying,
            "entry_time": self.entry_time, "exit_time": self.exit_time,
            "entry_spot": self.entry_spot, "exit_spot": self.exit_spot,
            "status": self.status, "exit_reason": self.exit_reason,
            "realized_pnl": self.realized_pnl, "unrealized_pnl": self.unrealized_pnl,
            "entry_costs": round(self.entry_costs, 2),
            "exit_costs": round(self.exit_costs, 2),
            "total_costs": round(self.total_costs, 2),
            "mae": round(self.mae, 2), "mfe": round(self.mfe, 2),
            "holding_seconds": round(self.holding_seconds(), 1),
            "net_credit_points": round(self.net_credit_points, 2),
            "legs": [asdict(l) for l in self.legs],
            "meta": self.meta,
        }


# ─────────────────────────── QUOTE ACCEPTANCE ───────────────────────────

def quote_age_seconds(quote_timestamp: Optional[str], now: Optional[datetime] = None
                      ) -> Optional[float]:
    """Age of an exchange timestamp, or None when it cannot be parsed."""
    if not quote_timestamp:
        return None
    now = now or datetime.now()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return (now - datetime.strptime(str(quote_timestamp), fmt)).total_seconds()
        except ValueError:
            continue
    return None


def validate_quote(bid: Optional[float], ask: Optional[float],
                   quote_timestamp: Optional[str], side: str,
                   max_age: float = MAX_QUOTE_AGE_SEC,
                   max_spread_pct: float = MAX_SPREAD_PCT) -> tuple:
    """
    (ok, reason). The single gate every fill passes through.

    Refuses rather than degrades: there is no LTP fallback, because an LTP is a
    record of someone else's past trade, not a price available to us now.
    """
    need = ask if side == "BUY" else bid
    if need is None or float(need) <= 0:
        return False, f"NO_EXECUTABLE_{'ASK' if side == 'BUY' else 'BID'}"
    if bid is None or ask is None or float(bid) <= 0 or float(ask) <= 0:
        return False, "INCOMPLETE_TWO_SIDED_QUOTE"
    bid, ask = float(bid), float(ask)
    if ask < bid:
        return False, f"INVERTED_BOOK bid={bid} ask={ask}"
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return False, "ZERO_MID"
    # Spread acceptance is percentage-based WITH a tick floor. On a 2-rupee option a
    # single 0.05 tick is 2.5% and two ticks is 5%, so a pure percentage cap would
    # reject perfectly normal far-OTM markets for being cheap rather than for being
    # illiquid. The floor is three ticks; anything wider than both tests is refused.
    spread = ask - bid
    spread_pct = spread / mid
    if spread_pct > max_spread_pct and spread > 3 * TICK_SIZE:
        return False, f"SPREAD_TOO_WIDE {spread_pct:.2%} ({spread:.2f})"
    age = quote_age_seconds(quote_timestamp)
    if age is None:
        return False, "NO_QUOTE_TIMESTAMP"
    if age > max_age:
        return False, f"STALE_QUOTE age={age:.1f}s"
    if age < -60:
        return False, f"QUOTE_TIMESTAMP_IN_FUTURE age={age:.1f}s"
    return True, "OK"


def fill_price(bid: float, ask: float, side: str, slippage: float = DEFAULT_SLIPPAGE) -> float:
    """BUY pays the ask plus slippage; SELL receives the bid minus it."""
    return round(float(ask) + slippage, 2) if side == "BUY" else round(
        max(0.05, float(bid) - slippage), 2)


# ─────────────────────────────── BROKER ───────────────────────────────

class PaperBroker:
    """
    Local simulated broker. Holds positions, marks them, closes them, keeps ledgers.

    PAPER and SHADOW are separate dictionaries and separate files. A shadow
    position can never be counted in paper P&L.
    """

    def __init__(self, session_dir: str = "data/paper_session",
                 slippage: float = DEFAULT_SLIPPAGE):
        self.slippage = slippage
        self.open_positions: Dict[str, List[PaperPosition]] = {"PAPER": [], "SHADOW": []}
        self.closed_positions: Dict[str, List[PaperPosition]] = {"PAPER": [], "SHADOW": []}
        self.rejections: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self._seq = 0
        self.dir = Path(session_dir) / datetime.now().strftime("%Y-%m-%d")
        self.dir.mkdir(parents=True, exist_ok=True)

    # ── bookkeeping ──
    def _next_id(self, bot: str) -> str:
        self._seq += 1
        return f"{bot.replace(' ', '')}-{datetime.now().strftime('%H%M%S')}-{self._seq}"

    def record_rejection(self, bot: str, reason: str, detail: Optional[Dict] = None) -> None:
        self.rejections.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot": bot, "reason": reason, **(detail or {}),
        })

    def record_error(self, bot: str, error: str) -> None:
        self.errors.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot": bot, "error": error,
        })
        logger.error(f"{bot}: {error}")

    # ── entry ──
    def open_position(self, bot: str, strategy: str, underlying: str, spot: float,
                      contracts: List[Dict[str, Any]], ledger: str = "PAPER",
                      target_pnl: Optional[float] = None, stop_pnl: Optional[float] = None,
                      trail_trigger: Optional[float] = None,
                      trail_giveback: Optional[float] = None,
                      flat_by: Optional[str] = None,
                      meta: Optional[Dict] = None) -> Optional[PaperPosition]:
        """
        Fills every leg or none of them.

        A structure is a single decision: filling three legs of a condor and
        refusing the fourth would leave naked risk that the strategy never chose.
        """
        legs: List[PaperLeg] = []
        for c in contracts:
            side = c["side"]
            ok, why = validate_quote(c.get("bid"), c.get("ask"),
                                     c.get("quote_timestamp"), side)
            if not ok:
                self.record_rejection(bot, f"LEG_QUOTE_REJECTED:{why}", {
                    "role": c.get("role"), "security_id": c.get("security_id"),
                    "bid": c.get("bid"), "ask": c.get("ask"),
                })
                return None
            qty = int(c.get("lot_size") or 0)
            if qty <= 0:
                self.record_rejection(bot, "NO_LOT_SIZE", {"role": c.get("role")})
                return None
            px = fill_price(float(c["bid"]), float(c["ask"]), side, self.slippage)
            legs.append(PaperLeg(
                role=c.get("role", "leg"), security_id=str(c["security_id"]),
                trading_symbol=str(c.get("trading_symbol", "")),
                custom_symbol=str(c.get("custom_symbol", "")),
                strike=float(c.get("strike") or 0.0), expiry=str(c.get("expiry") or ""),
                option_type=str(c.get("option_type", "")), side=side, qty=qty,
                entry_bid=float(c["bid"]), entry_ask=float(c["ask"]),
                entry_fill=px, slippage=self.slippage,
                entry_costs=IndianCostModel.calculate_roundtrip_costs(px, px, qty).total_costs / 2.0,
                current_bid=float(c["bid"]), current_ask=float(c["ask"]),
                current_mark=px,
            ))

        pos = PaperPosition(
            position_id=self._next_id(bot), bot=bot, strategy=strategy,
            underlying=underlying,
            entry_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            entry_spot=float(spot), legs=legs, ledger=ledger,
            target_pnl=target_pnl, stop_pnl=stop_pnl,
            trail_trigger=trail_trigger, trail_giveback=trail_giveback,
            flat_by=flat_by, meta=meta or {},
        )
        self.open_positions[ledger].append(pos)
        logger.info(f"{ledger} ENTRY {bot}: {len(legs)} leg(s) "
                    + ", ".join(f"{l.side} {l.custom_symbol} @ {l.entry_fill}" for l in legs))
        return pos

    # ── marking ──
    def mark_position(self, pos: PaperPosition, quotes: Dict[str, Dict[str, Any]],
                      spot: Optional[float] = None) -> Optional[float]:
        """
        Updates unrealised P&L, MAE and MFE from live quotes.

        Returns None when any leg has no usable quote, so the caller knows the
        position is UNMARKABLE rather than flat.
        """
        total = 0.0
        for leg in pos.legs:
            q = quotes.get(str(leg.security_id))
            if not q:
                return None
            bid, ask = q.get("bid"), q.get("ask")
            if bid is None or ask is None or float(bid) <= 0 or float(ask) <= 0:
                return None
            leg.current_bid, leg.current_ask = float(bid), float(ask)
            leg.current_mark = leg.mark_price(leg.current_bid, leg.current_ask)
            u = leg.unrealized()
            if u is None:
                return None
            total += u
        # Exit costs are already committed by the decision to be in the position.
        net = total - pos.total_costs
        # All four are rounded the same way: MAE/MFE are compared against
        # unrealized_pnl by callers and tests, and mixing rounded with unrounded
        # values makes "the excursion is at least the current P&L" fail by a
        # fraction of a paisa.
        net = round(net, 2)
        pos.unrealized_pnl = net
        pos.mae = round(min(pos.mae, net), 2)
        pos.mfe = round(max(pos.mfe, net), 2)
        pos.peak_unrealized = round(max(pos.peak_unrealized, net), 2)
        if spot:
            pos.meta["last_spot"] = float(spot)
        return pos.unrealized_pnl

    def exit_signal(self, pos: PaperPosition, now_hhmm: str) -> Optional[str]:
        """Which exit rule, if any, fires right now. Pure function of recorded state."""
        u = pos.unrealized_pnl
        if pos.stop_pnl is not None and u <= pos.stop_pnl:
            return "STOP"
        if pos.target_pnl is not None and u >= pos.target_pnl:
            return "TARGET"
        if (pos.trail_trigger is not None and pos.trail_giveback is not None
                and pos.peak_unrealized >= pos.trail_trigger
                and u <= pos.peak_unrealized - pos.trail_giveback):
            return "TRAIL"
        if pos.flat_by and now_hhmm >= pos.flat_by:
            return "EOD_FLAT"
        return None

    # ── exit ──
    def close_position(self, pos: PaperPosition, quotes: Dict[str, Dict[str, Any]],
                       reason: str, spot: Optional[float] = None) -> bool:
        """
        Closes at executable prices, or refuses and marks the position UNRESOLVED.

        A square-off that cannot be priced is NOT a fill. Reporting one would be
        fabricating the single number the whole ledger exists to measure.
        """
        fills: List[tuple] = []
        for leg in pos.legs:
            q = quotes.get(str(leg.security_id))
            if not q:
                self._unresolve(pos, f"{reason}_UNRESOLVED_NO_QUOTE")
                return False
            close_side = "SELL" if leg.side == "BUY" else "BUY"
            ok, why = validate_quote(q.get("bid"), q.get("ask"),
                                     q.get("quote_timestamp"), close_side)
            if not ok:
                self._unresolve(pos, f"{reason}_UNRESOLVED_{why}")
                return False
            fills.append((leg, float(q["bid"]), float(q["ask"]), close_side))

        realized = 0.0
        for leg, bid, ask, close_side in fills:
            px = fill_price(bid, ask, close_side, self.slippage)
            leg.exit_bid, leg.exit_ask, leg.exit_fill = bid, ask, px
            leg.exit_costs = IndianCostModel.calculate_roundtrip_costs(
                leg.entry_fill, px, leg.qty).total_costs / 2.0
            realized += leg.realized() or 0.0

        pos.realized_pnl = round(realized - pos.total_costs, 2)
        pos.unrealized_pnl = 0.0
        pos.exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pos.exit_spot = float(spot) if spot else None
        pos.exit_reason = reason
        pos.status = "CLOSED"
        self.open_positions[pos.ledger].remove(pos)
        self.closed_positions[pos.ledger].append(pos)
        logger.info(f"{pos.ledger} EXIT {pos.bot} [{reason}]: "
                    f"realized Rs {pos.realized_pnl:,.2f} after Rs {pos.total_costs:,.2f} costs")
        return True

    def _unresolve(self, pos: PaperPosition, reason: str) -> None:
        """No executable quote: stay open, realise nothing, say so."""
        pos.status = "UNRESOLVED"
        pos.exit_reason = reason
        pos.realized_pnl = None
        self.record_error(pos.bot, f"{reason} on {pos.position_id}")
        logger.warning(f"{pos.bot}: {reason} — position left OPEN with null realised P&L")

    # ── reporting ──
    def summary(self, ledger: str = "PAPER") -> Dict[str, Any]:
        closed = self.closed_positions[ledger]
        openp = self.open_positions[ledger]
        realized = sum(p.realized_pnl or 0.0 for p in closed)
        unreal = sum(p.unrealized_pnl for p in openp)
        costs = sum(p.total_costs for p in closed + openp)
        eq, peak, dd = 0.0, 0.0, 0.0
        for p in closed:
            eq += p.realized_pnl or 0.0
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        return {
            "ledger": ledger,
            "total_positions": len(closed) + len(openp),
            "open_positions": len(openp),
            "closed_positions": len(closed),
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unreal, 2),
            "total_costs": round(costs, 2),
            "max_drawdown": round(abs(dd), 2),
            "wins": sum(1 for p in closed if (p.realized_pnl or 0) > 0),
            "losses": sum(1 for p in closed if (p.realized_pnl or 0) <= 0),
            "unresolved": sum(1 for p in closed + openp if p.status == "UNRESOLVED"),
        }

    def persist(self) -> Path:
        """Writes both ledgers, kept strictly apart, plus rejections and errors."""
        payload = {
            "written_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "slippage_points": self.slippage,
            "PAPER": {
                "summary": self.summary("PAPER"),
                "open": [p.to_row() for p in self.open_positions["PAPER"]],
                "closed": [p.to_row() for p in self.closed_positions["PAPER"]],
            },
            "SHADOW": {
                "summary": self.summary("SHADOW"),
                "open": [p.to_row() for p in self.open_positions["SHADOW"]],
                "closed": [p.to_row() for p in self.closed_positions["SHADOW"]],
            },
            "rejections": self.rejections[-500:],
            "errors": self.errors[-200:],
        }
        path = self.dir / "paper_ledger.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path
