"""Fast sanity check on the Bot 7 reversion fade. Reject-if-broken, not a search."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from datetime import time as dtime
from src.research.bot56_real_option_model import load_option_grid_5m
from src.research import bot7_discovery as B7
from src.research import validation as V
from src.execution.cost_model import IndianCostModel

grid = load_option_grid_5m()
raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
n = raw[raw.symbol=="NIFTY50"][["datetime","high","low","close"]]
v = raw[raw.symbol=="INDIAVIX"][["datetime","close"]].rename(columns={"close":"vix"})
d = n.merge(v, on="datetime").sort_values("datetime").reset_index(drop=True)
prev = d.close.shift(1)
tr = pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
d["atr"] = tr.rolling(14).mean()
d["sess"] = d.datetime.dt.date
atr_by = dict(zip(d.sess, d.atr.shift(1)))   # PRIOR session's ATR only

by = B7.index_by_session(grid)
LOT=65

def run(stretch_atr, tgt_mult, stop_mult, direction_sign=+1):
    trades=[]
    for sess in sorted(set(by["ce"]) & set(by["pe"])):
        a = atr_by.get(sess)
        if a is None or not np.isfinite(a) or a<=0: continue
        g = by["ce"][sess]
        sp = B7.spot_path(g)
        if len(sp)<40: continue
        sp = sp[sp.datetime.dt.time <= dtime(15,10)]
        twap = sp.spot.expanding().mean()
        hi = sp.spot.cummax(); lo = sp.spot.cummin()
        entered=False
        for i in range(len(sp)):
            t = sp.iloc[i].datetime
            if t.time() < dtime(10,0) or t.time() >= dtime(15,0): continue
            s = float(sp.iloc[i].spot); w=float(twap.iloc[i])
            stretch = s-w
            if abs(stretch) < stretch_atr*a: continue
            if stretch>0 and s>=float(hi.iloc[i])-1e-9: continue
            if stretch<0 and s<=float(lo.iloc[i])+1e-9: continue
            dirn = (-1 if stretch>0 else 1)*direction_sign
            side = "ce" if dirn>0 else "pe"
            dg = by[side].get(sess)
            if dg is None: continue
            got = B7.buy_option_at(dg, t, s)
            if not got: continue
            strike, entry = got
            leg = dg[(dg.strike==strike)&(dg.datetime>=t)].sort_values("datetime")
            if len(leg)<2: continue
            tgt = tgt_mult*a*LOT*0.5; stp = -stop_mult*a*LOT*0.5
            exitp=None; reason="EOD"
            for _,b in leg.iloc[1:].iterrows():
                pnl = (float(b.close)-entry)*LOT
                if pnl<=stp: exitp=float(b.close); reason="STOP"; break
                if pnl>=tgt: exitp=float(b.close); reason="TARGET"; break
                if b.datetime.time()>=dtime(15,10): exitp=float(b.close); reason="EOD"; break
            if exitp is None: exitp=float(leg.iloc[-1].close)
            gross=(exitp-entry)*LOT
            costs=IndianCostModel.calculate_roundtrip_costs(entry,exitp,LOT).total_costs
            trades.append(gross-costs)
            entered=True; break
    return trades

for sign,label in [(+1,"FADE (revert)"), (-1,"FOLLOW (trend)")]:
    tr = run(0.55, 0.55, 0.45, sign)
    a=np.array(tr)
    if len(a)<20: print(f"{label}: only {len(a)} trades"); continue
    print(f"{label:16s} n={len(a):4d} net Rs {a.sum():>10,.0f} "
          f"exp {a.mean():>8,.1f} win% {(a>0).mean()*100:5.1f} t={V.tstat(tr):+.2f}")
