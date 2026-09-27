"""
CALIBRATION — is the agent's forecast better than the market's, before money enters.

WHY THIS EXISTS. Up to now the only verdict instrument has been replay P&L, which is
noisy and dominated by friction: the agent lost Rs 131,883 at t = -5.62, and that
single number cannot distinguish "it has no view" from "it has a view it cannot afford
to express". Scoring the FORECAST separates those.

The design borrows one idea from the `bennyjo/phil` prediction-market agent: its honest
metric is `brier_delta`, forecast accuracy measured against the MARKET's own price
rather than against profit. Adapted here, with the market's forecast taken from
instruments this repository already prices authentically.

TWO SCORES, deliberately separate, because they fail for different reasons.

1. DIRECTIONAL SKILL (Brier). The agent asserts a direction with a `direction_score`
   in 0..1. The outcome is whether the underlying actually moved that way over the
   holding period. Brier = mean((p - outcome)^2), lower is better, and it is reported
   as `brier_delta` against two baselines:

     - a coin flip at p = 0.50, the market's implicit view for a near-ATM option
     - the realised base rate over the same bars, which is the harder baseline because
       it already contains the index's drift

   A family can only be said to have directional skill if it beats BOTH.

2. MAGNITUDE CALIBRATION. The agent states `expected_move_points` over a declared
   horizon. That is compared to the realised absolute move AND to the option market's
   own implied move for the same window, taken from the ATM straddle. An agent whose
   magnitude estimate is worse than the straddle's has no volatility skill, whatever
   its P&L looks like.

WHAT THIS IS NOT. It is not a performance report and it never decides anything. It
produces evidence. Acting on that evidence is `retrospective.py`, which may only
PROPOSE, and a human promotes.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

SESSION_MINUTES = 375


@dataclass
class ForecastRecord:
    """
    One forecast and its outcome. Built after the fact, never used to make a decision.

    `market_implied_move_pts` is the option market's expected absolute move over the
    SAME horizon, or None when it could not be derived authentically — in which case
    the magnitude comparison is skipped rather than filled in.
    """
    bar_time: datetime
    family: str
    direction: int                      # +1 / -1 / 0
    direction_score: float              # the agent's confidence, 0..1
    expected_move_pts: float
    expected_move_horizon_minutes: int
    hold_minutes: int
    realised_move_pts: float            # signed, over the hold
    realised_abs_move_pts: float
    market_implied_move_pts: Optional[float] = None
    state_hash: str = ""
    decision_source: str = ""

    @property
    def went_right(self) -> Optional[int]:
        """1 if the move agreed with the stated direction, 0 if not, None if neutral."""
        if self.direction == 0:
            return None
        return int(self.realised_move_pts * self.direction > 0)


def brier(scores: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((scores - outcomes) ** 2))


def implied_move_from_straddle(straddle_pts: float, minutes_to_expiry: float,
                               horizon_minutes: float) -> Optional[float]:
    """
    The market's expected absolute move over `horizon_minutes`, from the ATM straddle.

    An ATM straddle is approximately the market's expected absolute move to expiry, so
    scaling by sqrt(horizon / time_to_expiry) gives the shorter-horizon equivalent.
    The 0.8 factor is the standard adjustment from a straddle price to E|move| for a
    roughly normal distribution; it is a constant, stated, and applied to BOTH sides of
    every comparison, so it cannot flatter the agent.

    Returns None rather than a guess when the inputs are not usable.
    """
    if (straddle_pts is None or straddle_pts <= 0
            or minutes_to_expiry is None or minutes_to_expiry <= 0
            or horizon_minutes <= 0):
        return None
    scale = min(1.0, (horizon_minutes / minutes_to_expiry) ** 0.5)
    return float(0.8 * straddle_pts * scale)


def independent_count(records: List[ForecastRecord]) -> int:
    """
    The size of a maximal set of records whose forward windows do not overlap.

    Greedy left-to-right on bar_time: take a record, then skip every record that starts
    before that one's hold has elapsed. Two records on the same bar count once. This is
    the sample size any t-stat or proposal threshold must use — `len(records)` on
    5-minute bars with a 60-minute hold overstates it by about 12x.
    """
    if not records:
        return 0
    times = sorted(pd.Timestamp(r.bar_time) for r in records)
    hold = pd.Timedelta(minutes=max(1, records[0].hold_minutes))
    n, cutoff = 0, None
    for t in times:
        if cutoff is None or t >= cutoff:
            n += 1
            cutoff = t + hold
    return n


@dataclass
class CalibrationResult:
    scope: str
    n: int
    # directional
    n_directional: int = 0
    hit_rate: Optional[float] = None
    mean_score: Optional[float] = None
    brier_agent: Optional[float] = None
    brier_coinflip: Optional[float] = None
    brier_base_rate: Optional[float] = None
    brier_delta_vs_coinflip: Optional[float] = None
    brier_delta_vs_base_rate: Optional[float] = None
    has_directional_skill: Optional[bool] = None
    # magnitude
    n_magnitude: int = 0
    mean_expected_pts: Optional[float] = None
    mean_realised_abs_pts: Optional[float] = None
    magnitude_bias_ratio: Optional[float] = None       # expected / realised
    mae_agent_pts: Optional[float] = None
    mae_market_pts: Optional[float] = None
    beats_market_on_magnitude: Optional[bool] = None
    # Observations whose forward windows do not overlap. With a 60-minute hold on
    # 5-minute bars, consecutive records share 11/12 of their window, so `n` is
    # roughly 12x the independent sample and must never be used as a sample size.
    #
    # NOTE ON WHICH SAMPLE EACH NUMBER USES. `hit_rate`, `brier_agent` and every other
    # point estimate are computed on ALL records, because each overlapping observation
    # is still a valid draw — merely correlated with its neighbours — and using all of
    # them gives the better estimate. `n_independent` is used only where CORRELATION
    # matters: the error bar, and therefore every sample-size and materiality
    # threshold. Mixing them this way is deliberate, not an oversight.
    #
    # The two can disagree when thinning bites: on 2022-2023, VWAP_REVERSION|dir=+1
    # scored 49.8% across all 235 records but 53.6% on the 125-observation thinned
    # subset. Neither is wrong; the gap is a measure of how much that cell's estimate
    # depends on which bars survive thinning, and it is a reason to distrust the cell.
    n_independent: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score(records: List[ForecastRecord], scope: str = "ALL") -> CalibrationResult:
    """
    Grade a set of forecasts. Every comparison that cannot be made authentically is
    left as None and counted, never defaulted.
    """
    res = CalibrationResult(scope=scope, n=len(records))
    if not records:
        res.notes.append("no records")
        return res

    # ── directional ──────────────────────────────────────────────────────────
    dirs = [r for r in records if r.went_right is not None]
    res.n_directional = len(dirs)
    res.n_independent = independent_count(dirs)
    if len(dirs) >= 10:
        p = np.clip(np.array([r.direction_score for r in dirs], float), 0.0, 1.0)
        y = np.array([r.went_right for r in dirs], float)
        res.hit_rate = round(float(y.mean() * 100), 1)
        res.mean_score = round(float(p.mean()), 3)
        res.brier_agent = round(brier(p, y), 5)
        res.brier_coinflip = round(brier(np.full_like(p, 0.5), y), 5)
        res.brier_base_rate = round(brier(np.full_like(p, float(y.mean())), y), 5)
        res.brier_delta_vs_coinflip = round(res.brier_coinflip - res.brier_agent, 5)
        res.brier_delta_vs_base_rate = round(res.brier_base_rate - res.brier_agent, 5)
        # Skill requires beating BOTH: a coin flip, and the base rate that already
        # contains the drift. Beating only the coin flip means it discovered the drift.
        res.has_directional_skill = bool(res.brier_delta_vs_coinflip > 0
                                         and res.brier_delta_vs_base_rate > 0)
    else:
        res.notes.append(f"only {len(dirs)} directional records; need 10")

    # ── magnitude ────────────────────────────────────────────────────────────
    mag = [r for r in records if r.market_implied_move_pts is not None]
    res.n_magnitude = len(mag)
    if len(mag) >= 10:
        exp = np.array([r.expected_move_pts for r in mag], float)
        act = np.array([r.realised_abs_move_pts for r in mag], float)
        mkt = np.array([r.market_implied_move_pts for r in mag], float)
        # the agent's estimate is over its own declared horizon; scale to the hold the
        # same way the risk gate does, so the comparison is like for like
        hold = np.array([max(1.0, r.hold_minutes) for r in mag], float)
        hor = np.array([max(1.0, r.expected_move_horizon_minutes) for r in mag], float)
        exp_scaled = exp * np.minimum(1.0, np.sqrt(hold / hor))
        res.mean_expected_pts = round(float(exp_scaled.mean()), 2)
        res.mean_realised_abs_pts = round(float(act.mean()), 2)
        res.magnitude_bias_ratio = (round(float(exp_scaled.mean() / act.mean()), 3)
                                    if act.mean() > 0 else None)
        res.mae_agent_pts = round(float(np.mean(np.abs(exp_scaled - act))), 2)
        res.mae_market_pts = round(float(np.mean(np.abs(mkt - act))), 2)
        res.beats_market_on_magnitude = bool(res.mae_agent_pts < res.mae_market_pts)
    else:
        res.notes.append(f"only {len(mag)} records with an authentic market implied "
                         f"move; magnitude comparison skipped")
    return res


def by_family(records: List[ForecastRecord]) -> Dict[str, CalibrationResult]:
    """
    Per-family calibration. This is the view that catches an INVERTED family, which a
    portfolio-level P&L number hides: a family whose Brier is WORSE than a coin flip is
    not merely unhelpful, it is carrying information with the sign reversed.
    """
    out: Dict[str, CalibrationResult] = {}
    for fam in sorted({r.family for r in records}):
        sub = [r for r in records if r.family == fam]
        out[fam] = score(sub, scope=fam)
    for fam in sorted({f"{r.family}|dir={r.direction:+d}" for r in records
                       if r.direction != 0}):
        f, d = fam.split("|dir=")
        sub = [r for r in records if r.family == f and r.direction == int(d)]
        if len(sub) >= 10:
            out[fam] = score(sub, scope=fam)
    return out


def inverted_families(cal: Dict[str, CalibrationResult],
                      min_n: int = 30, z: float = 1.5) -> List[Tuple[str, float]]:
    """
    Families whose directional forecast is systematically WRONG — the market moved
    against the stated direction more often than not.

    THE TEST IS THE HIT RATE, NOT THE BRIER SCORE. A Brier worse than a coin flip has
    two completely different causes and only one of them is an inversion:

      reversed discrimination  hit rate < 50%. The sign is wrong. Flipping it helps.
      overconfidence           hit rate >= 50% but the stated score is far from the
                               truth. The sign is RIGHT; flipping it makes things
                               worse. The fix is to shrink the score toward 0.5.

    An earlier version of this function used `brier_delta < 0` alone, and on real data
    it proposed inverting a family with a 53.7% hit rate — a change that would have
    made the forecast worse. The hit rate is the discriminating statistic; the Brier
    delta is returned as the effect size.

    The hit rate must also be below 50% by MORE THAN SAMPLING NOISE. A bare `< 50`
    test has no materiality bar: the first real run reported a 49.5% family on 84
    independent observations, where one standard error is 5.5 percentage points, so
    49.5% sits 0.1 SE below a coin flip and means nothing. The bar is `z` standard
    errors, with the standard error of a proportion taken at its maximum (0.5/sqrt(n)),
    which is the conservative choice.

    `min_n` and the standard error are both computed from `n_independent` when it is
    known, because overlapping forward windows inflate `n_directional` by the overlap
    factor and would shrink the error bar by sqrt(that factor).
    """
    out = []
    for k, c in cal.items():
        n = c.n_independent if c.n_independent is not None else c.n_directional
        if (n < min_n or c.hit_rate is None
                or c.brier_delta_vs_coinflip is None):
            continue
        shortfall = 0.50 - float(c.hit_rate) / 100.0
        if shortfall > z * 0.5 / (n ** 0.5):
            out.append((k, c.brier_delta_vs_coinflip))
    return sorted(out, key=lambda x: x[1])


def overconfident_families(cal: Dict[str, CalibrationResult],
                           min_n: int = 30,
                           min_gap: float = 0.10) -> List[Tuple[str, float]]:
    """
    Families whose stated confidence is far above what they deliver, while still
    pointing the right way. Reported as (scope, stated_score - hit_rate_fraction).

    This is a calibration fault, not a signal fault, and it matters because
    `direction_score` is an input the risk gate and any downstream model consume. A
    decider asserting 0.90 on a setup that resolves at 0.50 is not wrong about
    direction — it is wrong about how much to believe itself.
    """
    out = []
    for k, c in cal.items():
        n = c.n_independent if c.n_independent is not None else c.n_directional
        if (n >= min_n and c.hit_rate is not None and c.mean_score is not None
                and c.hit_rate >= 50.0):
            gap = float(c.mean_score) - float(c.hit_rate) / 100.0
            if gap >= min_gap:
                out.append((k, round(gap, 4)))
    return sorted(out, key=lambda x: -x[1])


def build_records_from_setups(
    events: pd.DataFrame, spot5: pd.DataFrame, *,
    hold_minutes: int = 60, bars_per_minute: float = 1 / 5.0,
    straddle_lookup: Optional[Any] = None,
    minutes_to_expiry_lookup: Optional[Any] = None,
    direction_score_for: Optional[Any] = None,
) -> List[ForecastRecord]:
    """
    Turn detected candidate events into scoreable forecasts.

    `events` needs columns: bar_index, family, direction, expected_move_pts,
    expected_move_horizon_minutes. Optional callables supply the market's straddle and
    time to expiry; when either is absent the magnitude comparison is simply skipped
    for that record, which keeps the directional score usable on its own.

    A record is dropped only when the forward window would cross a session boundary —
    a "60-minute" horizon must not silently span an overnight gap.
    """
    close = spot5["close"].to_numpy(float)
    sess = pd.to_datetime(spot5["datetime"]).dt.date.to_numpy()
    ts = pd.to_datetime(spot5["datetime"]).to_numpy()
    n_bars = int(round(hold_minutes * bars_per_minute))
    out: List[ForecastRecord] = []
    for _, e in events.iterrows():
        i = int(e["bar_index"])
        j = i + n_bars
        if j >= len(close) or sess[j] != sess[i]:
            continue
        moved = float(close[j] - close[i])
        dirn = int(e["direction"])
        p = (float(direction_score_for(e)) if direction_score_for
             else float(e.get("direction_score", 0.6)))
        straddle = (float(straddle_lookup(ts[i])) if straddle_lookup else None)
        mte = (float(minutes_to_expiry_lookup(ts[i]))
               if minutes_to_expiry_lookup else None)
        implied = (implied_move_from_straddle(straddle, mte, hold_minutes)
                   if (straddle and mte) else None)
        out.append(ForecastRecord(
            bar_time=pd.Timestamp(ts[i]).to_pydatetime(),
            family=str(e["family"]), direction=dirn, direction_score=p,
            expected_move_pts=float(e["expected_move_pts"]),
            expected_move_horizon_minutes=int(e["expected_move_horizon_minutes"]),
            hold_minutes=hold_minutes, realised_move_pts=moved,
            realised_abs_move_pts=abs(moved), market_implied_move_pts=implied,
            state_hash=str(e.get("state_hash", "")),
            decision_source=str(e.get("decision_source", ""))))
    return out


def report(cal: Dict[str, CalibrationResult]) -> str:
    L: List[str] = []
    L.append(f"{'scope':34}{'n':>6}{'indep':>7}{'hit%':>7}{'score':>7}{'brier':>9}"
             f"{'vs coin':>9}{'vs base':>9}{'skill':>7}{'nMag':>6}{'mag bias':>10}"
             f"{'beats mkt':>11}")
    for k in sorted(cal):
        c = cal[k]
        L.append(f"{k[:33]:34}{c.n_directional:>6}"
                 f"{(str(c.n_independent) if c.n_independent is not None else '-'):>7}"
                 f"{(f'{c.hit_rate:.1f}' if c.hit_rate is not None else '-'):>7}"
                 f"{(f'{c.mean_score:.2f}' if c.mean_score is not None else '-'):>7}"
                 f"{(f'{c.brier_agent:.4f}' if c.brier_agent is not None else '-'):>9}"
                 f"{(f'{c.brier_delta_vs_coinflip:+.4f}' if c.brier_delta_vs_coinflip is not None else '-'):>9}"
                 f"{(f'{c.brier_delta_vs_base_rate:+.4f}' if c.brier_delta_vs_base_rate is not None else '-'):>9}"
                 f"{(str(c.has_directional_skill) if c.has_directional_skill is not None else '-'):>7}"
                 f"{c.n_magnitude:>6}"
                 f"{(f'{c.magnitude_bias_ratio:.2f}x' if c.magnitude_bias_ratio is not None else '-'):>10}"
                 f"{(str(c.beats_market_on_magnitude) if c.beats_market_on_magnitude is not None else '-'):>11}")
    return "\n".join(L)


def save(cal: Dict[str, CalibrationResult], path: str,
         meta: Optional[Dict[str, Any]] = None) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(),
                   "meta": meta or {},
                   "scopes": {k: v.to_dict() for k, v in cal.items()}},
                  f, indent=2, default=str)
