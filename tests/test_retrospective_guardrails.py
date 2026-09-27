"""
Guardrail tests for the calibration -> proposal loop.

The loop's whole safety claim is "it can only propose". These tests are that claim's
enforcement, and they are the local equivalent of the CI check the `bennyjo/phil`
reference uses to fail any agent commit that touches its protected `core/`.
"""

import ast
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research import retrospective as R
from src.research.calibration import (
    CalibrationResult, ForecastRecord, brier, by_family, independent_count,
    implied_move_from_straddle, inverted_families, overconfident_families, score,
)


# ═══════════════ the loop cannot touch anything that matters ═══════════════

@pytest.mark.parametrize("path", list(R.PROTECTED))
def test_every_protected_file_is_refused_as_a_proposal_target(path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = R.Proposal(proposal_id="X", created_at="now", kind="RETUNE", target_file=path,
                   summary="s", evidence={}, rationale="r", validation_required=[])
    with pytest.raises(R.ProtectedFileError):
        R.write_journal([p], md_path="journal/t.md", json_path="journal/t.json")


def test_a_file_outside_the_proposable_set_is_also_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = R.Proposal(proposal_id="X", created_at="now", kind="RETUNE",
                   target_file="src/market/market_state.py", summary="s", evidence={},
                   rationale="r", validation_required=[])
    with pytest.raises(R.ProtectedFileError):
        R.write_journal([p], md_path="journal/t.md", json_path="journal/t.json")


def test_the_risk_boundary_and_live_flag_are_in_the_protected_set():
    for must in ("src/risk/structure_risk.py", "src/risk/risk_engine.py",
                 "src/config.py", "configs/risk.yaml",
                 "src/options/structures.py", "src/agent/decision_schema.py",
                 "src/execution/cost_model.py",
                 "src/execution/agent_paper_executor.py", ".env"):
        assert must in R.PROTECTED, f"{must} must be protected"


def test_protected_and_proposable_sets_do_not_overlap():
    assert not (set(R.PROTECTED) & set(R.PROPOSABLE))


def test_retrospective_writes_no_file_other_than_the_journal():
    """
    Static check on the module's own source: every `open(...)` with a write mode must
    be a journal path. A future edit that adds a write path elsewhere fails here
    rather than in production.
    """
    src = open(R.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    writes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            if any(c in mode for c in ("w", "a", "x", "+")):
                writes.append(ast.unparse(node.args[0]) if node.args else "?")
    assert writes, "expected at least the journal write"
    for w in writes:
        assert ("md_path" in w or "json_path" in w), \
            f"retrospective writes to {w}, which is not the proposals journal"


def test_analyse_is_pure_and_creates_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cal = {"BREAKOUT": CalibrationResult(
        scope="BREAKOUT", n=200, n_directional=200, brier_agent=0.30,
        brier_coinflip=0.25, brier_base_rate=0.24, brier_delta_vs_coinflip=-0.05,
        brier_delta_vs_base_rate=-0.06, has_directional_skill=False)}
    before = set(os.listdir(tmp_path))
    R.analyse(cal)
    assert set(os.listdir(tmp_path)) == before, "analyse() touched the filesystem"


def test_every_proposal_status_is_proposed_and_never_applied():
    cal = {"X": CalibrationResult(
        scope="X", n=100, n_directional=100, brier_agent=0.31, brier_coinflip=0.25,
        brier_delta_vs_coinflip=-0.06, brier_delta_vs_base_rate=-0.07,
        has_directional_skill=False)}
    props = R.analyse(cal)
    assert props
    for p in props:
        assert p.status == "PROPOSED"
        assert p.validation_required, "a proposal with no validation is a change"
        assert p.risk_note


# ═══════════════ calibration correctness ═══════════════

def test_brier_rewards_a_confident_correct_forecast():
    y = np.ones(100)
    assert brier(np.full(100, 0.9), y) < brier(np.full(100, 0.5), y)
    assert brier(np.full(100, 0.1), y) > brier(np.full(100, 0.5), y)


def _recs(n, direction, right_frac, p=0.7, family="F", hold=60, spacing=None):
    """
    Spaced one hold apart by default, so `independent_count` sees every record. A
    fixture packed at bar spacing would be ~12x overlapping and would be gated out by
    the sample-size rule — pass `spacing` explicitly to exercise that.
    """
    out = []
    step = hold if spacing is None else spacing
    for i in range(n):
        right = i < int(n * right_frac)
        move = (12.0 if right else -12.0) * direction
        out.append(ForecastRecord(
            bar_time=pd.Timestamp("2026-01-05 11:00") + pd.Timedelta(minutes=step * i),
            family=family, direction=direction, direction_score=p,
            expected_move_pts=15.0, expected_move_horizon_minutes=5,
            hold_minutes=hold, realised_move_pts=move,
            realised_abs_move_pts=abs(move)))
    return out


def test_a_family_that_is_right_beats_the_coin_flip():
    c = score(_recs(200, 1, 0.75), "good")
    assert c.hit_rate == 75.0
    assert c.brier_delta_vs_coinflip > 0


def test_a_family_that_is_wrong_scores_worse_than_a_coin_flip():
    """The inverted case — the finding a portfolio P&L number hides."""
    c = score(_recs(200, -1, 0.25), "inverted")
    assert c.hit_rate == 25.0
    assert c.brier_delta_vs_coinflip < 0
    assert c.has_directional_skill is False


def test_beating_only_the_coin_flip_is_not_called_skill():
    """
    A family riding the index's drift beats 0.5 but not the realised base rate.
    Calling that skill is how drift gets mistaken for an edge, so both baselines
    must be cleared.
    """
    c = score(_recs(300, 1, 0.62, p=0.62), "drift_rider")
    assert c.brier_delta_vs_coinflip > 0
    assert c.brier_delta_vs_base_rate <= 0
    assert c.has_directional_skill is False


def test_inverted_families_ranks_the_most_wrong_first():
    cal = {"a": score(_recs(100, -1, 0.30), "a"),
           "b": score(_recs(100, -1, 0.10), "b"),
           "c": score(_recs(100, 1, 0.80), "c")}
    inv = inverted_families(cal, min_n=50)
    assert [k for k, _ in inv][:2] == ["b", "a"]
    assert "c" not in dict(inv)


def test_a_small_sample_produces_no_verdict_rather_than_a_weak_one():
    c = score(_recs(8, 1, 1.0), "tiny")
    assert c.has_directional_skill is None and c.brier_agent is None
    assert any("need 10" in n for n in c.notes)


def test_neutral_direction_records_are_excluded_from_the_directional_score():
    recs = _recs(50, 1, 0.8) + [
        ForecastRecord(bar_time=pd.Timestamp("2026-01-05 12:00"), family="F",
                       direction=0, direction_score=0.5, expected_move_pts=10.0,
                       expected_move_horizon_minutes=5, hold_minutes=60,
                       realised_move_pts=5.0, realised_abs_move_pts=5.0)
        for _ in range(20)]
    c = score(recs, "mixed")
    assert c.n == 70 and c.n_directional == 50


def test_magnitude_comparison_is_skipped_when_the_market_move_is_absent():
    c = score(_recs(100, 1, 0.6), "no_market")
    assert c.n_magnitude == 0 and c.beats_market_on_magnitude is None
    assert any("magnitude comparison skipped" in n for n in c.notes)


def test_implied_move_refuses_unusable_inputs_instead_of_guessing():
    assert implied_move_from_straddle(0.0, 100, 60) is None
    assert implied_move_from_straddle(100.0, 0, 60) is None
    assert implied_move_from_straddle(100.0, 100, 0) is None
    assert implied_move_from_straddle(None, 100, 60) is None


def test_implied_move_never_scales_above_the_full_straddle():
    full = implied_move_from_straddle(100.0, 60, 6000)
    assert full == pytest.approx(80.0), "scale must cap at 1.0"
    part = implied_move_from_straddle(100.0, 400, 100)
    assert part < full


def test_by_family_splits_direction_so_an_asymmetric_family_is_visible():
    recs = _recs(60, 1, 0.80, family="VWAP") + _recs(60, -1, 0.20, family="VWAP")
    cal = by_family(recs)
    assert "VWAP" in cal
    assert "VWAP|dir=+1" in cal and "VWAP|dir=-1" in cal
    assert cal["VWAP|dir=+1"].brier_delta_vs_coinflip > 0
    assert cal["VWAP|dir=-1"].brier_delta_vs_coinflip < 0


def test_the_journal_records_that_nothing_was_applied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cal = {"X": score(_recs(100, -1, 0.2), "X")}
    props = R.analyse(cal)
    assert props
    path = R.write_journal(props, md_path="journal/proposals.md",
                           json_path="journal/proposals.json")
    txt = open(path, encoding="utf-8").read()
    assert "Nothing here has been applied" in txt
    assert "not applied" in txt
    assert "PROTECTED" in txt
    assert "Operator decision" in txt


# ═══════════════ the two defects the first real run exposed ═══════════════

def test_an_overconfident_family_is_not_called_inverted():
    """
    The bug the first authentic run produced: BREAKOUT|dir=+1 hit 53.7% while the
    decider asserted 0.90, so its Brier was far worse than a coin flip and the old
    `brier_delta < 0` test proposed INVERTING it. Flipping a rule that is right 53.7%
    of the time makes it worse. Discrimination and calibration are different faults.
    """
    c = score(_recs(200, 1, 0.537, p=0.90), "BREAKOUT|dir=+1")
    assert c.hit_rate >= 50.0
    assert c.brier_delta_vs_coinflip < 0, "overconfidence must still show as bad Brier"
    cal = {"BREAKOUT|dir=+1": c}
    assert inverted_families(cal, min_n=30) == [], "a 53.7% family is not inverted"
    assert [k for k, _ in overconfident_families(cal, min_n=30)] == ["BREAKOUT|dir=+1"]


def test_the_two_faults_produce_different_proposals_with_different_targets():
    cal = {"OVER": score(_recs(200, 1, 0.53, p=0.92), "OVER"),
           "WRONG": score(_recs(200, -1, 0.30, p=0.70), "WRONG")}
    kinds = {p.evidence["scope"]: (p.kind, p.target_file)
             for p in R.analyse(cal) if p.kind in
             ("INVERT_FAMILY", "RECALIBRATE_CONFIDENCE")}
    assert kinds["OVER"] == ("RECALIBRATE_CONFIDENCE", "src/agent/deciders.py")
    assert kinds["WRONG"] == ("INVERT_FAMILY", "src/market/setups.py")


def test_a_family_is_never_both_inverted_and_recalibrated():
    cal = {"W": score(_recs(200, -1, 0.25, p=0.95), "W")}
    props = [p for p in R.analyse(cal) if p.evidence.get("scope") == "W"]
    kinds = {p.kind for p in props}
    assert "INVERT_FAMILY" in kinds
    assert "RECALIBRATE_CONFIDENCE" not in kinds,         "the stronger sign finding must suppress the calibration one"


def test_independent_count_collapses_overlapping_forward_windows():
    packed = _recs(120, 1, 0.6, hold=60, spacing=5)     # 5-min bars, 60-min hold
    assert independent_count(packed) == 10, "120 packed records are ~10 independent"
    spaced = _recs(120, 1, 0.6, hold=60)
    assert independent_count(spaced) == 120


def test_a_proposal_threshold_is_applied_to_the_independent_count():
    """
    Guard against the inflated-n error directly: 200 records packed at bar spacing are
    ~17 independent observations and must not clear a min_n of 30.
    """
    c = score(_recs(200, -1, 0.20, spacing=5), "packed")
    assert c.n_directional == 200 and c.n_independent < 30
    assert R.analyse({"packed": c}, min_n=30) == []
    assert R.analyse({"packed": c}, min_n=10), "it should pass a threshold it clears"


def test_a_hit_rate_a_whisker_below_50_is_not_an_inversion():
    """
    The second defect the first authentic run produced: BREAKOUT came back at a 49.5%
    hit rate on 84 independent observations and the bare `< 50` test called it inverted.
    One standard error there is 5.5 percentage points, so 49.5% is 0.1 SE below a coin
    flip. Without a materiality bar the loop proposes a change on nothing.
    """
    c = score(_recs(400, 1, 0.495, p=0.85), "coinflip_family")
    assert c.hit_rate < 50.0
    assert c.brier_delta_vs_coinflip < 0
    assert inverted_families({"coinflip_family": c}, min_n=30) == []


def test_a_materially_wrong_family_still_clears_the_bar():
    """The bar must not be so high that a real inversion is missed."""
    c = score(_recs(400, -1, 0.38, p=0.70), "really_wrong")
    inv = inverted_families({"really_wrong": c}, min_n=30)
    assert [k for k, _ in inv] == ["really_wrong"]


def test_the_inversion_bar_scales_with_the_sample():
    """46% is noise on 40 observations and a finding on 1000."""
    small = score(_recs(40, 1, 0.46, p=0.70), "small")
    large = score(_recs(1000, 1, 0.46, p=0.70), "large")
    assert inverted_families({"small": small}, min_n=30) == []
    assert [k for k, _ in inverted_families({"large": large}, min_n=30)] == ["large"]


def test_the_confidence_proposal_is_one_entry_for_the_shared_mapping():
    """
    `direction_score` comes from a single expression in the decider, so N miscalibrated
    families are one change, not N. Queueing one per family would invite N separate
    edits to one line.
    """
    cal = {f"F{i}": score(_recs(200, 1, 0.52, p=0.90, family=f"F{i}"), f"F{i}")
           for i in range(4)}
    props = [p for p in R.analyse(cal) if p.kind == "RECALIBRATE_CONFIDENCE"]
    assert len(props) == 1, "one shared mapping, one proposal"
    assert len(props[0].evidence["scopes"]) == 4, "all four must appear as evidence"
    assert props[0].target_file == "src/agent/deciders.py"


def test_the_allow_list_is_the_binding_constraint_not_the_deny_list(tmp_path, monkeypatch):
    """
    PROTECTED gives a clear error for the files that matter today, but the guarantee
    rests on PROPOSABLE: a risk file added tomorrow will not be in PROTECTED either,
    and must still be refused. Fail-closed, not fail-open.
    """
    monkeypatch.chdir(tmp_path)
    for future in ("src/risk/new_gate_added_later.py",
                   "src/execution/some_new_broker.py",
                   "configs/risk_overrides.yaml",
                   "scripts/promote.py"):
        p = R.Proposal(proposal_id="X", created_at="now", kind="RETUNE",
                       target_file=future, summary="s", evidence={}, rationale="r",
                       validation_required=[])
        with pytest.raises(R.ProtectedFileError):
            R.write_journal([p], md_path="journal/t.md", json_path="journal/t.json")


def test_a_refused_proposal_writes_nothing_at_all(tmp_path, monkeypatch):
    """
    The target check runs over EVERY proposal before any write, so one bad entry in a
    batch cannot leave a half-written journal that a later reader treats as complete.
    """
    monkeypatch.chdir(tmp_path)
    good = R.Proposal(proposal_id="G", created_at="now", kind="RETUNE",
                      target_file="src/market/setups.py", summary="s", evidence={},
                      rationale="r", validation_required=["v"])
    bad = R.Proposal(proposal_id="B", created_at="now", kind="RETUNE",
                     target_file="src/risk/structure_risk.py", summary="s", evidence={},
                     rationale="r", validation_required=["v"])
    with pytest.raises(R.ProtectedFileError):
        R.write_journal([good, bad], md_path="journal/t.md", json_path="journal/t.json")
    assert not os.path.exists("journal/t.md"), "a refused batch must write nothing"
    assert not os.path.exists("journal/t.json")
