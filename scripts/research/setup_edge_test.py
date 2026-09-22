"""
DO THE CANDIDATE FAMILIES CARRY ANY SIGNAL AT ALL?

The agent's deterministic decider lost money (-Rs 131,883, t = -5.62, worse than not
trading). Two explanations are possible and they lead to completely different work:

  A  the SETUPS are fine and the expression is wrong  -> fix structures, stops, sizing
  B  the SETUPS carry no directional information      -> no option structure can help,
                                                         because options only add cost

This script separates them, on the UNDERLYING, with no options involved. For every
bar where a family fires, it measures the index's forward return over the horizons an
intraday position would actually be held, signed by the direction the setup pointed.

Two controls make the answer meaningful:

  1. EXCESS over drift. A "bullish" family in a rising market looks good for free, so
     every number is reported net of the unconditional mean forward return for the
     same horizon over the same window.
  2. A t-stat on NON-OVERLAPPING observations. Consecutive 5-minute bars share most of
     their forward window, so raw t-stats are inflated; samples are thinned to one per
     horizon length.

If no family clears a modest bar on the underlying, the agent's problem is B, and
building better option machinery on top would be wasted effort. That is the finding
this script exists to establish or refute.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.market.market_state import StateBuilder, resample
from src.market.setups import detect

SPOT5 = "data/derived/nifty_spot_5m.parquet"
HORIZON_BARS = {"15m": 3, "30m": 6, "60m": 12, "120m": 24}


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--out", default="reports/setup_edge_test.json")
    args = ap.parse_args()

    s5 = pd.read_parquet(SPOT5)
    s5["datetime"] = pd.to_datetime(s5["datetime"])
    s5 = s5.sort_values("datetime").reset_index(drop=True)
    a, b = pd.Timestamp(args.start).date(), pd.Timestamp(args.end).date()

    frames = {"5m": s5, "15m": resample(s5, "15min"), "30m": resample(s5, "30min"),
              "1h": resample(s5, "60min"), "1d": resample(s5, "1D")}
    sb = StateBuilder("NIFTY", frames, primary_tf="5m", source="REPLAY_GRID")

    close = s5["close"].to_numpy(float)
    ts = s5["datetime"].to_numpy()
    sess = s5["datetime"].dt.date.to_numpy()
    in_win = np.array([(a <= d <= b) for d in sess])
    idxs = np.flatnonzero(in_win)
    print(f"window {a} .. {b}   bars {len(idxs):,}")

    # Forward returns in POINTS, and a same-session mask so a "60-minute" horizon
    # never silently spans an overnight gap.
    fwd = {}
    same_sess = {}
    for name, n in HORIZON_BARS.items():
        f = np.full(len(close), np.nan)
        f[:-n] = close[n:] - close[:-n]
        fwd[name] = f
        m = np.zeros(len(close), bool)
        m[:-n] = sess[n:] == sess[:-n]
        same_sess[name] = m

    rows = []
    for k, i in enumerate(idxs):
        if k % 5000 == 0 and k:
            print(f"  ...{k:,}/{len(idxs):,}", flush=True)
        try:
            st = sb.at(pd.Timestamp(ts[i]))
        except Exception:                                      # noqa: BLE001
            continue
        for c in detect(st):
            rows.append({"i": int(i), "kind": c.kind, "dir": int(c.direction),
                         "quality": c.quality_hint})

    if not rows:
        print("no candidates fired in the window")
        return 0
    d = pd.DataFrame(rows)
    print(f"\ncandidate events: {len(d):,} over {d['i'].nunique():,} distinct bars")

    # Unconditional drift, on the same bars, so "excess" means something.
    base = {}
    for h in HORIZON_BARS:
        m = in_win & same_sess[h] & np.isfinite(fwd[h])
        base[h] = float(np.mean(fwd[h][m]))
    print("\nunconditional mean forward move on these bars (points):")
    print("  " + "   ".join(f"{h} {base[h]:+.3f}" for h in HORIZON_BARS))

    out = []
    print("\n" + "=" * 104)
    print("SIGNED FORWARD MOVE AFTER EACH FAMILY, EXCESS OF DRIFT, UNDERLYING ONLY")
    print("non-overlapping samples; 'excess' subtracts direction x unconditional drift")
    print("=" * 104)
    print(f"{'family':26}{'dir':>4}{'horizon':>9}{'n':>7}{'raw pts':>10}"
          f"{'excess':>10}{'t':>8}{'win%':>7}")

    for (kind, dr), g in d.groupby(["kind", "dir"]):
        for h, n in HORIZON_BARS.items():
            ii = g["i"].to_numpy()
            ok = same_sess[h][ii] & np.isfinite(fwd[h][ii])
            ii = ii[ok]
            if len(ii) < 40:
                continue
            # thin to non-overlapping observations
            keep, last = [], -10**9
            for x in np.sort(ii):
                if x - last >= n:
                    keep.append(x); last = x
            ii = np.array(keep)
            if len(ii) < 30:
                continue
            raw = fwd[h][ii] * (dr if dr != 0 else 1)
            exc = raw - (base[h] * (dr if dr != 0 else 0))
            out.append({"family": kind, "direction": dr, "horizon": h,
                        "n": int(len(ii)), "raw_pts": round(float(raw.mean()), 3),
                        "excess_pts": round(float(exc.mean()), 3),
                        "t": round(tstat(exc), 2),
                        "win_pct": round(float((raw > 0).mean() * 100), 1)})
            print(f"{kind:26}{dr:>4}{h:>9}{len(ii):>7}{raw.mean():>10.2f}"
                  f"{exc.mean():>10.2f}{tstat(exc):>8.2f}{(raw > 0).mean()*100:>7.1f}")

    r = pd.DataFrame(out)
    print("\n" + "=" * 104)
    print("VERDICT")
    print("=" * 104)
    strong = r[(r["t"].abs() >= 2.0)]
    if strong.empty:
        print("  NO family reaches |t| >= 2.0 on excess forward move at any horizon.")
    else:
        for _, x in strong.sort_values("t", key=abs, ascending=False).iterrows():
            print(f"  {x['family']:26} dir={x['direction']:+d} {x['horizon']:>5} "
                  f"excess {x['excess_pts']:+.2f} pts  t={x['t']:+.2f}  n={x['n']}")
    best = r.reindex(r["t"].abs().sort_values(ascending=False).index).head(5)
    print("\n  strongest five regardless of the bar:")
    for _, x in best.iterrows():
        print(f"    {x['family']:26} dir={x['direction']:+d} {x['horizon']:>5} "
              f"excess {x['excess_pts']:+.2f} pts  t={x['t']:+.2f}  n={x['n']}")

    print("\n  COST REFERENCE: a 2-leg NIFTY option structure pays roughly 4.4 points")
    print("  of modelled friction per round trip (measured in the agent replay), so an")
    print("  excess below that cannot be monetised through options at all.")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"window": {"start": str(a), "end": str(b)},
                   "bars": int(len(idxs)), "events": int(len(d)),
                   "unconditional_drift_pts": {k: float(v) for k, v in base.items()},
                   "families": out}, f, indent=2, default=float)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
