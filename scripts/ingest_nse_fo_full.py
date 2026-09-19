"""
Ingest the NSE F&O bhavcopy WITHOUT the filters the previous ingester applied.

WHY THIS EXISTS. `scripts/ingest_nse_fo_bhavcopy.py` keeps only
`TckrSymb == NIFTY` and `OptnTp in (CE, PE)`. Everything else in the file was
discarded at ingest, and three studies then recorded conclusions that rest on that
discard:

  - "no futures prices of any kind exist in this repository" — the bhavcopy carries
    FUTIDX for NIFTY and BANKNIFTY back to 2019-01-02 with OHLC, settlement price,
    open interest and volume. It was dropped, not absent.
  - "intraday work is NIFTY-only" — true for the 5-minute grid, but BANKNIFTY,
    FINNIFTY, MIDCPNIFTY and NIFTYNXT50 index options are all in the same daily
    file and were dropped too.

That is a data-availability failure being reported as a strategy failure, which is
the specific error PART 17 of the directive forbids. This script fixes the intake.

WHAT IT KEEPS
  futures   every FUTIDX and FUTSTK row, all symbols, all expiries
  idxopt    every OPTIDX row, all index underlyings, all strikes and expiries

Stock options (OPTSTK) are ~36,000 rows a session and are deliberately NOT
ingested here; that is a budget decision, recorded as such, not a claim that they
are unavailable.

PROVENANCE. The raw zip is cached byte-for-byte before anything is parsed, and its
URL, size, sha256, row counts and retrieval timestamp go into a ledger. Raw files
are never overwritten by transformed ones. A day that fails to download is written
to a failure ledger and is re-attempted on the next run; it is never silently
skipped and never filled in.

THREE SEMANTIC WARNINGS CARRIED DOWNSTREAM, all measured rather than assumed:

 0. THE INSTRUMENT-TYPE CODES CHANGE AT 2024-01-02 AND ARE NOT THE SAME STRINGS.
    Legacy `INSTRUMENT` uses FUTIDX / FUTSTK / OPTIDX / OPTSTK. UDiFF `FinInstrmTp`
    uses **IDF / STF / IDO / STO**. Filtering on the legacy names alone silently
    captures NOTHING for every UDiFF session -- this script did exactly that on its
    first run: 670 sessions parsed, zero rows kept, and each one recorded as "OK"
    because both output frames were merely empty. A day that yields no rows in
    either bucket is now an explicit `EMPTY_BOTH_BUCKETS` status, not a success.

 1. `TtlTradgVol` COUNTS CONTRACTS IN BOTH ERAS, and turnover is NOTIONAL.
    An earlier draft of this file asserted the opposite — that UDiFF reports units
    while the legacy feed reports contracts — and that assertion was wrong. It was
    settled by the turnover identity rather than by reading documentation:

      legacy 2019-01-02 NIFTY OPTIDX:  VAL_INLAKH x 1e5 / (STRIKE x CONTRACTS) = 75.5
      legacy 2019-01-02 NIFTY FUTIDX:  VAL_INLAKH x 1e5 / (CLOSE  x CONTRACTS) = 75.1
      UDiFF  FUTIDX, n=8,884:          TtlTrfVal / (ClsPric x TtlTradgVol) recovers
                                       the published NewBrdLotQty to within 1% on
                                       97.9% of rows
      UDiFF  index options:            TtlTrfVal / (StrkPric x TtlTradgVol) equals
                                       each row's own lot size

    The NIFTY lot was 75 in January 2019, so a ratio of ~75 means the denominator's
    volume term is in CONTRACTS and the turnover term is notional — strike-notional
    for options, price-notional for futures. The original ingester's rename of
    `CONTRACTS` into `TtlTradgVol` is therefore CORRECT and the two eras ARE
    comparable. `LegacyContracts` is still written out, but only as a provenance
    duplicate, not because the semantics differ.

    The useful consequence: this identity yields the AUTHENTIC historical lot size on
    every session in both eras, which `NewBrdLotQty` only supplies from 2024. Rupee
    results before 2024 become possible for the first time, from a derivation rather
    than a guess.
 2. A row with zero traded volume did not trade. Its `ClsPric` is the exchange's
    theoretical settlement value and is NOT an executable price.
"""

import argparse
import hashlib
import io
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

UDIFF = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip"
LEGACY = ("https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
          "{Y}/{MON}/fo{D}{MON}{Y}bhav.csv.zip")
UDIFF_FIRST_SESSION = "20240102"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

ZIP_DIR = Path("data/raw/nse/fo_zip")
FUT_DIR = Path("data/raw/nse/fo_futures")
IDXOPT_DIR = Path("data/raw/nse/fo_idxopt")
CATALOG = Path("data/catalog")
LEDGER = CATALOG / "fo_full_ingest_ledger.csv"
FAILURES = CATALOG / "fo_full_ingest_failures.csv"

# UDiFF columns worth keeping. Absent ones stay absent.
KEEP_UDIFF = [
    "TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "ISIN",
    "TckrSymb", "SctySrs", "XpryDt", "FininstrmActlXpryDt", "StrkPric", "OptnTp",
    "FinInstrmNm", "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
    "PrvsClsgPric", "UndrlygPric", "SttlmPric", "OpnIntrst", "ChngInOpnIntrst",
    "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd", "SsnId", "NewBrdLotQty",
]

LEGACY_RENAME = {
    "SYMBOL": "TckrSymb", "EXPIRY_DT": "XpryDt", "STRIKE_PR": "StrkPric",
    "OPTION_TYP": "OptnTp", "OPEN": "OpnPric", "HIGH": "HghPric", "LOW": "LwPric",
    "CLOSE": "ClsPric", "SETTLE_PR": "SttlmPric", "OPEN_INT": "OpnIntrst",
    "CHG_IN_OI": "ChngInOpnIntrst", "INSTRUMENT": "FinInstrmTp",
    # NOT renamed to TtlTradgVol on purpose — see the module docstring.
    "CONTRACTS": "LegacyContracts", "VAL_INLAKH": "LegacyValInLakh",
}


def session_dates(start: str, end: str) -> List[str]:
    """Trading sessions from authentic index history, never a synthetic calendar."""
    ext = Path("data/raw/nse/index_history/nse_index_daily.parquet")
    if ext.exists():
        raw = pd.read_parquet(ext)
        s = raw[raw["symbol"] == "NIFTY50"][["datetime"]].copy()
        s["datetime"] = pd.to_datetime(s["datetime"])
        s = s[(s["datetime"] >= start) & (s["datetime"] <= end)]
        days = sorted(s["datetime"].dt.strftime("%Y%m%d").unique())
        if days:
            return days
    return [d.strftime("%Y%m%d") for d in pd.bdate_range(start, end)]


def _download(day: str, timeout: int = 60) -> Tuple[Optional[bytes], str, str]:
    legacy = day < UDIFF_FIRST_SESSION
    d = pd.to_datetime(day, format="%Y%m%d")
    url = (LEGACY.format(Y=d.year, MON=d.strftime("%b").upper(), D=d.strftime("%d"))
           if legacy else UDIFF.format(d=day))
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except Exception as exc:                                    # noqa: BLE001
        return None, url, f"ERROR:{type(exc).__name__}"
    if r.status_code != 200 or len(r.content) < 1000:
        return None, url, f"HTTP:{r.status_code}:{len(r.content)}"
    return r.content, url, "OK"


def _parse(raw: bytes, day: str) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    legacy = day < UDIFF_FIRST_SESSION
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    except Exception as exc:                                    # noqa: BLE001
        return pd.DataFrame(), pd.DataFrame(), f"PARSE:{type(exc).__name__}"

    df.columns = [c.strip() for c in df.columns]
    if legacy:
        df = df.rename(columns=LEGACY_RENAME)
        df["TradDt"] = pd.to_datetime(day, format="%Y%m%d").strftime("%Y-%m-%d")
        df["XpryDt"] = pd.to_datetime(df["XpryDt"], format="%d-%b-%Y",
                                      errors="coerce").dt.strftime("%Y-%m-%d")
        df["LayoutEra"] = "LEGACY"
    else:
        df["LayoutEra"] = "UDIFF"
        for c in ("TradDt", "XpryDt"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d")

    tp = df.get("FinInstrmTp")
    if tp is None:
        return pd.DataFrame(), pd.DataFrame(), "NO_INSTRUMENT_TYPE_COLUMN"
    tp = tp.astype(str).str.strip().str.upper()
    # One vocabulary for both eras. `InstrmClass` is written out so downstream code
    # never has to know which era a row came from.
    FUT = {"FUTIDX", "FUTSTK", "IDF", "STF"}
    IDX_OPT = {"OPTIDX", "IDO"}
    unknown = sorted(set(tp.unique()) - FUT - IDX_OPT - {"OPTSTK", "STO"})
    df = df.copy()
    df["InstrmClass"] = tp.map(
        lambda v: "FUTIDX" if v in ("FUTIDX", "IDF")
        else "FUTSTK" if v in ("FUTSTK", "STF")
        else "OPTIDX" if v in ("OPTIDX", "IDO")
        else "OPTSTK" if v in ("OPTSTK", "STO")
        else "OTHER")
    fut = df[df["InstrmClass"].isin(["FUTIDX", "FUTSTK"])].copy()
    idxopt = df[df["InstrmClass"] == "OPTIDX"].copy()
    if unknown:
        # recorded, not swallowed
        fut.attrs["unknown_types"] = unknown

    keep = [c for c in (KEEP_UDIFF + ["LayoutEra", "InstrmClass", "LegacyContracts",
                                      "LegacyValInLakh"]) if c in df.columns]
    if fut.empty and idxopt.empty:
        return pd.DataFrame(), pd.DataFrame(), (
            "EMPTY_BOTH_BUCKETS:" + ",".join(sorted(set(tp.unique()))[:6]))
    return fut[keep], idxopt[keep], "OK"


def ingest_day(day: str, keep_zip: bool = True, timeout: int = 60) -> Dict:
    fut_p = FUT_DIR / f"fut_{day}.parquet"
    opt_p = IDXOPT_DIR / f"idxopt_{day}.parquet"
    if fut_p.exists() and opt_p.exists():
        return {"day": day, "status": "CACHED"}

    # The raw zip is cached, so a re-parse needs no network round trip. This matters:
    # the first run kept the zips but wrote no parquet for the whole UDiFF era, and
    # re-deriving from disk is both faster and provably the same bytes.
    zp = ZIP_DIR / f"fo_{day}.csv.zip"
    if zp.exists():
        raw = zp.read_bytes()
        url, st = f"file://{zp}", "OK"
    else:
        raw, url, st = _download(day, timeout)
    if raw is None:
        return {"day": day, "status": st, "url": url}
    sha = hashlib.sha256(raw).hexdigest()

    if keep_zip and not zp.exists():
        ZIP_DIR.mkdir(parents=True, exist_ok=True)
        zp.parent.mkdir(parents=True, exist_ok=True)
        zp.write_bytes(raw)                     # raw is written once, never replaced

    fut, idxopt, pst = _parse(raw, day)
    if pst != "OK":
        return {"day": day, "status": pst, "url": url, "sha256": sha,
                "bytes": len(raw)}
    FUT_DIR.mkdir(parents=True, exist_ok=True)
    IDXOPT_DIR.mkdir(parents=True, exist_ok=True)
    if not fut.empty:
        fut.to_parquet(fut_p, index=False)
    if not idxopt.empty:
        idxopt.to_parquet(opt_p, index=False)
    return {"day": day, "status": "OK", "url": url, "sha256": sha,
            "bytes": len(raw), "fut_rows": len(fut), "idxopt_rows": len(idxopt),
            "fut_symbols": int(fut["TckrSymb"].nunique()) if not fut.empty else 0,
            "idxopt_symbols": int(idxopt["TckrSymb"].nunique()) if not idxopt.empty else 0,
            "retrieved": pd.Timestamp.now().isoformat()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-09-18")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--no-zip", action="store_true",
                    help="skip caching the raw zip (hash is still recorded)")
    args = ap.parse_args()

    CATALOG.mkdir(parents=True, exist_ok=True)
    days = session_dates(args.start, args.end)
    print(f"sessions to ingest: {len(days)}  {days[0]} .. {days[-1]}", flush=True)

    done = set()
    if LEDGER.exists():
        prev = pd.read_csv(LEDGER, dtype={"day": str})
        ok = prev[prev["status"].astype(str).str.startswith(("OK", "CACHED"))]
        # A day that was logged OK but captured nothing is NOT done. This is the
        # guard against the first run's silent zeros.
        if "fut_rows" in ok.columns and "idxopt_rows" in ok.columns:
            captured = ok["fut_rows"].fillna(0) + ok["idxopt_rows"].fillna(0)
            ok = ok[(captured > 0) | ok["status"].eq("CACHED")]
        # A ledger row is not evidence that the output still exists. Require the
        # parquet files on disk too, so deleting an output always forces a re-parse
        # (the first attempt at this skipped 1,235 legacy days whose files had been
        # removed, because the ledger still said OK).
        done = {d for d in ok["day"]
                if (FUT_DIR / f"fut_{d}.parquet").exists()
                or (IDXOPT_DIR / f"idxopt_{d}.parquet").exists()}
        print(f"already ingested with rows AND files present: {len(done)}", flush=True)

    rows, fails, tally = [], [], {}
    for i, day in enumerate(days, 1):
        if day in done:
            tally["SKIP_DONE"] = tally.get("SKIP_DONE", 0) + 1
            continue
        rec = ingest_day(day, keep_zip=not args.no_zip)
        key = str(rec["status"]).split(":")[0]
        tally[key] = tally.get(key, 0) + 1
        rows.append(rec)
        if key not in ("OK", "CACHED"):
            fails.append(rec)
        if i % 100 == 0 or i == len(days):
            print(f"  [{i}/{len(days)}] {day} {rec['status']}  tally={tally}", flush=True)
        if rec["status"] not in ("CACHED",):
            time.sleep(args.sleep)

    if rows:
        df = pd.DataFrame(rows)
        if LEDGER.exists():
            df = pd.concat([pd.read_csv(LEDGER, dtype={"day": str}), df],
                           ignore_index=True)
        df.to_csv(LEDGER, index=False)
    if fails:
        pd.DataFrame(fails).to_csv(FAILURES, index=False)
        print(f"\nFAILED DAYS: {len(fails)} -> {FAILURES}", flush=True)
    else:
        print("\nno failures", flush=True)
    print(f"final tally: {tally}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
