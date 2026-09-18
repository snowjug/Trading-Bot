import os, sys, json
sys.path.insert(0, r"C:\Users\HP\Desktop\Trading Bot")
sys.path.insert(0, r"C:\Users\HP\Desktop\Trading Bot\scripts\research")
import pandas as pd, numpy as np
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from weekly_premium_lab import WSpec, run, daily_with_rsi, metrics

daily = daily_with_rsi(); store = load_bhavcopy_store()
chains = ChainIndex(store); expiries = weekly_expiry_calendar(store)
alls = sorted(set(store["TradDt"].unique()))
HS = pd.Timestamp("2026-06-18").date(); HE = pd.Timestamp("2026-09-18").date()

tr = run(WSpec("BOT1","condor",1.8,4), alls, daily, store, chains, expiries, {})
df = pd.DataFrame(tr); df["sess"]=pd.to_datetime(df.sess).dt.date
df["oos"] = df.sess >= HS
df["breach"] = [ (([l for l in t["legs"] if l["role"]=="short_call"] and t["settle"]>[l for l in t["legs"] if l["role"]=="short_call"][0]["strike"]) or
                  ([l for l in t["legs"] if l["role"]=="short_put"]  and t["settle"]<[l for l in t["legs"] if l["role"]=="short_put"][0]["strike"])) for t in tr]
df["ret_on_risk"] = df.net / df.max_risk * 100

print("=== FULL 79-CYCLE LEDGER (condor 1.8sd, 4-step wings) ===")
print(f"{'entry':12}{'expiry':12}{'shortP':>8}{'shortC':>8}{'settle':>9}{'credit':>8}{'risk':>9}{'net':>9}{'%risk':>7}  br")
for _,r in df.iterrows():
    sp=[l for l in r.legs if l["role"]=="short_put"]; sc=[l for l in r.legs if l["role"]=="short_call"]
    print(f"{str(r.sess):12}{str(r.expiry):12}{sp[0]['strike']:>8.0f}{sc[0]['strike']:>8.0f}"
          f"{r.settle:>9.1f}{r.credit_pts:>8.2f}{r.max_risk:>9,.0f}{r.net:>9,.0f}{r.ret_on_risk:>6.1f}%  {'X' if r.breach else ''}")

def blk(d, lab):
    if not len(d): print(f"{lab}: none"); return
    n=len(d); net=d.net.sum(); mu=d.net.mean(); sd=d.net.std(ddof=1) if n>1 else 0
    t = mu/(sd/np.sqrt(n)) if sd>0 else float('nan')
    eq=d.net.cumsum(); dd=abs((eq-eq.cummax()).min())
    print(f"\n{lab}: n={n} win={100*(d.net>0).mean():.1f}% net={net:,.0f} exp={mu:,.0f} "
          f"sd={sd:,.0f} t={t:.2f} maxDD={dd:,.0f} breaches={int(d.breach.sum())} "
          f"worst={d.net.min():,.0f} best={d.net.max():,.0f} avgRisk={d.max_risk.mean():,.0f} "
          f"medRetOnRisk={d.ret_on_risk.median():.2f}%")
blk(df, "ALL 2024-01..2026-09")
blk(df[~df.oos], "IN-SAMPLE (params chosen here)")
blk(df[df.oos],  "OUT-OF-SAMPLE HOLDOUT 2026-06-18..09-18")

print("\n=== MAX-LOSS TAIL ===")
print(f"  theoretical max loss/lot = (width - credit) = Rs {df.max_risk.max():,.0f}")
print(f"  worst realised cycle     = Rs {df.net.min():,.0f}  ({df.net.min()/df.max_risk.max()*100:.1f}% of max risk)")
print(f"  cycles needed to recover one MAX loss = {df.max_risk.max()/df.net.mean():.0f}")
print(f"  breach losses: {sorted(df[df.breach].net.round(0).tolist())}")

print("\n=== CAPITAL SCENARIOS (risk-defined; capital = max_risk per lot) ===")
per_lot = df.max_risk.max()
for acc in (20000.,50000.,100000.):
    lots = int((acc*0.60)//per_lot)
    if lots<1:
        print(f"  Rs {acc:>8,.0f}: NOT EXECUTABLE at 60% cap - one lot risks up to Rs {per_lot:,.0f}")
        lots_full = int(acc//per_lot)
        print(f"              (at 100% of account: {lots_full} lot(s))")
        continue
    hold = df[df.oos]
    for lab, d in (("full", df), ("holdout", hold)):
        net=d.net.sum()*lots; eq=(d.net*lots).cumsum(); dd=abs((eq-eq.cummax()).min())
        print(f"  Rs {acc:>8,.0f} {lab:8}: {lots} lot(s) risk Rs {per_lot*lots:,.0f}  net Rs {net:>9,.0f}"
              f"  return {net/acc*100:>7.2f}%  maxDD Rs {dd:,.0f} ({dd/acc*100:.2f}%)")
df.drop(columns=["legs"]).to_csv(r"reports/bot1_condor_full_ledger.csv", index=False)
print("\nwrote reports/bot1_condor_full_ledger.csv")
