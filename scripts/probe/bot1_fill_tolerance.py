import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import numpy as np, pandas as pd
from src.research.bot1_condor_real import load_bhavcopy_store, run_real_condor_backtest, condor_leg_costs
sys.path.insert(0, "scripts")
from validate_bot1_condor import underlying

store = load_bhavcopy_store(); d = underlying()
res = run_real_condor_backtest(d, store, signal_lag=0)
tr = res["trades"]

rng, closes = [], []
for t in tr:
    for l in t.legs:
        if l.entry_day_high > 0 and l.entry_day_low > 0:
            rng.append(l.entry_day_high - l.entry_day_low)
            span = l.entry_day_high - l.entry_day_low
            closes.append((l.entry_price - l.entry_day_low)/span if span > 0 else np.nan)
rng = np.array(rng); closes = np.array(closes, dtype=float)
print(f"legs={len(rng)}  leg intraday range: mean={rng.mean():.2f} median={np.median(rng):.2f} "
      f"p90={np.percentile(rng,90):.2f} pts")
print(f"entry close sits at {np.nanmean(closes)*100:.1f}% of the leg's daily range on average")

print("\nFILL-QUALITY SWEEP — fill at fraction f of the way from the close toward the worst print")
for f in [0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0]:
    tot = 0.0; wins = 0
    for t in tr:
        gross = 0.0
        cost = 0.0
        for l in t.legs:
            worst = l.entry_day_low if l.side == "SELL" else l.entry_day_high
            fill = l.entry_price + f * (worst - l.entry_price)
            sign = -1.0 if l.side == "SELL" else 1.0
            gross += sign * (l.exit_price - fill) * l.quantity
            cost += condor_leg_costs(l.side, fill, l.exit_price, l.quantity)
        net = gross - cost; tot += net; wins += net > 0
    print(f"  f={f:4.2f}  net {tot:>12,.0f}   win% {wins/len(tr)*100:5.1f}   "
          f"{'PROFITABLE' if tot>0 else 'LOSS'}")
