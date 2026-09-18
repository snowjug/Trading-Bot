import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()

print("=== STRIKE CEILING ACROSS ERAS (is ATM+/-10 stable?) ===")
for frm,to in [("2021-03-01","2021-03-31"),("2023-06-01","2023-06-30"),("2026-07-01","2026-07-31")]:
    row=[]
    for k in ["ATM+6","ATM+8","ATM+10","ATM+11","ATM+12"]:
        n=len(c.fetch_rolling_options(from_date=frm,to_date=to,strike=k,drv_option_type="CALL")["ce"])
        row.append(f"{k}={n}")
    print(f"  {frm[:7]}: " + "  ".join(row))

print("\n=== EXPIRY CODE COVERAGE (near vs next weekly) ===")
for code in [1,2,3]:
    n=len(c.fetch_rolling_options(from_date="2026-07-01",to_date="2026-07-31",
        strike="ATM",drv_option_type="CALL",expiry_code=code)["ce"])
    print(f"  expiryCode={code} (WEEK): bars={n}")

print("\n=== MONTHLY EXPIRY FLAG ===")
n=len(c.fetch_rolling_options(from_date="2026-07-01",to_date="2026-07-31",
    strike="ATM",drv_option_type="CALL",expiry_flag="MONTH")["ce"])
print(f"  expiryFlag=MONTH: bars={n}")

print("\n=== /charts/intraday WITH AN OPTION SECURITY ID (could reach Bot 1 far strikes) ===")
import pandas as pd
m = pd.read_csv("data/dhan_scrip_master_index_opt.csv", dtype={"SEM_SMST_SECURITY_ID":str}, low_memory=False)
n = m[(m.UNDERLYING=="NIFTY")&(m.SEM_OPTION_TYPE=="CE")].sort_values("EXPIRY_DATE_CLEAN")
if len(n):
    row=n.iloc[len(n)//2]
    sid=row.SEM_SMST_SECURITY_ID
    print(f"  probing {row.SEM_CUSTOM_SYMBOL} sid={sid}")
    for frm,to in [("2026-09-15 09:15:00","2026-09-17 15:30:00"),("2026-08-01 09:15:00","2026-08-30 15:30:00")]:
        df=c.fetch_intraday_candles(sid,"NSE_FNO","OPTIDX","5",frm,to)
        print(f"    {frm[:10]}..{to[:10]}: rows={len(df)}")
