"""
The AI's output contract.

The model returns ONE JSON object and nothing else. This module parses it, validates
it, and — critically — makes an invalid or ambitious response harmless.

Design rule that matters more than any other here: **there is no field the model can
set that relaxes a risk limit.** No override, no force, no size, no margin, no
"confidence" that buys leniency. The model proposes a direction and a structure; how
many lots (if any) is computed later by `src/risk/structure_risk.py` from the account
and the limits. The schema is small on purpose — every field is something the model
is actually qualified to say.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ACTIONS = {"BUY", "SELL", "HOLD", "EXIT", "REDUCE", "TRAIL"}
DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
QUALITIES = {"LOW", "MEDIUM", "HIGH"}
DECISIONS = {"EXECUTE", "SKIP"}

# Structures the agent is allowed to name. Naked short volatility is deliberately
# absent: an autonomous agent does not get to sell undefined risk.
ALLOWED_STRUCTURES = {
    "LONG_CALL", "LONG_PUT",
    "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD",
    "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD",
    "IRON_FLY", "IRON_CONDOR",
    "LONG_STRADDLE", "LONG_STRANGLE",
    "NONE",
}
BANNED_STRUCTURES = {"SHORT_STRADDLE", "SHORT_STRANGLE", "NAKED_CALL", "NAKED_PUT"}


@dataclass(frozen=True)
class AgentDecision:
    action: str
    decision: str                       # EXECUTE | SKIP
    underlying: str
    direction: str
    structure: str
    setup_quality: str
    direction_score: float              # 0..1, NOT treated as calibrated
    expected_move_points: float
    estimated_horizon_minutes: int
    max_hold_minutes: int
    stop_type: str                      # UNDERLYING_STRUCTURE | R_MULTIPLE | PREMIUM_PCT
    stop_value: float
    take_profit_type: str
    take_profit_value: float
    invalidation_conditions: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def wants_entry(self) -> bool:
        return self.decision == "EXECUTE" and self.action in ("BUY", "SELL")


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    decision: Optional[AgentDecision]
    errors: List[str]

    @property
    def tradable(self) -> bool:
        return bool(self.ok and self.decision and self.decision.wants_entry)


NO_TRADE = AgentDecision(
    action="HOLD", decision="SKIP", underlying="", direction="NEUTRAL",
    structure="NONE", setup_quality="LOW", direction_score=0.0,
    expected_move_points=0.0, estimated_horizon_minutes=0, max_hold_minutes=0,
    stop_type="R_MULTIPLE", stop_value=0.0, take_profit_type="R_MULTIPLE",
    take_profit_value=0.0, invalidation_conditions=[], reason_codes=["NO_TRADE"],
    rationale="default no-trade",
)


def extract_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Pull one JSON object out of a model response.

    Models wrap JSON in prose or fences more often than not, so this is tolerant
    about the envelope and strict about the content. It never repairs the JSON
    itself — a malformed object is an error, not something to guess at.
    """
    if text is None:
        return None, "empty response"
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if fence:
        t = fence.group(1)
    else:
        i, j = t.find("{"), t.rfind("}")
        if i == -1 or j == -1 or j <= i:
            return None, "no JSON object found in response"
        t = t[i:j + 1]
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    if not isinstance(obj, dict):
        return None, "top-level JSON is not an object"
    return obj, None


def _num(d: dict, key: str, default: float, lo: float, hi: float,
         errs: List[str]) -> float:
    v = d.get(key, default)
    try:
        f = float(v)
    except (TypeError, ValueError):
        errs.append(f"{key}: not a number ({v!r})")
        return default
    if not (lo <= f <= hi):
        errs.append(f"{key}: {f} outside [{lo}, {hi}]")
        return max(lo, min(hi, f))
    return f


def validate(obj: Optional[dict], expected_underlying: Optional[str] = None
             ) -> ValidationResult:
    """
    Turn a parsed object into an `AgentDecision`, or refuse.

    A refusal is never an exception and never a trade: the caller receives
    `ok=False` and must fall back to NO_TRADE. Anything the model gets wrong —
    missing field, unknown structure, impossible number, a banned structure, the
    wrong underlying — lands here.
    """
    errs: List[str] = []
    if obj is None:
        return ValidationResult(False, None, ["no object to validate"])

    action = str(obj.get("action", "")).upper().strip()
    if action not in ACTIONS:
        errs.append(f"action: {action!r} not in {sorted(ACTIONS)}")
    decision = str(obj.get("decision", "SKIP")).upper().strip()
    if decision not in DECISIONS:
        errs.append(f"decision: {decision!r} not in {sorted(DECISIONS)}")
    direction = str(obj.get("direction", "NEUTRAL")).upper().strip()
    if direction not in DIRECTIONS:
        errs.append(f"direction: {direction!r} not in {sorted(DIRECTIONS)}")
    structure = str(obj.get("structure", "NONE")).upper().strip()
    if structure in BANNED_STRUCTURES:
        errs.append(f"structure: {structure} is banned for autonomous trading "
                    f"(undefined risk)")
    elif structure not in ALLOWED_STRUCTURES:
        errs.append(f"structure: {structure!r} not in the allowed set")
    quality = str(obj.get("setup_quality", "LOW")).upper().strip()
    if quality not in QUALITIES:
        errs.append(f"setup_quality: {quality!r} not in {sorted(QUALITIES)}")

    underlying = str(obj.get("underlying", "") or "").upper().strip()
    if expected_underlying and underlying and underlying != expected_underlying.upper():
        errs.append(f"underlying: model said {underlying!r}, state is "
                    f"{expected_underlying!r}")

    ds = _num(obj, "direction_score", 0.0, 0.0, 1.0, errs)
    em = _num(obj, "expected_move_points", 0.0, 0.0, 5000.0, errs)
    hz = int(_num(obj, "estimated_horizon_minutes", 0, 0, 3000, errs))
    mh = int(_num(obj, "max_hold_minutes", 0, 0, 3000, errs))

    sl = obj.get("stop_loss") or {}
    tp = obj.get("take_profit") or {}
    st_type = str(sl.get("type", "R_MULTIPLE")).upper().strip()
    tp_type = str(tp.get("type", "R_MULTIPLE")).upper().strip()
    st_val = _num(sl, "value", 0.0, 0.0, 100000.0, errs)
    tp_val = _num(tp, "value", 0.0, 0.0, 100000.0, errs)

    inval = obj.get("invalidation_conditions") or []
    codes = obj.get("reason_codes") or []
    if not isinstance(inval, list):
        errs.append("invalidation_conditions: not a list"); inval = []
    if not isinstance(codes, list):
        errs.append("reason_codes: not a list"); codes = []

    # An EXECUTE must be complete. This is where "the model was vague" becomes
    # "no trade" rather than "trade with defaults".
    if decision == "EXECUTE" and action in ("BUY", "SELL"):
        if structure in ("NONE", ""):
            errs.append("EXECUTE without a structure")
        if em <= 0:
            errs.append("EXECUTE without a positive expected_move_points")
        if st_val <= 0:
            errs.append("EXECUTE without a stop_loss value")
        if mh <= 0:
            errs.append("EXECUTE without max_hold_minutes")
        if direction == "NEUTRAL" and structure in (
                "LONG_CALL", "LONG_PUT", "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD",
                "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"):
            errs.append(f"directional structure {structure} with NEUTRAL direction")

    if errs:
        return ValidationResult(False, None, errs)

    return ValidationResult(True, AgentDecision(
        action=action, decision=decision,
        underlying=(underlying or (expected_underlying or "")),
        direction=direction, structure=structure, setup_quality=quality,
        direction_score=ds, expected_move_points=em,
        estimated_horizon_minutes=hz, max_hold_minutes=mh,
        stop_type=st_type, stop_value=st_val,
        take_profit_type=tp_type, take_profit_value=tp_val,
        invalidation_conditions=[str(x) for x in inval][:10],
        reason_codes=[str(x) for x in codes][:12],
        rationale=str(obj.get("rationale", ""))[:400],
    ), [])


def parse_and_validate(text: str, expected_underlying: Optional[str] = None
                       ) -> ValidationResult:
    obj, err = extract_json(text)
    if err:
        return ValidationResult(False, None, [err])
    return validate(obj, expected_underlying)
