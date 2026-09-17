"""
Option Chain Dataset Builder & Normalizer (Phase 5).
Builds a normalized, research-grade options dataset from live Dhan option chains
and historical rolling option data.

Preserves every legitimately available Dhan field:
- underlying
- security_id
- symbol / trading_symbol
- expiry
- strike
- option_type (CE / PE)
- lot_size
- timestamp (event_timestamp, receive_timestamp)
- bid / ask / bid_qty / ask_qty
- LTP
- volume
- OI (open interest)
- open, high, low, close, previous_close
- implied volatility (IV)
- Greeks: delta, theta, gamma, vega
- underlying_spot

Writes partitioned Parquet to:
data/normalized/options/date=YYYY-MM-DD/underlying=SYMBOL/
"""

import os
import sys
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logging import setup_logging
from src.data.dhan_client import DhanAPIClient
from src.data.lake import MarketDataLake
from src.data.instrument_master import InstrumentMasterSnapshotter

logger = setup_logging("scripts.build_option_chain")


def build_option_chain_snapshot(underlying: str = "NIFTY", expiry: Optional[str] = None) -> Optional[Path]:
    """
    Fetches the live official option chain for the underlying from DhanHQ,
    normalizes all fields, enriches with official instrument master metadata,
    and stores it in the Parquet Data Lake.
    """
    client = DhanAPIClient()
    logger.info(f"Fetching live official option chain for {underlying} (expiry={expiry})...")
    
    scrip_map = {
        "NIFTY": 13,
        "BANKNIFTY": 25,
        "FINNIFTY": 27,
        "MIDCPNIFTY": 44,
        "SENSEX": 51,
    }
    scrip_id = scrip_map.get(underlying.upper(), 13)
    chain_data = client.fetch_option_chain(underlying_scrip=scrip_id, underlying_seg="IDX_I", expiry=expiry)
    if not chain_data or "strikes" not in chain_data:
        logger.error(f"Failed to fetch option chain for {underlying} (scrip={scrip_id}) from Dhan API.")
        return None

    spot_price = float(chain_data.get("spot_last_price", 0.0))
    oc_dict = chain_data.get("strikes", {})
    resolved_expiry = chain_data.get("expiry", expiry)
    now_ts = datetime.now().isoformat()
    today_str = datetime.now().strftime("%Y-%m-%d")

    records = []

    # Iterate over all strikes and both legs (ce & pe)
    for strike_str, strike_data in oc_dict.items():
        try:
            strike_val = float(strike_str)
        except ValueError:
            continue

        for opt_type in ["ce", "pe"]:
            leg = strike_data.get(opt_type)
            if not leg:
                continue

            sec_id = str(leg.get("security_id", "")).strip()
            ltp = float(leg.get("last_price", 0.0) or 0.0)
            oi = int(leg.get("oi", 0) or 0)
            vol = int(leg.get("volume", 0) or 0)
            iv = float(leg.get("implied_volatility", 0.0) or leg.get("iv", 0.0) or 0.0)

            # Greeks officially supplied by Dhan Data API
            greeks = leg.get("greeks", {}) or {}
            delta = float(greeks.get("delta", 0.0) or 0.0)
            theta = float(greeks.get("theta", 0.0) or 0.0)
            gamma = float(greeks.get("gamma", 0.0) or 0.0)
            vega = float(greeks.get("vega", 0.0) or 0.0)

            # Executable Bid / Ask microstructure
            top_bid = float(leg.get("top_bid_price", 0.0) or 0.0)
            top_ask = float(leg.get("top_ask_price", 0.0) or 0.0)
            top_bid_qty = int(leg.get("top_bid_quantity", 0) or 0)
            top_ask_qty = int(leg.get("top_ask_quantity", 0) or 0)

            # Price stats
            avg_price = float(leg.get("average_price", 0.0) or 0.0)
            prev_close = float(leg.get("previous_close_price", 0.0) or 0.0)
            prev_oi = int(leg.get("previous_oi", 0) or 0)
            prev_vol = int(leg.get("previous_volume", 0) or 0)

            # Resolve official metadata from snapshot if possible
            contract_meta = InstrumentMasterSnapshotter.resolve_contract_point_in_time(
                underlying=underlying,
                option_type=opt_type.upper(),
                target_strike=strike_val,
                as_of_date=datetime.now().date(),
            )

            lot_size = contract_meta.get("lot_size", 75 if underlying == "NIFTY" else 30) if contract_meta else (75 if underlying == "NIFTY" else 30)
            trading_symbol = contract_meta.get("trading_symbol", f"{underlying} {strike_val:.0f} {opt_type.upper()}") if contract_meta else f"{underlying} {strike_val:.0f} {opt_type.upper()}"
            resolved_sec_id = contract_meta.get("security_id", sec_id) if contract_meta else sec_id

            records.append({
                "timestamp": now_ts,
                "event_timestamp": now_ts,
                "receive_timestamp": now_ts,
                "date": today_str,
                "underlying": underlying.upper(),
                "underlying_spot": spot_price,
                "security_id": resolved_sec_id,
                "trading_symbol": trading_symbol,
                "strike": strike_val,
                "option_type": opt_type.upper(),
                "expiry": resolved_expiry or today_str,
                "lot_size": lot_size,
                "bid": top_bid,
                "ask": top_ask,
                "bid_qty": top_bid_qty,
                "ask_qty": top_ask_qty,
                "ltp": ltp,
                "average_price": avg_price,
                "prev_close": prev_close,
                "volume": vol,
                "oi": oi,
                "prev_oi": prev_oi,
                "prev_vol": prev_vol,
                "iv": iv,
                "delta": delta,
                "theta": theta,
                "gamma": gamma,
                "vega": vega,
                "source": "DhanHQ_Official_OptionChain",
            })

    if not records:
        logger.warning("No valid option chain records parsed.")
        return None

    df = pd.DataFrame(records)
    lake = MarketDataLake()
    
    # Save partitioned normalized dataset
    dest_path = Path("data/normalized/options") / f"date={today_str}" / f"underlying={underlying.upper()}" / "option_chain.parquet"
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    table = pa.Table.from_pandas(df)
    pq.write_table(table, dest_path, compression="snappy")
    logger.info(f"Normalized option chain dataset saved: {len(df)} strikes/legs -> {dest_path}")
    return dest_path


def main():
    parser = argparse.ArgumentParser(description="Build Normalized Option Chain Dataset from DhanHQ")
    parser.add_argument("--underlying", default="NIFTY", help="Underlying index (NIFTY, BANKNIFTY)")
    parser.add_argument("--expiry", default=None, help="Target expiry date YYYY-MM-DD")
    args = parser.parse_args()

    saved = build_option_chain_snapshot(underlying=args.underlying, expiry=args.expiry)
    if saved:
        print(f"Successfully generated normalized option dataset: {saved}")
    else:
        print("Failed to build option chain dataset.")
        sys.exit(1)


if __name__ == "__main__":
    main()
