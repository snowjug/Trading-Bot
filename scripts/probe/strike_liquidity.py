import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
import pandas as pd
from datetime import date
from src.data.dhan_client import get_dhan_client
from src.execution.dhan_scrip_master import DhanScripMaster

c = get_dhan_client()
idx = c.fetch_marketfeed_quote([13,21], exchange_segment="IDX_I")
spot = float(idx["13"]["ltp"]); vix=float(idx["21"]["ltp"])
atm = round(spot/50)*50
df = DhanScripMaster.get_master_df()
df = df[df.UNDERLYING=="NIFTY"].copy()
df["EXP"]=pd.to_datetime(df.EXPIRY_DATE_CLEAN, errors="coerce").dt.date
nearest = sorted({e for e in df.EXP.dropna() if e>=date.today()})[0]
print(f"spot {spot}  atm {atm}  vix {vix}  expiry {nearest}\n")

sids, meta = [], {}
for off in range(0, 21):
    for sgn, ot in ((1,"CE"), (-1,"PE")):
        k = atm + sgn*off*50
        r = df[(df.EXP==nearest)&(df.SEM_STRIKE_PRICE==k)&(df.SEM_OPTION_TYPE==ot)]
        if not r.empty:
            sid=str(r.iloc[0].SEM_SMST_SECURITY_ID); sids.append(sid); meta[sid]=(off,ot,k)
import time as _t
q = {}
for i in range(0, len(sids), 12):
    q.update(c.fetch_marketfeed_quote(sids[i:i+15], exchange_segment="NSE_FNO"))
    _t.sleep(2.0)
rows=[]
for sid,(off,ot,k) in meta.items():
    d=q.get(sid,{})
    rows.append({"off":off,"type":ot,"strike":k,"bid":d.get("bid"),"ask":d.get("ask"),
                 "two_sided": bool(d.get("bid") and d.get("ask"))})
t=pd.DataFrame(rows).sort_values(["type","off"])
for ot in ("CE","PE"):
    s=t[t.type==ot]
    live=s[s.two_sided]
    print(f"{ot}: two-sided at offsets {sorted(live.off.tolist())}")
    print(f"    furthest two-sided: ATM{'+' if ot=='CE' else '-'}{live.off.max() if len(live) else 'NONE'}")
    dead=s[~s.two_sided]
    if len(dead): print(f"    NO market at: {sorted(dead.off.tolist())}")
