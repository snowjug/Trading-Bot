import os, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()
for frm,to,lab in [("2026-01-01","2026-03-31","quarter"),("2026-01-01","2026-06-30","half"),
                   ("2025-01-01","2025-12-31","year"),("2023-01-01","2026-09-16","multi-year")]:
    t=time.time(); r=c.fetch_rolling_options(from_date=frm,to_date=to,strike="ATM",drv_option_type="CALL")
    n=len(r["ce"]); d=r["ce"]["datetime"].dt.date.nunique() if n else 0
    print(f"{lab:11s} {frm}..{to}: bars={n:7d} days={d:4d} in {time.time()-t:.1f}s")
