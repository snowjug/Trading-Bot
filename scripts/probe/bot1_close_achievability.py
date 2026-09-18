"""
Is the bhavcopy CLOSE an achievable fill?

Bot 1's backtest fills each leg at that leg's daily close. This measures, on
CURRENTLY LISTED far-OTM contracts at the distances Bot 1 actually uses
(~ATM+/-13 shorts, ~ATM+/-17 wings), how that close relates to prices genuinely
available in the closing half hour. Uses 5-minute bars from /charts/intraday,
read-only.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
import pandas as pd, numpy as np
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()

sm = pd.read_csv("data/dhan_scrip_master_index_opt.csv", dtype={"SEM_SMST_SECURITY_ID":str}, low_memory=False)
sm = sm[sm.UNDERLYING=="NIFTY"].copy()
sm["EXP"] = pd.to_datetime(sm.EXPIRY_DATE_CLEAN)
exps = sorted(sm.EXP.unique())[:4]
near = sm[sm.EXP.isin(exps)]
print("listed expiries used:", [str(pd.Timestamp(e).date()) for e in exps])

bh = pd.read_parquet("data/raw/nse/fo_bhavcopy/NIFTY_options_20260916.parquet")
spot = float(bh.UndrlygPric.iloc[0]); atm = round(spot/50)*50
print(f"spot {spot:.2f} atm {atm:.0f}\n")

rows = []
for off, lab in [(o,("short~1.8SD" if abs(o)==13 else "wing~2.4SD")) for o in (13,17,-13,-17)]:
    k = atm + off*50
    typ = "CE" if off > 0 else "PE"
    cands = near[(near.SEM_STRIKE_PRICE==k)&(near.SEM_OPTION_TYPE==typ)]
    if cands.empty: print(f"  K={k} {typ}: not listed"); continue
    frames=[]
    for _, cr in cands.iterrows():
        d0 = c.fetch_intraday_candles(cr.SEM_SMST_SECURITY_ID,"NSE_FNO","OPTIDX","5",
                                      "2026-08-01 09:15:00","2026-09-17 15:30:00")
        if not d0.empty:
            d0 = d0.copy(); d0["exp"]=str(pd.Timestamp(cr.EXP).date()); frames.append(d0)
    if not frames: print(f"  K={k} {typ}: no bars"); continue
    df = pd.concat(frames, ignore_index=True)
    df["d"]=df.datetime.dt.date; df["t"]=df.datetime.dt.time
    for (d, ex), g in df.groupby(["d","exp"]):
        last30 = g[g.t >= pd.Timestamp("15:00").time()]
        if last30.empty or len(g)<10: continue
        close = float(g.iloc[-1].close)
        rows.append({"date":str(d),"exp":ex,"strike":k,"type":typ,"label":lab,
            "close":close,
            "last30_lo":float(last30.low.min()),"last30_hi":float(last30.high.max()),
            "day_lo":float(g.low.min()),"day_hi":float(g.high.max()),
            "in_last30_range": bool(last30.low.min() <= close <= last30.high.max()),
            "last30_span": float(last30.high.max()-last30.low.min()),
            "day_span": float(g.high.max()-g.low.min())})
t = pd.DataFrame(rows)
if len(t):
    print(t.head(10).to_string(index=False)); print("  ... (%d rows)" % len(t))
    print(f"\nclose inside the closing half-hour range: {t.in_last30_range.sum()}/{len(t)}")
    print(f"closing half-hour span: mean {t.last30_span.mean():.2f} pts   full-day span: mean {t.day_span.mean():.2f} pts")
    print(f"ratio last30/day span: {t.last30_span.mean()/t.day_span.mean()*100:.1f}%")
