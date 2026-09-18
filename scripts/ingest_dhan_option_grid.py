"""
Ingest authentic 5-minute NIFTY option bars from DhanHQ `/charts/rollingoption`.

WHY: Bots 5 and 6 enter and exit INTRADAY, so pricing them needs intraday option
bars. Only 10 sessions were previously cached, which is why their "real option
economics" rested on n=8 and n=3. Measured 2026-09-18 with a valid token, the
endpoint actually serves 5-minute bars back to 2020-09 — roughly six years.

MEASURED ENDPOINT LIMITS (read-only probes, 2026-09-18):
  * history floor   2020-09 returns data; 2019-09 returns empty
  * request window  one month; a quarter or longer returns empty
  * strike ceiling  ATM+/-10; ATM+/-11 and beyond return empty
  * option type     CALL populates `ce`, PUT populates `pe` — two separate calls

WHAT THIS IS: read-only market-data GET/POST against a documented chart endpoint.
No order, position or account endpoint is touched. Nothing is derived or invented:
a month the endpoint does not serve is simply absent.

THE ROLLING-ATM TRAP, carried downstream: the "ATM" series RE-ANCHORS as spot
moves, so one session can contain many different strikes under a single label. It
is a synthetic continuous index, NOT a tradable contract. That is exactly why this
script pulls the whole ATM+/-N ladder: stitching the ladder yields a real per-strike
history from which ONE fixed contract can be followed for the life of a trade.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from src.data.dhan_client import get_dhan_client

OUT = Path("data/raw/dhan/option_grid_5m")
HISTORY_FLOOR = "2020-09-01"          # measured; earlier months return empty


def month_windows(start: str, end: str):
    """Monthly [from, to] pairs, newest first — a partial run still yields a usable span."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    months = pd.date_range(s.normalize().replace(day=1), e, freq="MS")
    out = []
    for m in months:
        last = min(m + pd.offsets.MonthEnd(0), e)
        out.append((m.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")))
    return list(reversed(out))


def strike_labels(max_offset: int):
    labels = ["ATM"]
    for i in range(1, max_offset + 1):
        labels += [f"ATM+{i}", f"ATM-{i}"]
    return labels


def slug(label: str) -> str:
    return label.replace("+", "p").replace("-", "m")


def fetch_chunk(client, label: str, side: str, frm: str, to: str) -> str:
    """One (strike, side, month). Returns a status string; never raises."""
    path = OUT / f"strike={slug(label)}" / f"{side}_{frm[:7]}.parquet"
    if path.exists():
        return "CACHED"
    try:
        res = client.fetch_rolling_options(
            from_date=frm, to_date=to, strike=label,
            drv_option_type="CALL" if side == "ce" else "PUT",
            interval="5",
        )
    except Exception as exc:                                   # noqa: BLE001
        return f"ERROR:{type(exc).__name__}"
    df = res.get(side, pd.DataFrame())
    if df is None or df.empty:
        return "EMPTY"
    df = df.copy()
    df["strike_label"] = label
    df["option_type"] = side.upper()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return f"OK:{len(df)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=HISTORY_FLOOR)
    ap.add_argument("--end", default="2026-09-16")
    ap.add_argument("--max-offset", type=int, default=6,
                    help="strike ladder half-width; the endpoint caps at 10")
    ap.add_argument("--sleep", type=float, default=0.12)
    args = ap.parse_args()

    client = get_dhan_client()
    windows = month_windows(max(args.start, HISTORY_FLOOR), args.end)
    labels = strike_labels(min(args.max_offset, 10))
    total = len(windows) * len(labels) * 2
    print(f"months={len(windows)} strikes={len(labels)} sides=2 -> {total} requests", flush=True)

    tally, done = {}, 0
    # Strike-major so a partial run still covers the full date span at the strikes
    # nearest the money, which are the ones a trade is most likely to need.
    for label in labels:
        for frm, to in windows:
            for side in ("ce", "pe"):
                st = fetch_chunk(client, label, side, frm, to)
                key = st.split(":")[0]
                tally[key] = tally.get(key, 0) + 1
                done += 1
                if done % 100 == 0:
                    print(f"[{done}/{total}] {label} {side} {frm[:7]} {st}  {tally}", flush=True)
                if key != "CACHED":
                    time.sleep(args.sleep)
        print(f"  == {label} complete == {tally}", flush=True)
    print("TALLY", tally, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
