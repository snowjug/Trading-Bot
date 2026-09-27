"""
Run the calibration -> proposal loop on authentic data.

    python scripts/research/run_calibration.py --start 2023-01-01 --end 2023-12-31

Detects candidates exactly as the live agent would, grades each one's forecast against
the outcome AND against the option market's own implied move, then writes proposals to
`journal/proposals.md`.

Nothing is applied. The script has no code path that edits a strategy file, and
`tests/test_retrospective_guardrails.py` enforces that the retrospective module cannot
either.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.market.market_state import StateBuilder, resample
from src.market.setups import detect, options_vol_setup
from src.research.calibration import (
    ForecastRecord, by_family, implied_move_from_straddle, report, save,
)
from src.research.retrospective import analyse, write_journal

SPOT5 = "data/derived/nifty_spot_5m.parquet"
GRID_CE = "data/derived/grid5m_ce.parquet"
GRID_PE = "data/derived/grid5m_pe.parquet"
PANEL = "data/derived/chain_panel.parquet"
SESSION_CLOSE = dtime(15, 30)


def build_straddle_index():
    """
    ATM straddle price per (session, time), from authentic traded 5-minute option bars.

    Keys are derived from the `datetime` column, not the stored `sess`/`t` columns, so
    they are guaranteed to compare equal to the keys the main loop builds.
    """
    cols = ["datetime", "strike", "close", "spot"]
    parts = []
    for path, side in ((GRID_CE, "CE"), (GRID_PE, "PE")):
        d = pd.read_parquet(path, columns=cols)
        d["sess"] = d["datetime"].dt.date
        d["t"] = d["datetime"].dt.time
        d["gap"] = (d["strike"] - d["spot"]).abs()
        # nearest-to-spot strike per timestamp = the authentic ATM, never interpolated
        d = d.sort_values(["sess", "t", "gap"]).drop_duplicates(["sess", "t"])
        parts.append(d[["sess", "t", "close"]].rename(columns={"close": side}))
    m = parts[0].merge(parts[1], on=["sess", "t"], how="inner")
    m = m[(m["CE"] > 0) & (m["PE"] > 0)]
    return dict(zip(zip(m["sess"], m["t"]),
                    (m["CE"] + m["PE"]).astype(float).to_numpy()))


def build_dte_index():
    """Days to the near expiry, per session, from the authentic chain panel."""
    p = pd.read_parquet(PANEL, columns=["date", "dte"])
    p["date"] = pd.to_datetime(p["date"])
    return {d.date(): int(v) for d, v in zip(p["date"], p["dte"]) if np.isfinite(v)}


def minutes_to_expiry(sess, t, dte_map) -> float | None:
    dte = dte_map.get(sess)
    if dte is None:
        return None
    mins_left_today = max(0.0, (dtime(15, 30).hour * 60 + 30)
                          - (t.hour * 60 + t.minute))
    return float(mins_left_today + dte * 375.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--hold", type=int, default=60, help="holding period, minutes")
    ap.add_argument("--cal-out", default="reports/calibration.json")
    ap.add_argument("--no-journal", action="store_true")
    args = ap.parse_args()

    s5 = pd.read_parquet(SPOT5)
    s5["datetime"] = pd.to_datetime(s5["datetime"])
    s5 = s5.sort_values("datetime").reset_index(drop=True)
    a, b = pd.Timestamp(args.start).date(), pd.Timestamp(args.end).date()

    frames = {"5m": s5, "15m": resample(s5, "15min"), "30m": resample(s5, "30min"),
              "1h": resample(s5, "60min"), "1d": resample(s5, "1D")}
    sb = StateBuilder("NIFTY", frames, primary_tf="5m", source="REPLAY_GRID")

    print("indexing authentic ATM straddle prices ...", flush=True)
    straddle = build_straddle_index()
    dte_map = build_dte_index()
    print(f"  {len(straddle):,} (session, time) straddle points; "
          f"{len(dte_map):,} sessions with a dte", flush=True)

    close = s5["close"].to_numpy(float)
    sess_arr = s5["datetime"].dt.date.to_numpy()
    ts = s5["datetime"].to_numpy()
    n_bars = max(1, args.hold // 5)
    idxs = np.flatnonzero(np.array([(a <= d <= b) for d in sess_arr]))
    print(f"window {a} .. {b}   bars {len(idxs):,}   hold {args.hold}min "
          f"({n_bars} bars)", flush=True)

    recs: list[ForecastRecord] = []
    skipped = {"CROSSES_SESSION": 0, "NO_STATE": 0, "NO_STRADDLE": 0}
    for k, i in enumerate(idxs):
        if k % 5000 == 0 and k:
            print(f"  ...{k:,}/{len(idxs):,}  records={len(recs):,}", flush=True)
        j = i + n_bars
        if j >= len(close) or sess_arr[j] != sess_arr[i]:
            skipped["CROSSES_SESSION"] += 1
            continue
        try:
            st = sb.at(pd.Timestamp(ts[i]))
        except Exception:                                      # noqa: BLE001
            skipped["NO_STATE"] += 1
            continue
        sess, t = pd.Timestamp(ts[i]).date(), pd.Timestamp(ts[i]).time()
        sp = straddle.get((sess, t))
        cands = list(detect(st))
        if sp:
            ov = options_vol_setup(st, sp, None)
            if ov is not None:
                cands.append(ov)
        if not cands:
            continue
        mte = minutes_to_expiry(sess, t, dte_map)
        implied = implied_move_from_straddle(sp, mte, args.hold) if (sp and mte) else None
        if implied is None:
            skipped["NO_STRADDLE"] += 1
        moved = float(close[j] - close[i])
        for c in cands:
            # The agent's own confidence rule, mirrored from HeuristicDecider so the
            # score grades what the agent would actually have asserted.
            base = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}[c.quality_hint]
            aligned = ((c.direction > 0 and st.htf_alignment >= 1)
                       or (c.direction < 0 and st.htf_alignment <= -1))
            p = min(1.0, 0.45 + 0.15 * (base + (1 if aligned else 0)))
            recs.append(ForecastRecord(
                bar_time=pd.Timestamp(ts[i]).to_pydatetime(), family=c.kind,
                direction=int(c.direction), direction_score=float(p),
                expected_move_pts=float(c.expected_move_pts or 0.0),
                expected_move_horizon_minutes=int(c.expected_move_horizon_minutes),
                hold_minutes=args.hold, realised_move_pts=moved,
                realised_abs_move_pts=abs(moved), market_implied_move_pts=implied,
                decision_source="heuristic-mirror"))

    print(f"\nforecast records: {len(recs):,}   skipped: {skipped}")
    if not recs:
        print("nothing to grade")
        return 0

    cal = by_family(recs)
    print("\n" + "=" * 112)
    print("CALIBRATION  --  is the forecast better than the market's, before money")
    print("brier_delta > 0 means better than that baseline; SKILL needs BOTH > 0")
    print("=" * 112)
    print(report(cal))

    save(cal, args.cal_out, meta={"window": {"start": str(a), "end": str(b)},
                                  "hold_minutes": args.hold,
                                  "records": len(recs), "skipped": skipped})
    print(f"\nwrote {args.cal_out}")

    props = analyse(cal)
    print("\n" + "=" * 112)
    print(f"PROPOSALS GENERATED: {len(props)}  (none applied; a human promotes)")
    print("=" * 112)
    for p in props:
        print(f"  [{p.kind:15}] {p.target_file:28} {p.summary}")
    if not args.no_journal and props:
        path = write_journal(props, meta={"window": {"start": str(a), "end": str(b)},
                                         "hold_minutes": args.hold,
                                         "records": len(recs)})
        print(f"\nwrote {path}  (documentation only; nothing reads it back)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
