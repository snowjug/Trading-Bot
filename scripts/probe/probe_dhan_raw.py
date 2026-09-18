import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()
r = c._post("charts/historical", {"securityId":"13","exchangeSegment":"IDX_I","instrument":"INDEX",
    "expiryCode":0,"fromDate":"2024-01-01","toDate":"2024-02-01"})
print("status", r.status_code if r is not None else None)
print((r.text[:400] if r is not None else "no response"))
