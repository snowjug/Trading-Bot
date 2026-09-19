"""
Measure the HISTORY FLOOR of every Dhan intraday source, per underlying. READ-ONLY.

Three studies in this repository recorded "intraday work is NIFTY-only". With a live
token that is false: BANKNIFTY, FINNIFTY, MIDCPNIFTY and SENSEX all return 5-minute
option bars. What is NOT yet known is how far back each one goes, and that is what
decides whether a family is testable or merely fashionable.

This script answers, per underlying and per source:
  - the earliest month that returns rows          (probe month by month, coarse then fine)
  - the strike ladder width actually served
  - whether iv / oi / spot are populated at depth, not just recently
  - for futures: whether an EXPIRED contract serves intraday bars at all

Every result is recorded with the request that produced it, so a zero can be
distinguished from a failure. HTTP status is captured explicitly, because
`dhan_client._post` returns None on an error and a caller cannot otherwise tell 401
from "no data" — the exact confusion that made an expired token look like missing
BANKNIFTY history.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import Config

BASE = "https://api.dhan.co/v2"
OUT = Path("data/catalog")
MASTER = "data/raw/dhan/scrip_master/api-scrip-master.csv"

# (name, security_id, exchange_segment for F&O)
UNDERLYINGS = [
    ("NIFTY", "13", "NSE_FNO"),
    ("BANKNIFTY", "25", "NSE_FNO"),
    ("FINNIFTY", "27", "NSE_FNO"),
    ("MIDCPNIFTY", "442", "NSE_FNO"),
    ("NIFTYNXT50", "38", "NSE_FNO"),
    ("SENSEX", "51", "BSE_FNO"),
    ("BANKEX", "69", "BSE_FNO"),
]

REQ = ["open", "high", "low", "close", "volume", "oi", "iv", "spot", "strike"]


def headers() -> Dict[str, str]:
    return {"access-token": str(Config.DHAN_ACCESS_TOKEN).strip(),
            "client-id": str(Config.DHAN_CLIENT_ID).strip(),
            "Content-Type": "application/json", "Accept": "application/json"}


def post(ep: str, payload: dict, timeout: int = 60) -> Tuple[int, Any]:
    """Returns (http_status, parsed_json_or_text). Status is never hidden."""
    try:
        r = requests.post(f"{BASE}/{ep}", json=payload, headers=headers(), timeout=timeout)
    except Exception as exc:                                    # noqa: BLE001
        return -1, f"{type(exc).__name__}: {exc}"
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:300]


def rolling(sid: str, seg: str, frm: str, to: str, strike: str = "ATM",
            interval: str = "5", side: str = "CALL") -> Dict[str, Any]:
    st, body = post("charts/rollingoption", {
        "exchangeSegment": seg, "interval": interval, "securityId": str(sid),
        "instrument": "OPTIDX", "expiryFlag": "WEEK", "expiryCode": 1,
        "strike": strike, "drvOptionType": side, "requiredData": REQ,
        "fromDate": frm, "toDate": to})
    out: Dict[str, Any] = {"http": st}
    if st != 200 or not isinstance(body, dict):
        out["error"] = body if isinstance(body, str) else str(body)[:200]
        return out
    data = body.get("data", {}) or {}
    ce = data.get("ce") or {}
    if not isinstance(ce, dict) or not ce.get("timestamp"):
        out["rows"] = 0
        return out
    df = pd.DataFrame(ce)
    dt = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(
        "Asia/Kolkata").dt.tz_localize(None)
    out.update({
        "rows": int(len(df)), "sessions": int(dt.dt.date.nunique()),
        "first": str(dt.min()), "last": str(dt.max()),
        "strikes": int(df["strike"].nunique()) if "strike" in df else None,
        "iv_pop": round(float(pd.to_numeric(df.get("iv"), errors="coerce").notna().mean()), 3)
                  if "iv" in df else None,
        "oi_pop": round(float(pd.to_numeric(df.get("oi"), errors="coerce").gt(0).mean()), 3)
                  if "oi" in df else None,
        "spot_pop": round(float(pd.to_numeric(df.get("spot"), errors="coerce").gt(0).mean()), 3)
                    if "spot" in df else None,
    })
    return out


def find_floor(sid: str, seg: str, sleep: float,
               years: List[int]) -> Dict[str, Any]:
    """Coarse year scan, then month scan inside the first year that returns rows."""
    trail: List[Dict[str, Any]] = []
    first_year = None
    for y in years:
        r = rolling(sid, seg, f"{y}-06-01", f"{y}-06-25")
        trail.append({"probe": f"{y}-06", **{k: r.get(k) for k in ("http", "rows", "sessions")}})
        time.sleep(sleep)
        if r.get("rows", 0) > 0:
            first_year = y
            break
    if first_year is None:
        return {"floor": None, "trail": trail}
    # walk months backwards from June of that year into the previous year
    floor = f"{first_year}-06"
    probes = [(first_year, m) for m in (5, 4, 3, 2, 1)] + \
             [(first_year - 1, m) for m in (12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)]
    for y, m in probes:
        last = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
        r = rolling(sid, seg, f"{y}-{m:02d}-01", str(last.date()))
        trail.append({"probe": f"{y}-{m:02d}", **{k: r.get(k) for k in ("http", "rows", "sessions")}})
        time.sleep(sleep)
        if r.get("rows", 0) > 0:
            floor = f"{y}-{m:02d}"
        else:
            break
    return {"floor": floor, "trail": trail}


def probe_expired_future(sleep: float) -> Dict[str, Any]:
    """
    Does an EXPIRED futures contract serve intraday bars? If not, a long intraday
    futures history cannot be built from /charts/intraday and must come from
    somewhere else. This is the decisive question for the futures families.
    """
    m = pd.read_csv(MASTER, low_memory=False, dtype={"SEM_SMST_SECURITY_ID": str})
    fut = m[(m["SEM_INSTRUMENT_NAME"].astype(str).str.strip() == "FUTIDX")
            & (m["SEM_EXM_EXCH_ID"] == "NSE")].copy()
    fut["sym"] = fut["SEM_TRADING_SYMBOL"].astype(str).str.split("-").str[0]
    n = fut[fut["sym"] == "NIFTY"].sort_values("SEM_EXPIRY_DATE")
    out: Dict[str, Any] = {"listed_nifty_futures": int(len(n)), "probes": []}
    for _, row in n.iterrows():
        sid = str(row["SEM_SMST_SECURITY_ID"])
        st, body = post("charts/intraday", {
            "securityId": sid, "exchangeSegment": "NSE_FNO", "instrument": "FUTIDX",
            "interval": "5", "fromDate": "2026-06-01", "toDate": "2026-09-18"})
        rows = 0
        if st == 200 and isinstance(body, dict):
            d = body.get("data", body) or {}
            rows = len(d.get("timestamp", [])) if isinstance(d, dict) else 0
        out["probes"].append({"symbol": str(row["SEM_TRADING_SYMBOL"]),
                              "security_id": sid, "expiry": str(row["SEM_EXPIRY_DATE"]),
                              "http": st, "rows": rows})
        time.sleep(sleep)
    # an id below the current block is an older, now-expired contract
    for sid in ("55000", "60000", "65000"):
        st, body = post("charts/intraday", {
            "securityId": sid, "exchangeSegment": "NSE_FNO", "instrument": "FUTIDX",
            "interval": "5", "fromDate": "2025-01-01", "toDate": "2025-03-31"})
        rows = 0
        if st == 200 and isinstance(body, dict):
            d = body.get("data", body) or {}
            rows = len(d.get("timestamp", [])) if isinstance(d, dict) else 0
        out["probes"].append({"symbol": f"(unlisted id {sid})", "security_id": sid,
                              "expiry": None, "http": st, "rows": rows})
        time.sleep(sleep)
    # is there a rolling-futures analogue?
    st, body = post("charts/rollingoption", {
        "exchangeSegment": "NSE_FNO", "interval": "5", "securityId": "13",
        "instrument": "FUTIDX", "expiryFlag": "MONTH", "expiryCode": 1,
        "requiredData": ["open", "high", "low", "close", "volume", "oi"],
        "fromDate": "2026-08-01", "toDate": "2026-09-18"})
    out["rollingoption_with_FUTIDX"] = {"http": st,
                                        "body": str(body)[:220] if st != 200 else "200 OK"}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.55)
    ap.add_argument("--ladder", action="store_true",
                    help="also measure the strike ladder width at depth")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    res: Dict[str, Any] = {"probed_at": pd.Timestamp.now().isoformat(),
                           "token_exp": None, "rollingoption": {}, "futures": {}}

    print("=" * 104)
    print("ROLLING OPTION 5-MINUTE HISTORY FLOOR, per underlying")
    print("=" * 104)
    years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    for name, sid, seg in UNDERLYINGS:
        recent = rolling(sid, seg, "2026-09-01", "2026-09-18")
        time.sleep(args.sleep)
        if recent.get("rows", 0) == 0:
            print(f"{name:12} id={sid:5} seg={seg:8} NO RECENT DATA  http={recent.get('http')}"
                  f" {recent.get('error', '')[:70]}")
            res["rollingoption"][name] = {"security_id": sid, "segment": seg,
                                          "recent": recent, "floor": None}
            continue
        fl = find_floor(sid, seg, args.sleep, years)
        res["rollingoption"][name] = {"security_id": sid, "segment": seg,
                                       "recent": recent, **fl}
        print(f"{name:12} id={sid:5} seg={seg:8} floor={str(fl['floor']):8} "
              f"recent rows={recent['rows']} sessions={recent['sessions']} "
              f"strikes={recent['strikes']} iv={recent['iv_pop']} oi={recent['oi_pop']} "
              f"spot={recent['spot_pop']}")

    if args.ladder:
        print("\n" + "=" * 104)
        print("STRIKE LADDER ACTUALLY SERVED (recent month)")
        print("=" * 104)
        res["ladder"] = {}
        for name, sid, seg in UNDERLYINGS:
            if res["rollingoption"].get(name, {}).get("floor") is None:
                continue
            got = []
            for off in range(0, 13):
                lab = "ATM" if off == 0 else f"ATM+{off}"
                r = rolling(sid, seg, "2026-09-01", "2026-09-18", strike=lab)
                time.sleep(args.sleep)
                if r.get("rows", 0) > 0:
                    got.append(off)
                else:
                    break
            res["ladder"][name] = {"max_positive_offset": max(got) if got else None}
            print(f"{name:12} serves ATM .. ATM+{max(got) if got else '?'}")

    print("\n" + "=" * 104)
    print("FUTURES INTRADAY — can expired contracts be pulled?")
    print("=" * 104)
    f = probe_expired_future(args.sleep)
    res["futures"] = f
    for p in f["probes"]:
        print(f"  {p['symbol']:28} id={p['security_id']:7} exp={str(p['expiry'])[:10]:12} "
              f"http={p['http']} rows={p['rows']}")
    print(f"  rollingoption with instrument=FUTIDX -> {f['rollingoption_with_FUTIDX']}")

    with (OUT / "dhan_depth_probe.json").open("w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, default=str)
    print(f"\nwrote {OUT / 'dhan_depth_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
