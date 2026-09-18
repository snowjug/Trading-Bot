import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from src.research import bot7_discovery as B7
from src.research.bot56_real_option_model import load_option_grid_5m
from src.research.bot1_condor_real import load_bhavcopy_store, weekly_expiry_calendar
from datetime import time as dtime

grid = load_option_grid_5m(); store = load_bhavcopy_store()
expiries = set(weekly_expiry_calendar(store))
sessions = sorted(set(grid["ce"].datetime.dt.date) & set(grid["pe"].datetime.dt.date))
exp_days = [d for d in sessions if d in expiries]
tr = B7.c6_expiry_iron_fly(grid, exp_days)
priced = {t.date for t in tr}

by = B7.index_by_session(grid)
rows=[]
for d in exp_days:
    g = by["ce"].get(d)
    if g is None or g.empty: continue
    sp = B7.spot_path(g)
    e = sp[sp.datetime.dt.time >= dtime(9,20)]
    x = sp[sp.datetime.dt.time >= dtime(15,15)]
    if e.empty or x.empty: 
        rows.append({"d":str(d),"priced":str(d) in priced,"move":np.nan,"reason":"no entry/exit bar"}); continue
    s0=float(e.iloc[0].spot); s1=float(x.iloc[0].spot)
    rows.append({"d":str(d),"priced":str(d) in priced,"move":abs(s1-s0),
                 "signed":s1-s0,"strikes":g.strike.nunique(),
                 "atm":round(s0/50)*50,
                 "has_atm": bool((g.strike==round(s0/50)*50).any()),
                 "has_wings": bool((g.strike==round(s0/50)*50+200).any())})
df=pd.DataFrame(rows)
print(f"expiry days {len(df)}  priced {df.priced.sum()}  skipped {(~df.priced).sum()}")
ok=df[df.priced]; no=df[~df.priced]
print(f"\nABS SPOT MOVE 09:20->15:15")
print(f"  priced : n={len(ok):3d}  mean {ok.move.mean():7.2f}  median {ok.move.median():7.2f}  p90 {ok.move.quantile(.9):7.2f}  max {ok.move.max():7.2f}")
print(f"  skipped: n={len(no):3d}  mean {no.move.mean():7.2f}  median {no.move.median():7.2f}  p90 {no.move.quantile(.9):7.2f}  max {no.move.max():7.2f}")
print(f"\nwhy skipped: missing ATM strike {int((~no.has_atm).sum())}, missing wing {int((~no.has_wings).sum())}")
print(f"\nfraction of moves exceeding the 200-pt wing:")
print(f"  priced {100*(ok.move>200).mean():.1f}%   skipped {100*(no.move>200).mean():.1f}%")
