import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
import pandas as pd
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()
m = pd.read_csv("data/dhan_scrip_master_index_opt.csv", dtype={"SEM_SMST_SECURITY_ID":str}, low_memory=False)
n = m[(m.UNDERLYING=="NIFTY")&(m.SEM_OPTION_TYPE=="CE")].copy()
n["EXPIRY_DATE_CLEAN"]=pd.to_datetime(n.EXPIRY_DATE_CLEAN)
nearest = n[n.EXPIRY_DATE_CLEAN==n.EXPIRY_DATE_CLEAN.min()]
spot = 23217.6
for label, k in [("ATM", round(spot/50)*50), ("ATM+13", round(spot/50)*50+650), ("ATM+17", round(spot/50)*50+850)]:
    r = nearest[nearest.SEM_STRIKE_PRICE==k]
    if r.empty: print(f"  {label} K={k}: not listed"); continue
    sid = r.iloc[0].SEM_SMST_SECURITY_ID
    for frm,to in [("2026-09-17 09:15:00","2026-09-17 15:30:00"),
                   ("2026-09-10 09:15:00","2026-09-17 15:30:00")]:
        df = c.fetch_intraday_candles(sid,"NSE_FNO","OPTIDX","5",frm,to)
        print(f"  {label} K={k:.0f} sid={sid} {frm[:10]}..{to[:10]}: rows={len(df)}"
              + (f"  range {df.low.min():.2f}-{df.high.max():.2f}" if len(df) else ""))
