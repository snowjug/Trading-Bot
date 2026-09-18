"""
Shared validation battery for strategy research.

The point of this module is to make it HARD to believe a backtest, not easy. Every
routine here is designed to find a reason the result is not real: too few trades,
a break-even threshold inside the confidence interval, an edge that dies under
slippage, a sequence indistinguishable from a random reordering.

Nothing here selects parameters, periods or symbols. It only measures.
"""

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


# ───────────────────────── PROPORTION INFERENCE ─────────────────────────

def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> Dict[str, float]:
    """
    Exact binomial confidence interval.

    Used instead of a normal approximation because the interesting cases here are
    exactly the ones it handles badly: 0 successes, or very few, in a small sample.
    """
    from scipy.stats import beta
    if n == 0:
        return {"lo": 0.0, "hi": 1.0, "point": float("nan")}
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return {"lo": lo, "hi": hi, "point": k / n}


def breakeven_adverse_rate(avg_win: float, avg_loss: float) -> Optional[float]:
    """
    The adverse-outcome rate at which expectancy turns negative.

    For a structure that wins small and loses big, this single number decides
    whether a high win rate means anything. avg_loss is passed as a negative.
    """
    if avg_loss >= 0 or avg_win <= 0:
        return None
    return float(avg_win / (avg_win + abs(avg_loss)))


def sample_size_verdict(n_trades: int, observed_adverse: int, breakeven: Optional[float],
                        alpha: float = 0.05) -> Dict[str, Any]:
    """
    Decides whether the sample can distinguish a profitable structure from a
    losing one, rather than whether the backtest happens to be green.
    """
    ci = clopper_pearson(observed_adverse, n_trades, alpha)
    if breakeven is None:
        return {"verdict": "INDETERMINATE", "reason": "no losing trades to estimate the tail",
                "adverse_ci": ci, "breakeven_rate": None}
    # Three outcomes, not two. A sample can settle the question in EITHER direction,
    # and collapsing "we cannot tell" with "we can tell it loses" would let a
    # demonstrably negative strategy hide behind an inconclusive-sounding label.
    if ci["hi"] < breakeven:
        verdict = "EDGE_DISTINGUISHABLE"
        reason = (f"the 95% upper bound on the adverse rate ({ci['hi']:.3f}) is below "
                  f"the break-even rate ({breakeven:.3f})")
    elif ci["lo"] > breakeven:
        verdict = "CONCLUSIVELY_ADVERSE"
        reason = (f"the 95% LOWER bound on the adverse rate ({ci['lo']:.3f}) is above "
                  f"the break-even rate ({breakeven:.3f}), so this sample shows a "
                  f"losing structure rather than merely failing to confirm a winning one")
    else:
        verdict = "NOT_DISTINGUISHABLE"
        reason = (f"the break-even rate ({breakeven:.3f}) lies inside the 95% interval "
                  f"[{ci['lo']:.3f}, {ci['hi']:.3f}], so this sample cannot separate a "
                  f"winning structure from a losing one")
    return {
        "n_trades": n_trades,
        "observed_adverse": observed_adverse,
        "adverse_rate": ci["point"],
        "adverse_ci95": [round(ci["lo"], 5), round(ci["hi"], 5)],
        "breakeven_rate": round(breakeven, 5),
        "verdict": verdict,
        "reason": reason,
    }


def trades_needed(breakeven: float, assumed_true_rate: float, alpha: float = 0.05) -> Optional[int]:
    """
    Roughly how many trades would be needed before the CI could clear break-even.

    Answers "how much more data" concretely instead of saying "not enough".
    """
    if not (0 < assumed_true_rate < breakeven < 1):
        return None
    for n in range(10, 20001, 10):
        k = int(round(assumed_true_rate * n))
        if clopper_pearson(k, n)["hi"] < breakeven:
            return n
    return None


# ───────────────────────── SPLITS AND SEQUENCES ─────────────────────────

def chronological_split(pnl: Sequence[float], dates: Sequence[Any],
                        is_frac: float = 0.7) -> Dict[str, Any]:
    """A-priori 70/30 chronological split. The fraction is fixed, never searched."""
    n = len(pnl)
    if n < 10:
        return {"verdict": "INSUFFICIENT", "n": n}
    cut = int(n * is_frac)
    a, b = np.array(pnl[:cut]), np.array(pnl[cut:])
    return {
        "split_date": str(dates[cut]) if cut < len(dates) else None,
        "is": {"n": len(a), "net": float(a.sum()), "mean": float(a.mean()),
               "win_rate": float((a > 0).mean() * 100)},
        "oos": {"n": len(b), "net": float(b.sum()), "mean": float(b.mean()),
                "win_rate": float((b > 0).mean() * 100)},
        "sign_agreement": bool(np.sign(a.mean()) == np.sign(b.mean())),
    }


def walk_forward(pnl: Sequence[float], dates: Sequence[Any], folds: int = 4) -> Dict[str, Any]:
    """Contiguous equal folds. No refitting happens — there is nothing to fit."""
    n = len(pnl)
    if n < folds * 5:
        return {"verdict": "INSUFFICIENT", "n": n, "folds_requested": folds}
    edges = np.linspace(0, n, folds + 1).astype(int)
    out = []
    for i in range(folds):
        seg = np.array(pnl[edges[i]:edges[i + 1]])
        if not len(seg):
            continue
        out.append({"fold": i + 1, "n": int(len(seg)),
                    "start": str(dates[edges[i]]), "net": float(seg.sum()),
                    "mean": float(seg.mean()), "win_rate": float((seg > 0).mean() * 100)})
    pos = sum(1 for f in out if f["net"] > 0)
    return {"folds": out, "folds_positive": pos, "folds_total": len(out),
            "consistent": pos == len(out)}


def monte_carlo_paths(pnl: Sequence[float], n_paths: int = 2000,
                      seed: int = 20260918) -> Dict[str, Any]:
    """
    Bootstrap the ORDER of realised trades.

    This says nothing about whether the edge is real — only what drawdown the same
    trades could have produced in a different sequence. Reported so a lucky
    ordering is not mistaken for robustness.
    """
    a = np.array(pnl, dtype=float)
    if len(a) < 5:
        return {"verdict": "INSUFFICIENT", "n": len(a)}
    rng = np.random.default_rng(seed)
    finals, dds = np.empty(n_paths), np.empty(n_paths)
    for i in range(n_paths):
        p = rng.permutation(a)
        eq = np.cumsum(p)
        finals[i] = eq[-1]
        dds[i] = float((eq - np.maximum.accumulate(eq)).min())
    return {
        "paths": n_paths,
        "final_pnl_mean": float(finals.mean()),
        "final_pnl_p05": float(np.percentile(finals, 5)),
        "final_pnl_p95": float(np.percentile(finals, 95)),
        "max_drawdown_median": float(np.median(dds)),
        "max_drawdown_p05_worst": float(np.percentile(dds, 5)),
        "prob_final_negative": float((finals < 0).mean()),
    }


def resample_control(pnl: Sequence[float], n_draws: int = 2000,
                     seed: int = 20260918) -> Dict[str, Any]:
    """
    With-replacement bootstrap of the realised P&L pool.

    Controls for sequencing ONLY. It cannot show that entry selection had value,
    because it reuses the very trades that selection produced. Stated so the
    result is not over-read.
    """
    a = np.array(pnl, dtype=float)
    if len(a) < 5:
        return {"verdict": "INSUFFICIENT", "n": len(a)}
    rng = np.random.default_rng(seed)
    sums = np.array([rng.choice(a, size=len(a), replace=True).sum() for _ in range(n_draws)])
    return {
        "draws": n_draws, "actual": float(a.sum()),
        "control_mean": float(sums.mean()), "control_sd": float(sums.std(ddof=1)),
        "actual_percentile": float((sums < a.sum()).mean() * 100),
        "prob_negative": float((sums < 0).mean()),
        "note": "sequencing control only; provides no evidence of entry-selection edge",
    }


# ───────────────────────── COST / SLIPPAGE STRESS ─────────────────────────

def slippage_sensitivity(pnl: Sequence[float], per_trade_extra_cost: Sequence[float],
                         labels: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """
    Re-prices the SAME trades under progressively worse fills.

    For a credit structure the credit is small, so a few points of slippage across
    four legs can consume most of it. This is the test that usually decides.
    """
    a = np.array(pnl, dtype=float)
    out = []
    for i, extra in enumerate(per_trade_extra_cost):
        adj = a - extra
        out.append({
            "label": labels[i] if labels else f"extra_{extra}",
            "extra_cost_per_trade": float(extra),
            "net": float(adj.sum()), "mean": float(adj.mean()),
            "win_rate": float((adj > 0).mean() * 100),
            "still_profitable": bool(adj.sum() > 0),
        })
    return out


def regime_breakdown(pnl: Sequence[float], regime_value: Sequence[float],
                     edges: Sequence[float], name: str = "vix") -> List[Dict[str, Any]]:
    """Bucketed performance. Reported for every bucket — never used to select one."""
    df = pd.DataFrame({"pnl": list(pnl), "v": list(regime_value)})
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        seg = df[(df["v"] >= lo) & (df["v"] < hi)]
        out.append({
            f"{name}_range": f"[{lo}, {hi})", "n": int(len(seg)),
            "net": float(seg["pnl"].sum()) if len(seg) else 0.0,
            "mean": float(seg["pnl"].mean()) if len(seg) else 0.0,
            "win_rate": float((seg["pnl"] > 0).mean() * 100) if len(seg) else 0.0,
        })
    return out


def deflated_expectation(n_variants_examined: int, t_stat: float, n_obs: int) -> Dict[str, Any]:
    """
    Multiple-testing haircut.

    Records how many variants were looked at and what the highest t-statistic would
    need to be to survive a Bonferroni-style adjustment. Honesty bookkeeping, not
    a significance claim.
    """
    from scipy.stats import t as tdist
    if n_obs < 3:
        return {"verdict": "INSUFFICIENT"}
    p_raw = float(2 * (1 - tdist.cdf(abs(t_stat), df=n_obs - 1)))
    p_adj = min(1.0, p_raw * max(1, n_variants_examined))
    return {
        "variants_examined": n_variants_examined, "t_stat": round(t_stat, 4),
        "p_raw": round(p_raw, 6), "p_bonferroni": round(p_adj, 6),
        "survives_5pct_after_adjustment": bool(p_adj < 0.05),
    }


def tstat(pnl: Sequence[float]) -> float:
    a = np.array(pnl, dtype=float)
    if len(a) < 2 or a.std(ddof=1) == 0:
        return 0.0
    return float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))
