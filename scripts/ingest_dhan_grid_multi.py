"""
Ingest 5-minute option bars for ANY index underlying Dhan serves, not just NIFTY.

WHY. `scripts/ingest_dhan_option_grid.py` hardcodes NIFTY (the client's default
`security_id="13"`), and three studies then recorded "intraday work is NIFTY-only"
as though it were a property of the data. Measured with a live token on 2026-09-19,
`/charts/rollingoption` serves 5-minute bars with `iv`, `oi`, `spot` and `strike`
fully populated for:

    NIFTY       id  13  NSE_FNO   floor 2020-08   ATM+/-10
    BANKNIFTY   id  25  NSE_FNO   floor 2021-08   ATM+/-10
    FINNIFTY    id  27  NSE_FNO   floor 2021-08   ATM+/-10
    MIDCPNIFTY  id 442  NSE_FNO   floor 2022-01   ATM+/-10
    SENSEX      id  51  BSE_FNO   floor 2023-05   ATM+/-10
    BANKEX      id  69  BSE_FNO   floor 2023-05   ATM+/-10
    NIFTYNXT50  id  38  NSE_FNO   floor 2025-11   (too short to be useful)

Security IDs come from the official scrip master (sha256 recorded in
data/catalog/scrip_master_provenance.json), never guessed. Floors come from
`scripts/probe/probe_dhan_depth.py`, measured rather than assumed.

The endpoint caps the ladder at ATM+/-10 and the window at one month; both limits
belong to the vendor, not to the data, and both are recorded as such.

A chunk that returns no rows is written to a ledger as EMPTY with its exact request,
so a vendor gap can never be mistaken for a market fact. Nothing is fabricated and
no partial download is silently treated as complete.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from src.data.dhan_client import get_dhan_client

OUT_ROOT = Path("data/raw/dhan/option_grid_5m_multi")
CATALOG = Path("data/catalog")

# name -> (security_id, exchange_segment, measured history floor)
UNDERLYINGS: Dict[str, Tuple[str, str, str]] = {
    "NIFTY": ("13", "NSE_FNO", "2020-08-01"),
    "BANKNIFTY": ("25", "NSE_FNO", "2021-08-01"),
    "FINNIFTY": ("27", "NSE_FNO", "2021-08-01"),
    "MIDCPNIFTY": ("442", "NSE_FNO", "2022-01-01"),
    "SENSEX": ("51", "BSE_FNO", "2023-05-01"),
    "BANKEX": ("69", "BSE_FNO", "2023-05-01"),
    "NIFTYNXT50": ("38", "NSE_FNO", "2025-11-01"),
}


def month_windows(start: str, end: str) -> List[Tuple[str, str]]:
    """Monthly [from, to] pairs, newest first, so a partial run still spans recent data."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out = []
    for m in pd.date_range(s.normalize().replace(day=1), e, freq="MS"):
        last = min(m + pd.offsets.MonthEnd(0), e)
        out.append((m.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")))
    return list(reversed(out))


def strike_labels(max_offset: int) -> List[str]:
    labels = ["ATM"]
    for i in range(1, max_offset + 1):
        labels += [f"ATM+{i}", f"ATM-{i}"]
    return labels


def slug(label: str) -> str:
    return label.replace("+", "p").replace("-", "m")


def fetch_chunk(client, under: str, sid: str, seg: str, label: str, side: str,
                frm: str, to: str) -> Tuple[str, int]:
    path = OUT_ROOT / f"underlying={under}" / f"strike={slug(label)}" / f"{side}_{frm[:7]}.parquet"
    if path.exists():
        return "CACHED", 0
    try:
        res = client.fetch_rolling_options(
            security_id=sid, exchange_segment=seg, from_date=frm, to_date=to,
            strike=label, drv_option_type="CALL" if side == "ce" else "PUT",
            interval="5")
    except Exception as exc:                                    # noqa: BLE001
        return f"ERROR:{type(exc).__name__}", 0
    df = res.get(side, pd.DataFrame())
    if df is None or df.empty:
        return "EMPTY", 0
    df = df.copy()
    df["underlying"] = under
    df["strike_label"] = label
    df["option_type"] = side.upper()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return "OK", int(len(df))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlyings", default="BANKNIFTY",
                    help="comma-separated; must be keys of UNDERLYINGS")
    ap.add_argument("--end", default="2026-09-18")
    ap.add_argument("--start", default=None,
                    help="defaults to each underlying's measured history floor")
    ap.add_argument("--max-offset", type=int, default=6,
                    help="ladder half-width; the endpoint caps at 10")
    ap.add_argument("--sleep", type=float, default=0.12)
    args = ap.parse_args()

    client = get_dhan_client()
    CATALOG.mkdir(parents=True, exist_ok=True)
    want = [u.strip().upper() for u in args.underlyings.split(",") if u.strip()]
    bad = [u for u in want if u not in UNDERLYINGS]
    if bad:
        raise SystemExit(f"unknown underlying(s): {bad}. known: {sorted(UNDERLYINGS)}")

    labels = strike_labels(min(args.max_offset, 10))
    ledger: List[Dict] = []
    for under in want:
        sid, seg, floor = UNDERLYINGS[under]
        start = max(args.start or floor, floor)
        windows = month_windows(start, args.end)
        total = len(windows) * len(labels) * 2
        print(f"\n=== {under} id={sid} seg={seg} floor={floor} -> "
              f"{len(windows)} months x {len(labels)} strikes x 2 sides = {total} requests",
              flush=True)
        tally, done, rows = {}, 0, 0
        # Strike-major: a partial run still covers the whole span at the strikes
        # nearest the money, which are the ones any trade actually needs.
        for label in labels:
            for frm, to in windows:
                for side in ("ce", "pe"):
                    st, n = fetch_chunk(client, under, sid, seg, label, side, frm, to)
                    key = st.split(":")[0]
                    tally[key] = tally.get(key, 0) + 1
                    rows += n
                    done += 1
                    if key not in ("OK", "CACHED"):
                        ledger.append({"underlying": under, "security_id": sid,
                                       "segment": seg, "strike": label, "side": side,
                                       "from": frm, "to": to, "status": st})
                    if done % 200 == 0:
                        print(f"  [{done}/{total}] {label} {side} {frm[:7]} {st} "
                              f"rows={rows:,} {tally}", flush=True)
                    if key != "CACHED":
                        time.sleep(args.sleep)
            print(f"  == {under} {label} done == {tally} rows={rows:,}", flush=True)
        print(f"{under} TALLY {tally} total_rows={rows:,}", flush=True)

    if ledger:
        p = CATALOG / "grid_multi_gaps.csv"
        pd.DataFrame(ledger).to_csv(p, index=False)
        print(f"\n{len(ledger)} non-OK chunks recorded -> {p}", flush=True)
    else:
        print("\nno gaps", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
