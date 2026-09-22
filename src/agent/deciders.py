"""
Deciders — the pluggable seam where "AI" lives.

Two implementations, one interface:

  HeuristicDecider  deterministic, zero LLM calls. This is the BASELINE the AI must
                    beat, and it is what every replay, test and benchmark runs on by
                    default. Having a real, non-trivial deterministic decider is what
                    makes the claim "the AI adds value" falsifiable at all.

  LLMDecider        calls a model with the compact brief, caches by state_hash, and
                    degrades to NO_TRADE on any failure. It never sees bars.

Both return an `AgentDecision`. Neither can size a position or touch a risk limit —
that happens afterwards in `src/risk/structure_risk.py`.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from src.agent.decision_schema import (
    NO_TRADE, AgentDecision, ValidationResult, parse_and_validate,
)
from src.agent.state_compactor import PROMPT_VERSION, compact, state_hash
from src.market.market_state import MarketState
from src.market.setups import CandidateSetup


@dataclass
class DecisionRecord:
    """Everything needed to reproduce or audit one decision."""
    state_hash: str
    decision: AgentDecision
    source: str                 # "heuristic" | "llm" | "cache" | "invalid"
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    errors: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    raw: str = ""


class Decider(Protocol):
    name: str

    def decide(self, st: MarketState, candidates: List[CandidateSetup],
               options_note: Optional[str] = None,
               position_note: Optional[str] = None) -> DecisionRecord: ...


# ════════════════════════════════════════════════════════════════════════════
# Heuristic baseline
# ════════════════════════════════════════════════════════════════════════════

class HeuristicDecider:
    """
    A competent, explainable rule-set standing in for the model.

    It encodes the reasoning the directive describes — multiple independent
    confirmations, trend vs range, breakout vs failed breakout, volume, time of day —
    and nothing else. It is intentionally NOT tuned: it exists to be a fair baseline
    and to let the whole pipeline run without a model.

    Structure choice follows the expected move and the regime:
      strong directional + decent move  -> debit vertical (defined risk, cheaper theta)
      weaker directional                -> credit vertical on the opposite side
      non-directional, vol looks cheap  -> long straddle
      anything unclear                  -> HOLD
    """

    name = "heuristic-v1"

    def __init__(self, min_score: int = 2, min_move_pts: float = 15.0):
        self.min_score = int(min_score)
        self.min_move_pts = float(min_move_pts)

    def decide(self, st: MarketState, candidates: List[CandidateSetup],
               options_note: Optional[str] = None,
               position_note: Optional[str] = None) -> DecisionRecord:
        h = state_hash(st, candidates)
        if not candidates:
            return DecisionRecord(h, NO_TRADE, "heuristic")

        best = max(candidates, key=lambda c: (
            {"HIGH": 3, "MEDIUM": 2, "LOW": 1}[c.quality_hint],
            c.expected_move_pts or 0.0))
        em = float(best.expected_move_pts or 0.0)
        if em < self.min_move_pts:
            return DecisionRecord(h, NO_TRADE, "heuristic")

        score = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}[best.quality_hint]
        aligned = ((best.direction > 0 and st.htf_alignment >= 1)
                   or (best.direction < 0 and st.htf_alignment <= -1))
        if aligned:
            score += 1
        if score < self.min_score:
            return DecisionRecord(h, NO_TRADE, "heuristic")

        if best.direction == 0:
            structure = ("LONG_STRADDLE" if best.kind in
                         ("VOLATILITY_EXPANSION", "OPTIONS_VOL_CHEAP") else "NONE")
            direction = "NEUTRAL"
        elif best.direction > 0:
            structure = "BULL_CALL_SPREAD" if score >= 3 else "BULL_PUT_SPREAD"
            direction = "BULLISH"
        else:
            structure = "BEAR_PUT_SPREAD" if score >= 3 else "BEAR_CALL_SPREAD"
            direction = "BEARISH"

        if structure == "NONE":
            return DecisionRecord(h, NO_TRADE, "heuristic")

        prim = st.views.get(st.primary_tf)
        atr = (prim.atr14 if prim and prim.atr14 else em)
        dec = AgentDecision(
            action=("BUY" if best.direction >= 0 else "SELL"),
            decision="EXECUTE", underlying=st.symbol, direction=direction,
            structure=structure,
            setup_quality=best.quality_hint,
            direction_score=round(min(1.0, 0.45 + 0.15 * score), 3),
            expected_move_points=round(em, 1),
            estimated_horizon_minutes=60,
            max_hold_minutes=min(120, max(30, st.minutes_to_close)),
            stop_type="UNDERLYING_STRUCTURE",
            stop_value=round(float(atr) * 1.2, 1),
            take_profit_type="R_MULTIPLE", take_profit_value=1.8,
            invalidation_conditions=[
                f"5m close back through {best.level:.0f}" if best.level else
                "structure invalidated",
                "volume collapse", "regime flips",
            ],
            reason_codes=list(best.reason_codes)[:8],
            rationale=f"{best.kind} score={score}",
        )
        return DecisionRecord(h, dec, "heuristic")


# ════════════════════════════════════════════════════════════════════════════
# LLM decider
# ════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a disciplined Indian index-options trader.

You are given a pre-computed market brief. Every number in it was calculated for
you. Do NOT recompute indicators, do not invent data, and do not ask for more.

Judge whether the detected candidate setup is worth trading AFTER costs. "No trade"
is a correct and common answer — a poor setup skipped is a good decision.

Think about, in this order: is the market tradable now; what regime; what the higher
timeframes say; what the decision timeframe says; structure; activity; volatility;
whether the expected move is large enough to pay the spread and statutory costs;
where the idea is invalidated.

You may ONLY choose from these structures:
LONG_CALL, LONG_PUT, BULL_CALL_SPREAD, BEAR_PUT_SPREAD, BULL_PUT_SPREAD,
BEAR_CALL_SPREAD, IRON_FLY, IRON_CONDOR, LONG_STRADDLE, LONG_STRANGLE, NONE.

Naked short options are forbidden and will be rejected.

You do NOT decide position size, margin, or how much to risk. A deterministic risk
engine does that after you. Do not mention size.

Reply with ONE JSON object and nothing else:

{"action":"BUY|SELL|HOLD|EXIT|REDUCE|TRAIL","decision":"EXECUTE|SKIP",
 "underlying":"NIFTY","direction":"BULLISH|BEARISH|NEUTRAL",
 "structure":"<one of the allowed>","setup_quality":"LOW|MEDIUM|HIGH",
 "direction_score":0.0,"expected_move_points":0,"estimated_horizon_minutes":0,
 "max_hold_minutes":0,
 "stop_loss":{"type":"UNDERLYING_STRUCTURE|R_MULTIPLE|PREMIUM_PCT","value":0},
 "take_profit":{"type":"R_MULTIPLE|POINTS","value":0},
 "invalidation_conditions":["..."],"reason_codes":["..."],"rationale":"one sentence"}
"""


class LLMDecider:
    """
    Model-backed decider with a hard cache and a safe failure mode.

    `call_model` is injected so this class stays testable and provider-agnostic; the
    caller supplies something that takes (system, user) and returns text. On ANY
    problem — exception, unparseable text, schema violation — the result is
    NO_TRADE with the errors recorded. A broken model can cost opportunity here; it
    can never cost money.
    """

    name = "llm"

    def __init__(self, call_model: Callable[[str, str], str], model: str = "unknown",
                 cache: Optional[Dict[str, DecisionRecord]] = None,
                 max_calls: Optional[int] = None):
        self.call_model = call_model
        self.model = model
        self.cache: Dict[str, DecisionRecord] = cache if cache is not None else {}
        self.max_calls = max_calls
        self.calls = 0
        self.cache_hits = 0
        self.invalid = 0

    def decide(self, st: MarketState, candidates: List[CandidateSetup],
               options_note: Optional[str] = None,
               position_note: Optional[str] = None) -> DecisionRecord:
        h = state_hash(st, candidates)
        if h in self.cache:
            self.cache_hits += 1
            c = self.cache[h]
            return DecisionRecord(h, c.decision, "cache", c.model, c.prompt_version,
                                  c.errors, 0.0, c.raw)
        if not candidates:
            return DecisionRecord(h, NO_TRADE, "heuristic")
        if self.max_calls is not None and self.calls >= self.max_calls:
            return DecisionRecord(h, NO_TRADE, "budget_exhausted",
                                  errors=["LLM call budget reached"])

        brief = compact(st, candidates, options_note, position_note)
        t0 = time.time()
        try:
            raw = self.call_model(SYSTEM_PROMPT, brief)
        except Exception as e:                                  # noqa: BLE001
            self.invalid += 1
            return DecisionRecord(h, NO_TRADE, "invalid", self.model,
                                  errors=[f"model call failed: {type(e).__name__}: {e}"],
                                  latency_ms=(time.time() - t0) * 1000)
        self.calls += 1
        lat = (time.time() - t0) * 1000
        res: ValidationResult = parse_and_validate(raw, st.symbol)
        if not res.ok or res.decision is None:
            self.invalid += 1
            rec = DecisionRecord(h, NO_TRADE, "invalid", self.model, PROMPT_VERSION,
                                 res.errors, lat, raw[:2000])
        else:
            rec = DecisionRecord(h, res.decision, "llm", self.model, PROMPT_VERSION,
                                 [], lat, raw[:2000])
        self.cache[h] = rec
        return rec

    def stats(self) -> Dict[str, Any]:
        total = self.calls + self.cache_hits
        return {"model": self.model, "calls": self.calls, "cache_hits": self.cache_hits,
                "invalid": self.invalid,
                "cache_hit_rate": round(self.cache_hits / total * 100, 1) if total else 0.0}
