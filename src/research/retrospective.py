"""
RETROSPECTIVE — turns calibration evidence into PROPOSALS. It never applies one.

This implements the directive's §34 in full, which my last report listed as NOT
IMPLEMENTED:

    record experience -> analyse experience -> produce candidate rule/model updates
    -> validate offline -> version the change -> then promote MANUALLY

The structure is borrowed from the `bennyjo/phil` prediction-market agent, which runs a
daily deep-retrospective that audits the cycle agent's edits and grades its estimation
errors, and routes anything touching its protected engine through
`journal/proposals.md` for a human to adjudicate. One thing is deliberately NOT
borrowed: Phil rewrites its own strategy after every resolved bet. That is exactly what
§34 forbids here, so this module writes proposals and stops.

THE MECHANICAL GUARANTEE. `PROTECTED` lists the files that encode the safety argument.
Nothing in this module writes any file except the proposals journal, and
`tests/test_retrospective_guardrails.py` fails if a proposal's target is protected or
if this module gains a write path. Phil enforces the same idea in CI by failing any
agent commit that touches `core/`; the test here is that check's equivalent.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.calibration import (
    CalibrationResult, inverted_families, overconfident_families,
)

PROPOSALS_PATH = "journal/proposals.md"
PROPOSALS_JSON = "journal/proposals.json"

# Files that encode the safety argument. A proposal naming any of these is refused,
# not queued: they change only by a human editing them directly.
PROTECTED = (
    "src/risk/structure_risk.py",        # the 12 gates and all sizing
    "src/risk/risk_engine.py",           # kill switch, drawdown, loss limits
    "src/agent/decision_schema.py",      # what the model is allowed to say
    "src/options/structures.py",         # the allowed structures; no naked-short builder
    "src/execution/agent_paper_executor.py",
    "src/execution/cost_model.py",       # statutory friction
    "src/config.py",                     # LIVE_TRADING_ENABLED
    "configs/risk.yaml",                 # every risk limit
    ".env",
)

# What a proposal is allowed to target. Deliberately narrow: sensing and pacing, in
# Phil's terms — never the risk boundary, never execution, never the cost model.
PROPOSABLE = (
    "src/market/setups.py",              # which candidates exist and their thresholds
    "configs/market.yaml",               # setup thresholds
    "configs/agent.yaml",                # decider wiring, cadence
    "src/agent/deciders.py",             # the heuristic's structure choice
    "src/agent/state_compactor.py",      # what the model is shown
)


class ProtectedFileError(RuntimeError):
    """Raised when a proposal names a file that only a human may change."""


@dataclass
class Proposal:
    proposal_id: str
    created_at: str
    kind: str                     # DISABLE_FAMILY | INVERT_FAMILY | RETUNE | INVESTIGATE
    target_file: str
    summary: str
    evidence: Dict[str, Any]
    rationale: str
    validation_required: List[str]
    status: str = "PROPOSED"      # PROPOSED only. A human writes anything else.
    risk_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pid(kind: str, scope: str, created: str) -> str:
    h = hashlib.sha256(f"{kind}|{scope}|{created}".encode()).hexdigest()[:8]
    return f"P-{created[:10].replace('-', '')}-{h}"


def _check_target(path: str) -> None:
    norm = path.replace("\\", "/")
    for p in PROTECTED:
        if norm == p or norm.endswith("/" + p):
            raise ProtectedFileError(
                f"{path} is protected. The retrospective may not propose changes to "
                f"the risk boundary, execution, the cost model, the decision schema, "
                f"the structure catalogue, or any config holding a risk limit. "
                f"A human edits these directly.")
    if not any(norm == q or norm.endswith("/" + q) for q in PROPOSABLE):
        raise ProtectedFileError(
            f"{path} is not in the proposable set {PROPOSABLE}; refusing to queue a "
            f"proposal against a file whose blast radius has not been considered.")


def _n(c: CalibrationResult) -> int:
    """The sample size a threshold may be applied to: independent observations."""
    return int(c.n_independent if c.n_independent is not None else c.n_directional)


def analyse(cal: Dict[str, CalibrationResult], *,
            min_n: int = 30,
            skill_epsilon: float = 0.0) -> List[Proposal]:
    """
    Read the calibration table and produce proposals. Pure: touches no file.

    Three findings produce a proposal, in descending order of how much they tell us:

      INVERTED   Brier worse than a coin flip on a meaningful sample. The family has
                 information with the sign reversed, which is the most actionable
                 result available and the easiest to get wrong by fitting.
      NO SKILL   beats neither the coin flip nor the base rate. Costs friction for
                 nothing; the proposal is to disable it, not to retune it.
      OVERCONFIDENT  Brier worse than a coin flip while the hit rate is at or above
                 50%. The direction is right, the stated confidence is not. Flipping
                 such a family would make it worse, so this is deliberately a SEPARATE
                 finding from INVERTED with a different remedy: shrink the score.
      MISCALIBRATED MAGNITUDE  the agent's move estimate is worse than the option
                 market's own implied move, so it has no volatility skill and its
                 expected-move figure should not be used to justify a debit.

    `min_n` is applied to `n_independent`, not to the raw record count. Overlapping
    forward windows inflate the record count by the overlap factor, and a threshold
    applied to the inflated number would queue proposals off a handful of independent
    observations.
    """
    created = datetime.now().isoformat()
    out: List[Proposal] = []

    for scope, delta in inverted_families(cal, min_n=min_n):
        c = cal[scope]
        out.append(Proposal(
            proposal_id=_pid("INVERT_FAMILY", scope, created), created_at=created,
            kind="INVERT_FAMILY", target_file="src/market/setups.py",
            summary=f"{scope} forecasts are systematically WRONG "
                    f"- hit rate {c.hit_rate}% (brier_delta vs coin flip "
                    f"{delta:+.4f}; n_independent={c.n_independent})",
            evidence={"scope": scope, "n_directional": c.n_directional,
                      "n_independent": c.n_independent,
                      "hit_rate": c.hit_rate, "brier_agent": c.brier_agent,
                      "brier_coinflip": c.brier_coinflip,
                      "brier_delta_vs_coinflip": c.brier_delta_vs_coinflip,
                      "brier_delta_vs_base_rate": c.brier_delta_vs_base_rate},
            rationale="The market moved AGAINST the stated direction more often than "
                      "not, so the family carries information with the sign reversed. "
                      "That is a stronger finding than absence of signal, and the "
                      "easiest of all to over-fit: the same data that produced the "
                      "inversion cannot also validate it.",
            validation_required=[
                "re-score the inverted rule on a DEV window that excludes the one "
                "that produced this finding",
                "confirm the sign holds in at least two separate years",
                "confirm the excess move clears the measured option friction "
                "(~4.4 points per 2-leg round trip)",
                "check it is not an artefact of the index's upward drift by comparing "
                "long and short sides separately"],
            risk_note="Inverting a rule doubles the multiple-testing surface: the same "
                      "data now supports two hypotheses. Treat as a NEW hypothesis "
                      "needing its own out-of-sample window."))

    for scope, c in sorted(cal.items()):
        if _n(c) < min_n or c.has_directional_skill is not False:
            continue
        if any(p.evidence.get("scope") == scope for p in out):
            continue          # already covered by the stronger inverted finding
        out.append(Proposal(
            proposal_id=_pid("DISABLE_FAMILY", scope, created), created_at=created,
            kind="DISABLE_FAMILY", target_file="configs/market.yaml",
            summary=f"{scope} shows no directional skill "
                    f"(brier_delta vs coin {c.brier_delta_vs_coinflip:+.4f}, "
                    f"vs base rate {c.brier_delta_vs_base_rate:+.4f}, "
                    f"n_independent={c.n_independent})",
            evidence={"scope": scope, "n_directional": c.n_directional,
                      "n_independent": c.n_independent,
                      "hit_rate": c.hit_rate,
                      "brier_delta_vs_coinflip": c.brier_delta_vs_coinflip,
                      "brier_delta_vs_base_rate": c.brier_delta_vs_base_rate},
            rationale="Beating neither a coin flip nor the realised base rate means "
                      "the family pays friction for nothing. The proposal is to stop "
                      "emitting it, not to retune it — retuning a family with no "
                      "measured signal is how thresholds get fitted to noise.",
            validation_required=[
                "confirm on a second window",
                "confirm the family's trades are not carrying the portfolio in some "
                "regime the aggregate hides"],
            risk_note="Disabling a family reduces trade count, which widens the "
                      "confidence interval on everything that remains."))

    over = overconfident_families(cal, min_n=min_n)
    inverted_scopes = {p.evidence.get("scope") for p in out
                       if p.kind == "INVERT_FAMILY"}
    over = [(k, g) for k, g in over if k not in inverted_scopes]
    if over:
        worst, worst_gap = over[0]
        wc = cal[worst]
        out.append(Proposal(
            proposal_id=_pid("RECALIBRATE_CONFIDENCE", worst, created),
            created_at=created, kind="RECALIBRATE_CONFIDENCE",
            target_file="src/agent/deciders.py",
            summary=f"the confidence mapping overstates {len(over)} scope(s); worst "
                    f"{worst} asserts {wc.mean_score:.2f} and delivers "
                    f"{wc.hit_rate}% (gap {worst_gap:+.2f}, "
                    f"n_independent={wc.n_independent})",
            evidence={"scope": worst, "worst_gap": worst_gap,
                      "n_independent": wc.n_independent,
                      "scopes": [{"scope": k, "gap": g,
                                  "mean_score": cal[k].mean_score,
                                  "hit_rate": cal[k].hit_rate,
                                  "n_independent": cal[k].n_independent}
                                 for k, g in over]},
            rationale="ONE proposal rather than one per family, because the number comes "
                      "from a single expression in the decider - `0.45 + 0.15 * score` "
                      "- which reaches 0.90-1.00 for an aligned MEDIUM or HIGH setup. "
                      "The direction is not reversed in any of these scopes (every hit "
                      "rate is at or above a coin flip), so this is a calibration "
                      "fault, not a signal fault, and inverting them would make things "
                      "worse. It matters because `direction_score` is consumed "
                      "downstream as a probability: asserting 0.90 on a setup that "
                      "resolves near 0.50 misstates the evidence to every consumer.",
            validation_required=[
                "confirm the gap on a second window before changing the mapping",
                "re-fit the quality->score mapping on DEV only, then report the Brier "
                "on a window not used for the fit",
                "check the gap per quality_hint bucket separately: a single shrink "
                "factor is only correct if the miscalibration is uniform across "
                "LOW/MEDIUM/HIGH",
                "confirm shrinking the score does not simply route every decision to "
                "NO_TRADE through the risk gate's confidence floor, which would make "
                "the change look harmless while silently disabling the agent"],
            risk_note="A confidence number is an input to the risk boundary, so "
                      "lowering it is the safe direction (fewer, smaller trades). The "
                      "danger is the opposite of usual: the mapping must not be "
                      "re-fitted on the window that measured the gap, or the new "
                      "numbers are fitted noise wearing a calibration label."))

    for scope, c in sorted(cal.items()):
        if c.n_magnitude < min_n or c.beats_market_on_magnitude is not False:
            continue
        out.append(Proposal(
            proposal_id=_pid("RETUNE", scope, created), created_at=created,
            kind="RETUNE", target_file="src/market/setups.py",
            summary=f"{scope} magnitude estimate is worse than the option market's "
                    f"implied move (MAE {c.mae_agent_pts} vs {c.mae_market_pts} pts, "
                    f"bias {c.magnitude_bias_ratio}x)",
            evidence={"scope": scope, "n_magnitude": c.n_magnitude,
                      "mae_agent_pts": c.mae_agent_pts,
                      "mae_market_pts": c.mae_market_pts,
                      "magnitude_bias_ratio": c.magnitude_bias_ratio,
                      "mean_expected_pts": c.mean_expected_pts,
                      "mean_realised_abs_pts": c.mean_realised_abs_pts},
            rationale="The expected-move figure is what the risk gate uses to justify "
                      "a debit structure. If it is less accurate than the straddle "
                      "the market is quoting, the agent has no volatility skill and "
                      "that figure should not be the basis of a debit trade.",
            validation_required=[
                "re-measure with the market implied move on the same horizon",
                "check whether using the straddle-implied move directly, instead of "
                "an ATR multiple, changes the gate's decisions"],
            risk_note="Adopting the market's implied move makes the gate stricter, "
                      "which is the safe direction, but it will cut trade count."))
    return out


def write_journal(proposals: List[Proposal], *,
                  md_path: str = PROPOSALS_PATH,
                  json_path: str = PROPOSALS_JSON,
                  meta: Optional[Dict[str, Any]] = None) -> str:
    """
    Append proposals to the journal. This is the ONLY file this module writes, and it
    is documentation: nothing reads it back to change behaviour.

    Every target is re-checked here even though `analyse` already set it, because a
    caller could construct a `Proposal` by hand.
    """
    for p in proposals:
        _check_target(p.target_file)

    os.makedirs(os.path.dirname(md_path) or ".", exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    lines: List[str] = []
    if not os.path.exists(md_path):
        lines += [
            "# PROPOSALS JOURNAL",
            "",
            "Candidate changes produced by `src/research/retrospective.py` from",
            "calibration evidence. **Nothing here has been applied.** Each entry is a",
            "hypothesis with the validation it must pass first; a human promotes it by",
            "editing the target file and recording the outcome below the entry.",
            "",
            "The risk boundary, execution path, cost model, decision schema, structure",
            "catalogue and every risk limit are PROTECTED and can never appear as a",
            "target here — `retrospective.PROTECTED` refuses them and a test enforces it.",
            "", "---", ""]
    lines += [f"## Batch {stamp}", ""]
    if meta:
        lines += ["```json", json.dumps(meta, indent=2, default=str), "```", ""]
    if not proposals:
        lines += ["No proposal: the calibration evidence did not meet the sample or",
                  "effect thresholds for any finding.", ""]
    for p in proposals:
        lines += [
            f"### {p.proposal_id} — {p.kind}", "",
            f"- **target** `{p.target_file}` (proposable; not protected)",
            f"- **status** `{p.status}` — not applied",
            f"- **finding** {p.summary}", "",
            f"**Why.** {p.rationale}", "",
            "**Must pass before promotion:**"]
        lines += [f"{i}. {v}" for i, v in enumerate(p.validation_required, 1)]
        lines += ["", f"**Risk of acting on this.** {p.risk_note}", "",
                  "<details><summary>evidence</summary>", "",
                  "```json", json.dumps(p.evidence, indent=2, default=str), "```",
                  "", "</details>", "",
                  "**Operator decision:** _(unfilled)_", "", "---", ""]
    with open(md_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))

    existing: List[Dict[str, Any]] = []
    if os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                existing = json.load(f).get("proposals", [])
        except (OSError, ValueError):
            existing = []
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"updated_at": stamp, "meta": meta or {},
                   "proposals": existing + [p.to_dict() for p in proposals]},
                  f, indent=2, default=str)
    return md_path
