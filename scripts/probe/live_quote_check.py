import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
from datetime import datetime
from src.data.dhan_client import get_dhan_client
from src.execution.dhan_contract_resolver import DhanContractResolver

c = get_dhan_client()
idx = c.fetch_marketfeed_quote([13, 21], exchange_segment="IDX_I")
print("=== INDEX ===")
for k, v in idx.items():
    print(f"  {k}: ltp={v.get('ltp')} ts={v.get('market_timestamp')}")

spot = float(idx.get("13", {}).get("ltp") or 0)
vix  = float(idx.get("21", {}).get("ltp") or 0)
print(f"\nNIFTY={spot}  VIX={vix}")

if spot > 0 and vix > 0:
    for ot in ("CE", "PE"):
        ct = DhanContractResolver.resolve_option_contract(spot, vix, ot, strike_offset_steps=0)
        if ct:
            print(f"\n=== {ot} ATM ===")
            for f in ("custom_symbol","security_id","strike","expiry","lot_size",
                      "bid","ask","ltp","quote_timestamp"):
                print(f"  {f:16s} {ct.get(f)}")
        else:
            print(f"\n{ot}: resolver returned None")
