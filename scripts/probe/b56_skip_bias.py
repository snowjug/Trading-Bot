"""Does the ATM+/-6 window silently drop Bots 5/6's biggest moves?"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from src.research.bot56_real_option_model import load_option_grid_5m, simulate_real_option_trades
from src.research.bot5_point_in_time import generate_signals_point_in_time
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
sys.path.insert(0,"scripts"); from validate_bot56_real_options import underlying

g = load_option_grid_5m(); d = underlying(); s = ActiveMomentumOptionScalperStrategy()
sig = generate_signals_point_in_time(s, d)
tr = simulate_real_option_trades(d, sig, g, s.target_atr_mult, s.stop_atr_mult, 65)
traded = {t.date for t in tr}

# Signal days that had option data but produced no trade
days = set(g["ce"].datetime.dt.date) & set(g["pe"].datetime.dt.date)
m = sig.merge(d[["datetime","close","high","low"]], on="datetime", how="left")
m["sess"] = m.datetime.dt.date
sigdays = m[(m.signal != 0) & (m.sess.isin(days))]
print(f"signal days with option data: {len(sigdays)}   trades produced: {len(tr)}")

# Intraday range on each session from the grid's own spot path
rng = (g["ce"].groupby(g["ce"].datetime.dt.date)["spot"]
       .agg(lambda x: x.max()-x.min()).rename("intraday_range"))
sd = sigdays.copy(); sd["rng"] = sd.sess.map(rng)
sd["traded"] = sd.sess.astype(str).isin(traded)
a = sd[sd.traded]; b = sd[~sd.traded]
print(f"\nINTRADAY SPOT RANGE on signal days")
print(f"  traded   : n={len(a):4d} mean {a.rng.mean():7.2f} median {a.rng.median():7.2f} p90 {a.rng.quantile(.9):7.2f} max {a.rng.max():7.2f}")
print(f"  no trade : n={len(b):4d} mean {b.rng.mean():7.2f} median {b.rng.median():7.2f} p90 {b.rng.quantile(.9):7.2f} max {b.rng.max():7.2f}")
print(f"\n  >300pt range: traded {100*(a.rng>300).mean():.1f}%   not traded {100*(b.rng>300).mean():.1f}%")
