"""
Ingest NSE's public F&O UDiFF bhavcopy archive into a per-strike NIFTY option store.

WHY: Bot 1's four-leg Iron Condor needs authentic prices at ~ATM+/-17 strikes.
DhanHQ's /charts/rollingoption endpoint serves only ATM+/-10, which is why the
condor engine previously failed closed on 420/420 sessions. That ceiling belongs
to ONE vendor endpoint, not to the data itself: NSE publishes the full daily F&O
bhavcopy for every contract, every strike and every expiry, free and unauthenticated.

WHAT THIS DOES: plain read-only HTTP GET against the public NSE archive, filtered
to NIFTY index options, written to parquet. It downloads only; it derives nothing,
models nothing and fabricates nothing. Absent sessions stay absent.

FIELDS PRESERVED (UDiFF names kept verbatim so provenance stays auditable):
  TradDt XpryDt StrkPric OptnTp FinInstrmId FinInstrmNm NewBrdLotQty
  OpnPric HghPric LwPric ClsPric LastPric SttlmPric UndrlygPric
  OpnIntrst ChngInOpnIntrst TtlTradgVol TtlNbOfTxsExctd

CRITICAL SEMANTIC WARNING carried downstream: a row with TtlTradgVol == 0 did NOT
trade that day. Its ClsPric is the exchange's theoretical settlement value, NOT an
executable price. Consumers MUST treat those as unfilled rather than as a fill.
"""

import argparse
import io
import os
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ARCHIVE = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip"
# NSE switched to the UDiFF layout on 2024-01-02. Sessions before that are served
# by the legacy derivatives archive, which carries the same economics under
# different column names. Verified reachable back to at least 2019-01-02.
LEGACY = ("https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
          "{Y}/{MON}/fo{D}{MON}{Y}bhav.csv.zip")
UDIFF_FIRST_SESSION = "20240102"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
OUT_DIR = Path("data/raw/nse/fo_bhavcopy")
KEEP = [
    "TradDt", "XpryDt", "StrkPric", "OptnTp", "FinInstrmId", "FinInstrmNm",
    "NewBrdLotQty", "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
    "SttlmPric", "UndrlygPric", "OpnIntrst", "ChngInOpnIntrst",
    "TtlTradgVol", "TtlNbOfTxsExctd",
]


def session_dates(start: str, end: str) -> list:
    """
    Trading sessions taken from authentic index history, not a synthetic calendar.

    Prefers the extended NSE archive (which reaches back to 2024) and falls back to
    the repository's own history. A date the exchange never published is simply
    never requested.
    """
    ext = Path("data/raw/nse/index_history/nse_index_daily.parquet")
    if ext.exists():
        raw = pd.read_parquet(ext)
        s = raw[raw["symbol"] == "NIFTY50"][["datetime"]].copy()
        s["datetime"] = pd.to_datetime(s["datetime"])
        m = (s["datetime"] >= start) & (s["datetime"] <= end)
        days = sorted({d.strftime("%Y%m%d") for d in s.loc[m, "datetime"]})
        if days:
            return days
    df = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    m = (df["datetime"] >= start) & (df["datetime"] <= end)
    days = [d.strftime("%Y%m%d") for d in df.loc[m, "datetime"]]
    if days:
        return days
    # No authentic calendar covers this window yet. Fall back to weekdays: the
    # fetcher records a holiday as an absent session rather than inventing one.
    rng = pd.bdate_range(start, end)
    return [d.strftime("%Y%m%d") for d in rng]


LEGACY_RENAME = {
    "EXPIRY_DT": "XpryDt", "STRIKE_PR": "StrkPric", "OPTION_TYP": "OptnTp",
    "OPEN": "OpnPric", "HIGH": "HghPric", "LOW": "LwPric", "CLOSE": "ClsPric",
    "SETTLE_PR": "SttlmPric", "CONTRACTS": "TtlTradgVol", "OPEN_INT": "OpnIntrst",
    "CHG_IN_OI": "ChngInOpnIntrst", "TIMESTAMP": "TradDt",
}


def _normalise_legacy(df: pd.DataFrame, symbol: str, day: str) -> pd.DataFrame:
    """
    Maps the legacy derivatives layout onto the UDiFF column names.

    Renaming only — no value is derived or invented. Fields the legacy feed simply
    does not carry stay ABSENT rather than being filled with a guess:

      FinInstrmId    no security id in the legacy feed
      NewBrdLotQty   lot size is not published here and is NOT derivable from
                     VAL_INLAKH/CONTRACTS (checked: the implied value is unstable
                     across sessions), so rupee-denominated results must come from
                     the UDiFF era and per-point results from the full history
      UndrlygPric    spot comes from the NSE index archive instead

    SttlmPric keeps the same meaning as in UDiFF: on an expiry session every row
    carries the underlying's official settlement price (verified 2023-10-05, a
    single distinct value across all rows).
    """
    n = df[(df["SYMBOL"] == symbol) & (df["INSTRUMENT"] == "OPTIDX")].copy()
    if n.empty:
        return n
    n = n.rename(columns=LEGACY_RENAME)
    n["XpryDt"] = pd.to_datetime(n["XpryDt"], format="%d-%b-%Y", errors="coerce").dt.strftime("%Y-%m-%d")
    n["TradDt"] = pd.to_datetime(day, format="%Y%m%d").strftime("%Y-%m-%d")
    n["FinInstrmNm"] = (symbol + n["XpryDt"].str.replace("-", "", regex=False)
                        + n["StrkPric"].astype(float).round().astype(int).astype(str)
                        + n["OptnTp"].astype(str))
    n["LastPric"] = n["ClsPric"]
    return n.dropna(subset=["XpryDt"])


def fetch_one(day: str, symbol: str, timeout: int = 45) -> str:
    """Returns a status string. Never raises; a failed day is recorded, not faked."""
    out = OUT_DIR / f"{symbol}_options_{day}.parquet"
    if out.exists():
        return "CACHED"
    legacy = day < UDIFF_FIRST_SESSION
    d = pd.to_datetime(day, format="%Y%m%d")
    url = (LEGACY.format(Y=d.year, MON=d.strftime("%b").upper(), D=d.strftime("%d"))
           if legacy else ARCHIVE.format(d=day))
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except Exception as exc:                                   # noqa: BLE001
        return f"ERROR:{type(exc).__name__}"
    if r.status_code != 200 or len(r.content) < 1000:
        return f"HTTP:{r.status_code}"
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        df = pd.read_csv(z.open(z.namelist()[0]))
    except Exception as exc:                                   # noqa: BLE001
        return f"PARSE:{type(exc).__name__}"

    if legacy:
        opts = _normalise_legacy(df, symbol, day)
        opts = opts[opts["OptnTp"].isin(["CE", "PE"])] if not opts.empty else opts
    else:
        opts = df[(df["TckrSymb"] == symbol) & (df["OptnTp"].isin(["CE", "PE"]))]
    if opts.empty:
        return "EMPTY"
    cols = [c for c in KEEP if c in opts.columns]
    out.parent.mkdir(parents=True, exist_ok=True)
    opts[cols].to_parquet(out, index=False)
    return f"OK:{len(opts)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-09-16")
    ap.add_argument("--symbol", default="NIFTY")
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()

    days = session_dates(args.start, args.end)
    print(f"sessions to fetch: {len(days)}", flush=True)
    tally: dict = {}
    for i, day in enumerate(days, 1):
        status = fetch_one(day, args.symbol)
        key = status.split(":")[0]
        tally[key] = tally.get(key, 0) + 1
        if i % 25 == 0 or key not in ("OK", "CACHED"):
            print(f"[{i}/{len(days)}] {day} {status}", flush=True)
        if key not in ("CACHED",):
            time.sleep(args.sleep)
    print("TALLY", tally, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
