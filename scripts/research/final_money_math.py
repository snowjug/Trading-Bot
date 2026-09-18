import os, sys, json
sys.path.insert(0, r"C:\Users\HP\Desktop\Trading Bot")
sys.path.insert(0, r"C:\Users\HP\Desktop\Trading Bot\scripts\research")
from datetime import time as dtime
import pandas as pd, numpy as np
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.strategy_lab import Spec, daily_frame, index_grid, money_metrics, simulate, split_sessions, tstat
from weekly_premium_lab import WSpec, run, daily_with_rsi
from holdout_study import frozen_bot_signal

daily=daily_frame(); d2=daily_with_rsi(); store=load_bhavcopy_store()
chains=ChainIndex(store); expiries=weekly_expiry_calendar(store)
alls=sorted(set(store["TradDt"].unique()))
grid=load_option_grid_5m(); by_day=index_grid(grid)
dev,val,hold=split_sessions(available_option_days(grid))
HS,HE=hold[0],hold[-1]

def ledger(ws):
    tr=run(ws, alls, d2, store, chains, expiries, {})
    df=pd.DataFrame(tr); df["sess"]=pd.to_datetime(df.sess).dt.date
    df["expiry"]=pd.to_datetime(df.expiry).dt.date
    def _br(t):
        sc=[l for l in t["legs"] if l["role"]=="short_call"]
        sp=[l for l in t["legs"] if l["role"]=="short_put"]
        return bool((sc and t["settle"]>sc[0]["strike"]) or (sp and t["settle"]<sp[0]["strike"]))
    df["breach"]=[_br(t) for t in tr]
    return df
b1=ledger(WSpec("BOT1","condor",1.8,4)); b2=ledger(WSpec("BOT2","vertical_auto",1.3,12))

print("=== BOT2 vertical_auto 1.3sd/12 ===")
for lab,d in (("ALL",b2),("IN-SAMPLE",b2[b2.sess<HS]),("HOLDOUT",b2[b2.sess>=HS])):
    n=len(d); mu=d.net.mean(); sd=d.net.std(ddof=1); eq=d.net.cumsum()
    print(f"  {lab:10} n={n:>3} net={d.net.sum():>9,.0f} exp={mu:>7,.0f} t={mu/(sd/np.sqrt(n)):>6.2f} "
          f"maxDD={abs((eq-eq.cummax()).min()):>8,.0f} breach={int(d.breach.sum())} worst={d.net.min():>9,.0f} "
          f"maxRisk={d.max_risk.max():>9,.0f}")
print(f"  -> one lot risks up to Rs {b2.max_risk.max():,.0f}; 60% of Rs 50,000 = Rs 30,000 -> "
      f"{'EXECUTABLE' if b2.max_risk.max()<=30000 else 'NOT EXECUTABLE at Rs 50k'}")

# ── daily return distribution for BOT1 on the holdout, P&L realised on expiry day ──
print("\n=== BOT1 DAILY RETURN DISTRIBUTION — HOLDOUT (P&L realised on expiry day) ===")
hsess=[d for d in sorted(set(store["TradDt"].unique())) if HS<=d<=HE]
hb1=b1[b1.sess>=HS]
per_lot=b1.max_risk.max()
for acc in (20000.,50000.,100000.):
    lots=int((acc*0.60)//per_lot)
    cap_note=""
    if lots<1:
        lots=int(acc//per_lot); cap_note=" [needs 100% of account - NOT within 60% risk cap]"
    if lots<1: print(f"  Rs {acc:>8,.0f}: NOT EXECUTABLE - one lot risks Rs {per_lot:,.0f}"); continue
    s=pd.Series(0.0,index=pd.Index(hsess,name="sess"))
    for _,r in hb1.iterrows():
        if r.expiry in s.index: s.loc[r.expiry]+=r.net*lots
        else: s.iloc[-1]+=r.net*lots
    ret=s/acc*100
    eq=s.cumsum(); dd=abs((eq-eq.cummax()).min())
    print(f"  Rs {acc:>8,.0f} ({lots} lot){cap_note}")
    print(f"     net Rs {s.sum():>9,.0f}  return {s.sum()/acc*100:>7.2f}%  over {len(hsess)} sessions")
    print(f"     avg daily {ret.mean():>6.3f}%   median daily {ret.median():>6.3f}%   "
          f"avg on P&L days {ret[ret!=0].mean():>6.3f}%")
    print(f"     days >=+1% {100*(ret>=1).mean():>5.1f}%   >=+2% {100*(ret>=2).mean():>5.1f}%   "
          f"<=-1% {100*(ret<=-1).mean():>5.1f}%   no-P&L days {100*(ret==0).mean():.1f}%")
    print(f"     maxDD Rs {dd:,.0f} ({dd/acc*100:.2f}%)")

# ── does adding BOT7 (the only positive intraday line) help? ──
print("\n=== PORTFOLIO: BOT1 condor + BOT7 displacement, HOLDOUT ===")
b7=simulate(Spec("BOT7",frozen_bot_signal("BOT7",daily),1.2,0.6,trail_atr=0.7,trail_give_atr=0.4,
                 entry_from=dtime(10,0),entry_to=dtime(15,0)), hold, daily, by_day, {})
b7cap=max(t.capital for t in b7)
print(f"  BOT7: n={len(b7)} net={sum(t.net for t in b7):,.0f} max premium/lot Rs {b7cap:,.0f}")
for acc in (50000.,100000.):
    l1=int((acc*0.60)//per_lot); l7=int((acc*0.20)//b7cap)
    if l1<1 or l7<1: print(f"  Rs {acc:,.0f}: cannot run both"); continue
    s=pd.Series(0.0,index=pd.Index(hsess,name="sess"))
    for _,r in hb1.iterrows():
        (s.loc.__setitem__(r.expiry, s.loc[r.expiry]+r.net*l1) if r.expiry in s.index else None)
    for t in b7:
        if t.sess in s.index: s.loc[t.sess]+=t.net*l7
    eq=s.cumsum(); dd=abs((eq-eq.cummax()).min()); ret=s/acc*100
    print(f"  Rs {acc:>8,.0f}: {l1} condor + {l7} BOT7 lot -> net Rs {s.sum():>9,.0f} ({s.sum()/acc*100:.2f}%)"
          f"  maxDD Rs {dd:,.0f} ({dd/acc*100:.2f}%)  avg daily {ret.mean():.3f}%  >=1% days {100*(ret>=1).mean():.1f}%")
print(f"\nCONDOR ALONE at Rs 100,000 holdout: Rs {hb1.net.sum()*int((100000*0.60)//per_lot):,.0f}")
