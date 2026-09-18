"""
Bot 6 exit comparison with a CAUSAL intraday entry.

The strategy's generate_signals reads the CURRENT day's high/low, so it cannot be
evaluated at 09:30 — that is lookahead. Entry here is the actual moment the live
session first breaks the PREVIOUS session's range, with EMA/RSI from completed
bars only, which is what the live bot does.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from datetime import time as dtime
from src.research.bot56_real_option_model import load_option_grid_5m
from src.research import bot7_discovery as B7
from src.research import validation as V
from src.execution.cost_model import IndianCostModel

grid=load_option_grid_5m(); LOT=65
raw=pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
n=raw[raw.symbol=="NIFTY50"][["datetime","open","high","low","close"]]
v=raw[raw.symbol=="INDIAVIX"][["datetime","close"]].rename(columns={"close":"vix"})
d=n.merge(v,on="datetime").sort_values("datetime").reset_index(drop=True)
prev=d.close.shift(1)
tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
d["atr"]=tr.rolling(14).mean()
c=d.close
d["ema9"]=c.ewm(span=9,adjust=False).mean(); d["ema21"]=c.ewm(span=21,adjust=False).mean()
d["ema50"]=c.ewm(span=50,adjust=False).mean()
delta=c.diff(); g=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
l=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
d["rsi"]=100-(100/(1+g/l.replace(0,np.nan)))
d["sess"]=d.datetime.dt.date
# EVERYTHING shifted: only completed prior sessions are visible at decision time
P=d.shift(1)
prior=dict(zip(d.sess, zip(P.ema9,P.ema21,P.ema50,P.rsi,P.atr,P.high,P.low,P.vix)))
by=B7.index_by_session(grid)

entries=[]
for sess in sorted(set(by["ce"])&set(by["pe"])):
    p=prior.get(sess)
    if p is None: continue
    e9,e21,e50,r,a,ph,pl,pv=p
    if not all(np.isfinite(x) for x in (e9,e21,e50,r,a,ph,pl,pv)) or a<=0: continue
    if pv>=18.5: continue
    bull = e9>e21>e50 and r>52.0
    bear = e9<e21<e50 and r<48.0
    if not (bull or bear): continue
    sp=B7.spot_path(by["ce"][sess]); sp=sp[(sp.datetime.dt.time>=dtime(9,30))&(sp.datetime.dt.time<dtime(15,0))]
    if sp.empty: continue
    hi=sp.spot.cummax(); lo=sp.spot.cummin()
    for i in range(len(sp)):
        s=float(sp.iloc[i].spot)
        if bull and float(hi.iloc[i])>ph:
            entries.append((sess,sp.iloc[i].datetime,s,1,a)); break
        if bear and float(lo.iloc[i])<pl:
            entries.append((sess,sp.iloc[i].datetime,s,-1,a)); break

def sim(tgt_m,stop_m,trail_trig=None,trail_give=None):
    out=[]
    for sess,ts,spot,dirn,a in entries:
        side="ce" if dirn>0 else "pe"
        dg=by[side].get(sess)
        if dg is None: continue
        got=B7.buy_option_at(dg,ts,spot)
        if not got: continue
        strike,entry=got
        leg=dg[(dg.strike==strike)&(dg.datetime>=ts)].sort_values("datetime")
        if len(leg)<2: continue
        tgt=tgt_m*a*LOT*0.5; stp=-stop_m*a*LOT*0.5
        tt=trail_trig*a*LOT*0.5 if trail_trig else None
        tg=trail_give*a*LOT*0.5 if trail_give else None
        peak=0.0; exitp=None
        for _,b in leg.iloc[1:].iterrows():
            pnl=(float(b.close)-entry)*LOT; peak=max(peak,pnl)
            if pnl<=stp: exitp=float(b.close); break
            if pnl>=tgt: exitp=float(b.close); break
            if tt and tg and peak>=tt and pnl<=peak-tg: exitp=float(b.close); break
            if b.datetime.time()>=dtime(15,10): exitp=float(b.close); break
        if exitp is None: exitp=float(leg.iloc[-1].close)
        out.append((float(b.close) if False else exitp-entry)*LOT
                   - IndianCostModel.calculate_roundtrip_costs(entry,exitp,LOT).total_costs)
    return out

print(f"BOT 6 causal intraday entries: {len(entries)}")
for label,kw in (("old fixed 1.45x/0.85x", dict(tgt_m=2.2,stop_m=0.9)),
                 ("ATR target+stop",       dict(tgt_m=1.2,stop_m=0.6)),
                 ("ATR + TRAIL",           dict(tgt_m=1.2,stop_m=0.6,trail_trig=0.6,trail_give=0.35))):
    r=np.array(sim(**kw))
    print(f"  {label:22s} n={len(r):4d} net Rs {r.sum():>9,.0f} exp {r.mean():>7,.1f} "
          f"win% {(r>0).mean()*100:5.1f} t={V.tstat(r.tolist()):+.2f}")
