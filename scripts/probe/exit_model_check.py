"""Does the ATR target+trail exit beat the old fixed target? One check, then move on."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from datetime import time as dtime
from src.research.bot56_real_option_model import load_option_grid_5m
from src.research import bot7_discovery as B7
from src.research import validation as V
from src.execution.cost_model import IndianCostModel
from src.research.bot5_point_in_time import generate_signals_point_in_time
from src.strategies.micro_momentum_buyer import MicroMomentumBuyerStrategy

grid = load_option_grid_5m(); LOT=65
raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
n = raw[raw.symbol=="NIFTY50"][["datetime","open","high","low","close"]]
v = raw[raw.symbol=="INDIAVIX"][["datetime","close"]].rename(columns={"close":"vix"})
d = n.merge(v,on="datetime").sort_values("datetime").reset_index(drop=True)
prev=d.close.shift(1)
tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
d["atr"]=tr.rolling(14).mean(); d["sess"]=d.datetime.dt.date; d["volume"]=0.0
atr_prior = dict(zip(d.sess, d.atr.shift(1)))
by = B7.index_by_session(grid)

def simulate(entries, tgt_m, stop_m, trail_trig=None, trail_give=None):
    """entries: list of (sess, timestamp, spot, direction)"""
    out=[]
    for sess, ts, spot, dirn in entries:
        a = atr_prior.get(sess)
        if a is None or not np.isfinite(a) or a<=0: continue
        side = "ce" if dirn>0 else "pe"
        dg = by[side].get(sess)
        if dg is None: continue
        got = B7.buy_option_at(dg, ts, spot)
        if not got: continue
        strike, entry = got
        leg = dg[(dg.strike==strike)&(dg.datetime>=ts)].sort_values("datetime")
        if len(leg)<2: continue
        tgt=tgt_m*a*LOT*0.5; stp=-stop_m*a*LOT*0.5
        tt = trail_trig*a*LOT*0.5 if trail_trig else None
        tg = trail_give*a*LOT*0.5 if trail_give else None
        peak=0.0; exitp=None
        for _,b in leg.iloc[1:].iterrows():
            pnl=(float(b.close)-entry)*LOT
            peak=max(peak,pnl)
            if pnl<=stp: exitp=float(b.close); break
            if pnl>=tgt: exitp=float(b.close); break
            if tt and tg and peak>=tt and pnl<=peak-tg: exitp=float(b.close); break
            if b.datetime.time()>=dtime(15,10): exitp=float(b.close); break
        if exitp is None: exitp=float(leg.iloc[-1].close)
        gross=(exitp-entry)*LOT
        out.append(gross-IndianCostModel.calculate_roundtrip_costs(entry,exitp,LOT).total_costs)
    return out

# ---- BOT 6 entries (unchanged signal) ----
s6=MicroMomentumBuyerStrategy(); sig6=s6.generate_signals(d)
m=d.merge(sig6[["datetime","signal"]],on="datetime")
b6=[]
for _,row in m[m.signal!=0].iterrows():
    sess=row.datetime.date(); dg=by["ce"].get(sess)
    if dg is None: continue
    sp=B7.spot_path(dg); sp=sp[sp.datetime.dt.time>=dtime(9,30)]
    if sp.empty: continue
    b6.append((sess, sp.iloc[0].datetime, float(sp.iloc[0].spot), int(row.signal)))

# ---- BOT 7 entries (TWAP displacement, continuation) ----
b7=[]
for sess in sorted(set(by["ce"])&set(by["pe"])):
    a=atr_prior.get(sess)
    if a is None or not np.isfinite(a) or a<=0: continue
    g=by["ce"][sess]; sp=B7.spot_path(g)
    sp=sp[sp.datetime.dt.time<=dtime(15,10)]
    if len(sp)<40: continue
    twap=sp.spot.expanding().mean(); hi=sp.spot.cummax(); lo=sp.spot.cummin()
    for i in range(len(sp)):
        t=sp.iloc[i].datetime
        if t.time()<dtime(10,0) or t.time()>=dtime(15,0): continue
        s=float(sp.iloc[i].spot); st=s-float(twap.iloc[i])
        if abs(st)<0.55*a: continue
        if st>0 and s>=float(hi.iloc[i])-1e-9: continue
        if st<0 and s<=float(lo.iloc[i])+1e-9: continue
        b7.append((sess,t,s,1 if st>0 else -1)); break

for name, ent in (("BOT6", b6), ("BOT7", b7)):
    print(f"\n{name}  entries={len(ent)}")
    for label,args in (("old: fixed 1.45x/0.85x", dict(tgt_m=2.2, stop_m=0.9)),
                       ("new: ATR tgt+stop",      dict(tgt_m=1.2, stop_m=0.6)),
                       ("new: ATR + TRAIL",       dict(tgt_m=1.2, stop_m=0.6, trail_trig=0.6, trail_give=0.35))):
        r=np.array(simulate(ent, **args))
        if len(r)<20: print(f"   {label:24s} n={len(r)}"); continue
        print(f"   {label:24s} n={len(r):4d} net Rs {r.sum():>9,.0f} exp {r.mean():>7,.1f} "
              f"win% {(r>0).mean()*100:5.1f} t={V.tstat(r.tolist()):+.2f}")
