import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
import pandas as pd
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()

# 1) Do bhavcopy FinInstrmId and Scrip Master securityId agree for the SAME contract?
bh = pd.read_parquet("data/raw/nse/fo_bhavcopy/NIFTY_options_20260916.parquet")
sm = pd.read_csv("data/dhan_scrip_master_index_opt.csv", dtype={"SEM_SMST_SECURITY_ID":str}, low_memory=False)
sm = sm[sm.UNDERLYING=="NIFTY"].copy()
sm["EXPIRY_DATE_CLEAN"]=pd.to_datetime(sm.EXPIRY_DATE_CLEAN).dt.strftime("%Y-%m-%d")
j = bh.merge(sm, left_on=["XpryDt","StrkPric","OptnTp"],
             right_on=["EXPIRY_DATE_CLEAN","SEM_STRIKE_PRICE","SEM_OPTION_TYPE"], how="inner")
j["match"] = j.FinInstrmId.astype(str) == j.SEM_SMST_SECURITY_ID.astype(str)
print(f"matched contracts: {len(j)}   id agreement: {j.match.sum()}/{len(j)} = {j.match.mean()*100:.1f}%")
print(j[["FinInstrmNm","XpryDt","StrkPric","OptnTp","FinInstrmId","SEM_SMST_SECURITY_ID","match"]].head(4).to_string(index=False))

# 2) Can we fetch intraday bars for an EXPIRED contract using a bhavcopy id?
print("\n=== EXPIRED CONTRACT VIA BHAVCOPY ID ===")
for f, exp in [("NIFTY_options_20260805.parquet","2026-08-11"),
               ("NIFTY_options_20260610.parquet","2026-06-16"),
               ("NIFTY_options_20250210.parquet","2025-02-13")]:
    try:
        d = pd.read_parquet(f"data/raw/nse/fo_bhavcopy/{f}")
    except Exception:
        print(f"  {f}: not ingested"); continue
    sub = d[(d.XpryDt==exp)&(d.OptnTp=="CE")&(d.TtlTradgVol>0)]
    if sub.empty:
        sub = d[(d.OptnTp=="CE")&(d.TtlTradgVol>0)]
    if sub.empty: print(f"  {f}: no traded CE"); continue
    r = sub.nlargest(1,"TtlTradgVol").iloc[0]
    sid = str(int(r.FinInstrmId)); day = str(r.TradDt)
    df = c.fetch_intraday_candles(sid,"NSE_FNO","OPTIDX","5", f"{day} 09:15:00", f"{day} 15:30:00")
    print(f"  {r.FinInstrmNm} sid={sid} on {day}: rows={len(df)}"
          + (f"  range {df.low.min():.2f}-{df.high.max():.2f}  bhav O/H/L/C {r.OpnPric}/{r.HghPric}/{r.LwPric}/{r.ClsPric}" if len(df) else ""))
