"""Bot 8 causal historical sanity check. Reject-if-broken, not a parameter search."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from datetime import time as dtime
from src.research.bot56_real_option_model import load_option_grid_5m
from src.research import bot7_discovery as B7
from src.research import validation as V
from src.execution import bot8_price_action as B8
from src.execution.cost_model import IndianCostModel

grid=load_option_grid_5m(); LOT=65
raw=pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
n=raw[raw.symbol=="NIFTY50"][["datetime","open","high","low","close"]]
v=raw[raw.symbol=="INDIAVIX"][["datetime","close"]].rename(columns={"close":"vix"})
d=n.merge(v,on="datetime").sort_values("datetime").reset_index(drop=True)
prev=d.close.shift(1)
tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
d["atr"]=tr.rolling(14).mean(); d["sess"]=d.datetime.dt.date
P=d.shift(1)   # prior session only
d["bias"]=[B8.daily_bias_from(d.close.iloc[:i+1]) for i in range(len(d))]
P=d.shift(1)
prior=dict(zip(d.sess, zip(P.atr,P.vix,P.high,P.low,P.bias)))
by=B7.index_by_session(grid)

trades=[]
sessions=sorted(set(by["ce"])&set(by["pe"]))
for sess in sessions:
    p=prior.get(sess)
    if p is None: continue
    atr,vix,pdh,pdl,bias=p
    if not all(np.isfinite(x) for x in (atr,vix,pdh,pdl)) or atr<=0: continue
    sp=B7.spot_path(by["ce"][sess])
    sp=sp[sp.datetime.dt.time<=dtime(15,10)].reset_index(drop=True)
    if len(sp)<40: continue
    path=[]
    for i in range(len(sp)):
        t=sp.iloc[i].datetime; path.append(float(sp.iloc[i].spot))
        if t.time()<dtime(9,45) or t.time()>=dtime(15,0): continue
        sig=B8.evaluate(path, atr, vix, t.time(), pdh, pdl, daily_bias=bias)
        if sig.state not in ("LONG_ENTRY","SHORT_ENTRY"): continue
        dirn=sig.direction; side="ce" if dirn>0 else "pe"
        dg=by[side].get(sess)
        if dg is None: break
        got=B7.buy_option_at(dg,t,path[-1])
        if not got: break
        strike,entry=got
        leg=dg[(dg.strike==strike)&(dg.datetime>=t)].sort_values("datetime")
        if len(leg)<2: break
        # structural stop / target translated to option P&L via a 0.5 delta used
        # ONLY for exit sizing, never for pricing a fill
        stop_pts=abs(path[-1]-sig.stop); tgt_pts=abs(sig.target-path[-1])
        stp=-stop_pts*LOT*0.5; tgt=tgt_pts*LOT*0.5
        peak=0.0; exitp=None; mae=0.0; mfe=0.0
        for _,b in leg.iloc[1:].iterrows():
            pnl=(float(b.close)-entry)*LOT
            peak=max(peak,pnl); mae=min(mae,pnl); mfe=max(mfe,pnl)
            if pnl<=stp: exitp=float(b.close); break
            if pnl>=tgt: exitp=float(b.close); break
            if peak>=0.6*tgt and pnl<=peak-0.35*tgt: exitp=float(b.close); break
            if b.datetime.time()>=dtime(15,10): exitp=float(b.close); break
        if exitp is None: exitp=float(leg.iloc[-1].close)
        gross=(exitp-entry)*LOT
        cost=IndianCostModel.calculate_roundtrip_costs(entry,exitp,LOT).total_costs
        trades.append({"sess":sess,"net":gross-cost,"mae":mae,"mfe":mfe,
                       "rr":sig.risk_reward,"setup":sig.setup_type})
        break   # one trade per session

t=pd.DataFrame(trades)
print(f"sessions scanned : {len(sessions)}")
print(f"trades           : {len(t)}  ({len(t)/max(len(sessions),1)*100:.1f}% of sessions)")
if len(t)<20: print("TOO FEW TRADES — rework"); raise SystemExit(0)
a=t.net.values
w=a[a>0]; l=a[a<=0]
print(f"net              : Rs {a.sum():,.0f}")
print(f"expectancy       : Rs {a.mean():,.1f}/trade")
print(f"win rate         : {(a>0).mean()*100:.1f}%")
print(f"avg win / avg loss: Rs {w.mean():,.0f} / Rs {l.mean():,.0f}"
      f"   payoff {abs(w.mean()/l.mean()):.2f}" if len(w) and len(l) else "")
print(f"t-stat           : {V.tstat(a.tolist()):+.2f}")
print(f"MAE mean/worst   : Rs {t.mae.mean():,.0f} / {t.mae.min():,.0f}")
print(f"MFE mean/best    : Rs {t.mfe.mean():,.0f} / {t.mfe.max():,.0f}")
eq=np.cumsum(a); print(f"max drawdown     : Rs {abs((eq-np.maximum.accumulate(eq)).min()):,.0f}")
print(f"setups           : {t.setup.value_counts().to_dict()}")
t["yr"]=pd.to_datetime(t.sess).dt.year
print("\nby regime (year):")
print(t.groupby("yr").net.agg(["count","sum","mean"]).round(0).to_string())
print("\nwalk-forward:", V.walk_forward(a.tolist(), t.sess.astype(str).tolist(), folds=4).get("folds_positive"), "/4 positive")
oos=V.chronological_split(a.tolist(), t.sess.astype(str).tolist())
if "is" in oos: print(f"OOS 70/30: IS {oos['is']['mean']:+.0f} | OOS {oos['oos']['mean']:+.0f} | agree {oos['sign_agreement']}")
