"""
Probe what DhanHQ actually serves, per underlying and per endpoint. READ-ONLY.

PURPOSE. Three studies in this repository concluded that intraday work is
"NIFTY-only" and that no futures data exists. Neither claim was ever tested against
the API for any underlying other than NIFTY. This script measures coverage instead
of assuming it, so that PART 17's distinction — UNTESTABLE versus FAILED — can be
made on evidence.

Security IDs are resolved from the official scrip master
(data/raw/dhan/scrip_master/api-scrip-master.csv, sha256 recorded in
data/catalog/scrip_master_provenance.json), never guessed.

Endpoints touched, all non-mutating:
  optionchain/expirylist    active expiries
  charts/historical         daily candles for an index / a listed contract
  charts/intraday           intraday candles for an index / a listed contract
  charts/rollingoption      continuous expired-option bars, per ATM offset

Nothing is written except the coverage report and raw probe responses.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.data.dhan_client import get_dhan_client

MASTER = "data/raw/dhan/scrip_master/api-scrip-master.csv"
OUT = Path("data/catalog")

# Index underlyings that carry listed OPTIDX contracts, per the scrip master.
INDEX_UNDERLYINGS = [
    ("NIFTY", "13", "NSE", "IDX_I"),
    ("BANKNIFTY", "25", "NSE", "IDX_I"),
    ("FINNIFTY", "27", "NSE", "IDX_I"),
    ("MIDCPNIFTY", "442", "NSE", "IDX_I"),
    ("NIFTYNXT50", "38", "NSE", "IDX_I"),
    ("SENSEX", "51", "BSE", "IDX_I"),
    ("BANKEX", "69", "BSE", "IDX_I"),
]


def master() -> pd.DataFrame:
    d = pd.read_csv(MASTER, low_memory=False, dtype={"SEM_SMST_SECURITY_ID": str})
    d["SEM_INSTRUMENT_NAME"] = d["SEM_INSTRUMENT_NAME"].astype(str).str.strip()
    return d


def probe_expirylist(c, name: str, sid: str) -> Dict[str, Any]:
    try:
        e = c.fetch_expiry_list(int(sid), "IDX_I")
        return {"ok": bool(e), "n": len(e), "first": e[0] if e else None,
                "last": e[-1] if e else None}
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def probe_daily(c, sid: str, seg: str, instrument: str,
                frm: str, to: str) -> Dict[str, Any]:
    try:
        df = c.fetch_historical_daily(security_id=str(sid), exchange_segment=seg,
                                      instrument=instrument, from_date=frm, to_date=to)
        if df is None or len(df) == 0:
            return {"rows": 0}
        return {"rows": int(len(df)),
                "first": str(pd.to_datetime(df["datetime"]).min().date()),
                "last": str(pd.to_datetime(df["datetime"]).max().date()),
                "cols": list(df.columns)}
    except Exception as exc:                                    # noqa: BLE001
        return {"rows": 0, "error": f"{type(exc).__name__}: {exc}"}


def probe_intraday(c, sid: str, seg: str, instrument: str, frm: str, to: str,
                   interval: str = "5") -> Dict[str, Any]:
    try:
        df = c.fetch_intraday_candles(security_id=str(sid), exchange_segment=seg,
                                      instrument=instrument, from_date=frm,
                                      to_date=to, interval=interval)
        if df is None or len(df) == 0:
            return {"rows": 0}
        dt = pd.to_datetime(df["datetime"])
        return {"rows": int(len(df)), "first": str(dt.min()), "last": str(dt.max()),
                "sessions": int(dt.dt.date.nunique()), "cols": list(df.columns)}
    except Exception as exc:                                    # noqa: BLE001
        return {"rows": 0, "error": f"{type(exc).__name__}: {exc}"}


def probe_rolling(c, sid: str, frm: str, to: str, strike: str = "ATM",
                  interval: str = "5", expiry_flag: str = "WEEK") -> Dict[str, Any]:
    try:
        r = c.fetch_rolling_options(security_id=str(sid), strike=strike,
                                    from_date=frm, to_date=to, interval=interval,
                                    expiry_flag=expiry_flag)
        out = {}
        for side in ("ce", "pe"):
            df = r.get(side)
            if df is None or len(df) == 0:
                out[side] = {"rows": 0}
                continue
            dt = pd.to_datetime(df["datetime"])
            out[side] = {"rows": int(len(df)), "sessions": int(dt.dt.date.nunique()),
                         "first": str(dt.min()), "last": str(dt.max()),
                         "cols": list(df.columns),
                         "strikes": int(df["strike"].nunique()) if "strike" in df else None,
                         "has_iv": bool("iv" in df.columns and df["iv"].notna().any()),
                         "has_oi": bool("oi" in df.columns and df["oi"].notna().any())}
        return out
    except Exception as exc:                                    # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.6)
    ap.add_argument("--deep", action="store_true",
                    help="also bisect the rolling-option history floor per underlying")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    c = get_dhan_client()
    m = master()
    res: Dict[str, Any] = {"probed_at": pd.Timestamp.now().isoformat(),
                           "underlyings": {}, "futures": {}, "notes": []}

    print("=" * 100)
    print("INDEX UNDERLYINGS — expiry list, daily, intraday, rolling options")
    print("=" * 100)
    recent_to = date(2026, 9, 18)
    recent_frm = recent_to - timedelta(days=25)

    for name, sid, exch, seg in INDEX_UNDERLYINGS:
        rec: Dict[str, Any] = {"security_id": sid, "exchange": exch}
        rec["expirylist"] = probe_expirylist(c, name, sid); time.sleep(args.sleep)
        rec["daily_index"] = probe_daily(c, sid, "IDX_I", "INDEX",
                                         "2019-01-01", "2026-09-18"); time.sleep(args.sleep)
        rec["intraday_index"] = probe_intraday(c, sid, "IDX_I", "INDEX",
                                               str(recent_frm), str(recent_to)); time.sleep(args.sleep)
        rec["rolling_recent"] = probe_rolling(c, sid, str(recent_frm), str(recent_to)); time.sleep(args.sleep)
        rec["rolling_2021"] = probe_rolling(c, sid, "2021-06-01", "2021-06-25"); time.sleep(args.sleep)
        res["underlyings"][name] = rec

        d, i = rec["daily_index"], rec["intraday_index"]
        rr = rec["rolling_recent"].get("ce", {}) if "error" not in rec["rolling_recent"] else {}
        r21 = rec["rolling_2021"].get("ce", {}) if "error" not in rec["rolling_2021"] else {}
        print(f"\n{name:12} id={sid:5} exch={exch}")
        print(f"  expirylist    {rec['expirylist']}")
        print(f"  daily INDEX   rows={d.get('rows')} {d.get('first')} -> {d.get('last')}"
              f" {('err=' + d['error']) if d.get('error') else ''}")
        print(f"  intraday 5m   rows={i.get('rows')} sessions={i.get('sessions')}"
              f" {('err=' + i['error']) if i.get('error') else ''}")
        print(f"  rollingopt now  CE rows={rr.get('rows')} sessions={rr.get('sessions')}"
              f" strikes={rr.get('strikes')} iv={rr.get('has_iv')} oi={rr.get('has_oi')}")
        print(f"  rollingopt 2021 CE rows={r21.get('rows')} sessions={r21.get('sessions')}")

    print("\n" + "=" * 100)
    print("INDEX FUTURES — can a listed FUTIDX contract be pulled daily and intraday?")
    print("=" * 100)
    fut = m[(m["SEM_INSTRUMENT_NAME"] == "FUTIDX") & (m["SEM_EXM_EXCH_ID"] == "NSE")].copy()
    fut["sym"] = fut["SEM_TRADING_SYMBOL"].astype(str).str.split("-").str[0]
    for sym in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"):
        g = fut[fut["sym"] == sym]
        if g.empty:
            res["futures"][sym] = {"listed": 0}
            print(f"{sym:12} no listed FUTIDX contract in the master")
            continue
        g = g.sort_values("SEM_EXPIRY_DATE")
        row = g.iloc[0]
        sid = str(row["SEM_SMST_SECURITY_ID"])
        rec = {"listed": int(len(g)), "probe_security_id": sid,
               "probe_symbol": str(row["SEM_TRADING_SYMBOL"]),
               "expiry": str(row["SEM_EXPIRY_DATE"]),
               "lot": float(row["SEM_LOT_UNITS"])}
        rec["daily"] = probe_daily(c, sid, "NSE_FNO", "FUTIDX",
                                   "2019-01-01", "2026-09-18"); time.sleep(args.sleep)
        rec["intraday"] = probe_intraday(c, sid, "NSE_FNO", "FUTIDX",
                                         str(recent_frm), str(recent_to)); time.sleep(args.sleep)
        res["futures"][sym] = rec
        print(f"{sym:12} listed={rec['listed']} probe={rec['probe_symbol']} "
              f"id={sid} lot={rec['lot']}")
        print(f"  daily    rows={rec['daily'].get('rows')} {rec['daily'].get('first')}"
              f" -> {rec['daily'].get('last')} {('err=' + rec['daily']['error']) if rec['daily'].get('error') else ''}")
        print(f"  intraday rows={rec['intraday'].get('rows')} sessions={rec['intraday'].get('sessions')}"
              f" {('err=' + rec['intraday']['error']) if rec['intraday'].get('error') else ''}")

    with (OUT / "dhan_universe_probe.json").open("w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, default=str)
    print(f"\nwrote {OUT / 'dhan_universe_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
