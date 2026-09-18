import os, sys, collections
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from datetime import time as dtime
from src.research.bot56_real_option_model import load_option_grid_5m
from src.research import bot7_discovery as B7
from src.execution import bot8_price_action as B8

grid=load_option_grid_5m()
raw=pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
n=raw[raw.symbol=="NIFTY50"][["datetime","open","high","low","close"]]
v=raw[raw.symbol=="INDIAVIX"][["datetime","close"]].rename(columns={"close":"vix"})
d=n.merge(v,on="datetime").sort_values("datetime").reset_index(drop=True)
prev=d.close.shift(1)
tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
d["atr"]=tr.rolling(14).mean(); d["sess"]=d.datetime.dt.date
d["bias"]=[B8.daily_bias_from(d.close.iloc[:i+1]) for i in range(len(d))]
P=d.shift(1); prior=dict(zip(d.sess, zip(P.atr,P.vix,P.high,P.low,P.bias)))
by=B7.index_by_session(grid)
cnt=collections.Counter(); reasons=collections.Counter(); sess_best={}
for sess in sorted(set(by["ce"]))[:400]:
    p=prior.get(sess)
    if p is None: continue
    atr,vix,pdh,pdl,bias=p
    if not all(np.isfinite(x) for x in (atr,vix,pdh,pdl)) or atr<=0: continue
    sp=B7.spot_path(by["ce"][sess]); sp=sp[sp.datetime.dt.time<=dtime(15,10)].reset_index(drop=True)
    if len(sp)<40: continue
    path=[]; best="WAIT"
    for i in range(len(sp)):
        t=sp.iloc[i].datetime; path.append(float(sp.iloc[i].spot))
        if t.time()<dtime(9,45) or t.time()>=dtime(15,0): continue
        sig=B8.evaluate(path,atr,vix,t.time(),pdh,pdl,daily_bias=bias)
        cnt[sig.state]+=1
        if sig.state=="WAIT": reasons[sig.reason.split("—")[0].split(" ")[0][:28]]+=1
        rank={"WAIT":0,"REJECTED":1,"ARMED":2,"LONG_SETUP":3,"SHORT_SETUP":3,"LONG_ENTRY":4,"SHORT_ENTRY":4}
        if rank.get(sig.state,0)>rank.get(best,0): best=sig.state
    sess_best[sess]=best
print("state counts (all bar-evaluations):", dict(cnt))
print("\ntop WAIT reasons:", reasons.most_common(8))
print("\nbest state reached per session:", collections.Counter(sess_best.values()))
