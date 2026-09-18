import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()

# 1) read-only liveness
r = c._post("charts/historical", {"securityId":"13","exchangeSegment":"IDX_I","instrument":"INDEX",
    "expiryCode":0,"fromDate":"2024-01-01","toDate":"2024-02-01"})
print("[index historical] status", r.status_code if r else None, (r.text[:120] if r else ""))

# 2) how far back does the rolling-option feed serve?
for frm, to in [("2026-09-01","2026-09-15"),("2026-08-01","2026-08-31"),
                ("2026-06-01","2026-06-30"),("2026-01-01","2026-01-31"),
                ("2025-06-01","2025-06-30"),("2025-01-01","2025-01-31")]:
    p = {"securityId":"13","exchangeSegment":"NSE_FNO","instrument":"OPTIDX",
         "expiryFlag":"WEEK","expiryCode":1,"strike":"ATM","drvOptionType":"CALL",
         "fromDate":frm,"toDate":to,"interval":"5"}
    rr = c._post("charts/rollingoption", p)
    if rr is None: print(f"[roll {frm}] no response"); continue
    try:
        j = rr.json(); n = len(j.get("timestamp", [])) if isinstance(j, dict) else 0
    except Exception: n = -1
    print(f"[roll {frm}..{to}] status {rr.status_code} bars={n} {('' if n>0 else rr.text[:100])}")
