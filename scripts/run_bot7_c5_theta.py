"""
Bot 7 / C5 — descriptive phase: is weekly option decay uneven across the week?

The ledger specified this candidate as a MEASUREMENT first. No trading rule is
written unless the data shows an asymmetry worth trading, and any such rule would
be added to the ledger before being tested.
"""
import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd, numpy as np
from src.research.bot1_condor_real import load_bhavcopy_store, weekly_expiry_calendar, ChainIndex

store = load_bhavcopy_store()
chains = ChainIndex(store)   # one grouping instead of a 4M-row scan per lookup
sessions = sorted(store["TradDt"].unique())
pos = {d: i for i, d in enumerate(sessions)}
expiries = [e for e in weekly_expiry_calendar(store) if e in pos]

rows = []
for e in expiries:
    ep = pos[e]
    for k in range(0, 6):                       # 5 sessions before expiry .. expiry day
        sp = ep - k
        if sp < 0:
            continue
        day = sessions[sp]
        ch = chains.chain(day, e)
        if ch.empty:
            continue
        spot = ch["UndrlygPric"].dropna()
        if spot.empty or float(spot.iloc[0]) <= 0:
            continue
        spot = float(spot.iloc[0])
        atm = round(spot / 50.0) * 50.0
        legs = ch[(ch["StrkPric"] == atm) & (ch["TtlTradgVol"] > 0)]
        if len(legs) < 2:
            continue
        ce = legs[legs["OptnTp"] == "CE"]["ClsPric"]
        pe = legs[legs["OptnTp"] == "PE"]["ClsPric"]
        if ce.empty or pe.empty:
            continue
        rows.append({"expiry": str(e), "day": str(day), "sessions_to_expiry": k,
                     "weekday": pd.Timestamp(day).day_name(),
                     "straddle": float(ce.iloc[0]) + float(pe.iloc[0]), "spot": spot})

df = pd.DataFrame(rows)
print(f"observations: {len(df)} across {df.expiry.nunique()} expiries "
      f"({df.day.min()} .. {df.day.max()})")

print("\nATM STRADDLE PREMIUM BY SESSIONS TO EXPIRY")
g = df.groupby("sessions_to_expiry")["straddle"].agg(["count", "mean", "median"])
print(g.round(2).to_string())

# Decay per session, measured within each expiry cycle so spot level cancels out.
df = df.sort_values(["expiry", "sessions_to_expiry"], ascending=[True, False])
df["prev"] = df.groupby("expiry")["straddle"].shift(1)
df["decay_pct"] = (df["straddle"] / df["prev"] - 1.0) * 100
d = df.dropna(subset=["decay_pct"])
print("\nPREMIUM CHANGE PER SESSION (%, within each expiry cycle)")
print(d.groupby("sessions_to_expiry")["decay_pct"]
       .agg(["count", "mean", "median", "std"]).round(2).to_string())
print("\nBY WEEKDAY")
print(d.groupby("weekday")["decay_pct"].agg(["count", "mean", "median"]).round(2).to_string())

mean_by_k = d.groupby("sessions_to_expiry")["decay_pct"].mean()
spread = float(mean_by_k.max() - mean_by_k.min())
print(f"\nspread between the best and worst session bucket: {spread:.2f} pp per session")
print("VERDICT:", "ASYMMETRY PRESENT — worth a rule" if spread > 5 else
      "asymmetry is not large or stable enough to specify a tradable rule")
json.dump({"observations": len(df), "expiries": int(df.expiry.nunique()),
           "mean_decay_by_sessions_to_expiry": mean_by_k.round(3).to_dict(),
           "spread_pp": round(spread, 3)},
          open("reports/bot7_c5_theta.json", "w"), indent=2, default=str)
