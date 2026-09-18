"""Weekly condor/vertical across ALL priced sessions, plus a breach-rate stress."""
import os, sys
sys.path.insert(0, r"C:\Users\HP\Desktop\Trading Bot")
import pandas as pd, numpy as np
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
sys.path.insert(0, r"C:\Users\HP\Desktop\Trading Bot\scripts\research")
from weekly_premium_lab import WSpec, run, daily_with_rsi, metrics

daily = daily_with_rsi(); store = load_bhavcopy_store()
chains = ChainIndex(store); expiries = weekly_expiry_calendar(store)
alls = sorted(set(store["TradDt"].unique()))
print(f"all priced sessions: {len(alls)}  {alls[0]} .. {alls[-1]}")

for nm, spec in (("condor_1.8sd_w4", WSpec("c","condor",1.8,4)),
                 ("vert_auto_1.3sd_w12", WSpec("v","vertical_auto",1.3,12)),
                 ("vert_auto_1.8sd_w4", WSpec("v2","vertical_auto",1.8,4))):
    sk={}
    tr = run(spec, alls, daily, store, chains, expiries, sk)
    if not tr: print(f"{nm}: no trades"); continue
    df = pd.DataFrame(tr); df["yr"]=pd.to_datetime(df.sess).dt.year
    m = metrics(tr, len(alls))
    br=0
    for t in tr:
        sc=[l for l in t["legs"] if l["role"]=="short_call"]; sp=[l for l in t["legs"] if l["role"]=="short_put"]
        if (sc and t["settle"]>sc[0]["strike"]) or (sp and t["settle"]<sp[0]["strike"]): br+=1
    print(f"\n=== {nm} ===")
    print(f"  n={m['trades']} win={m['win_rate']}% gross={m['gross']:,.0f} costs={m['costs']:,.0f} "
          f"net={m['net']:,.0f} exp={m['expectancy']:,.0f} t={m['tstat']}")
    print(f"  breaches={br}/{m['trades']} = {br/m['trades']*100:.1f}%   avg credit {m['avg_credit_pts']:.2f} pts")
    print(f"  avg max_risk Rs {m['avg_max_risk']:,.0f}   maxDD Rs {m['max_dd']:,.0f}")
    print(f"  by year: {df.groupby('yr').net.agg(['count','sum']).round(0).to_dict('index')}")
    # stress: what if breaches occurred at the 7.32% historically measured rate?
    lot = df.lot.mode()[0]
    credit_rs = df.credit_pts.mean()*lot
    cost_rs = df.costs.mean()
    # measured loss when breached, from this sample if any, else from full-history study
    brs = [t for t in tr if ((([l for l in t['legs'] if l['role']=='short_call'] and t['settle']>[l for l in t['legs'] if l['role']=='short_call'][0]['strike']) or
                              ([l for l in t['legs'] if l['role']=='short_put'] and t['settle']<[l for l in t['legs'] if l['role']=='short_put'][0]['strike'])))]
    if brs:
        loss_rs = -np.mean([t["net"] for t in brs])
        print(f"  measured avg loss when breached: Rs {loss_rs:,.0f}  (n={len(brs)})")
    else:
        loss_rs = 73.48*lot   # full-history measured 73.48 pts loss when breached
        print(f"  NO BREACH IN SAMPLE -> using full-history measured 73.48 pts = Rs {loss_rs:,.0f}")
    for rate in (0.0732, 0.10, 0.1429):
        exp = (1-rate)*(credit_rs-cost_rs) - rate*(loss_rs)
        print(f"    at {rate*100:5.2f}% breach rate -> expectancy Rs {exp:+,.0f}/cycle")
