import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import pandas as pd, numpy as np
from src.research.bot56_real_option_model import load_option_grid_5m, simulate_real_option_trades
from src.research.bot5_point_in_time import generate_signals_point_in_time
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
sys.path.insert(0,"scripts"); from validate_bot56_real_options import underlying
g=load_option_grid_5m(); d=underlying(); b5=ActiveMomentumOptionScalperStrategy()
tr=simulate_real_option_trades(d, generate_signals_point_in_time(b5,d), g,
                               b5.target_atr_mult, b5.stop_atr_mult, 65)
t=pd.DataFrame([x.__dict__ for x in tr])
print("trades",len(t))
print("\nSAMPLE (first 6):")
print(t.head(6)[["date","option_type","strike","entry_time","exit_time","entry_spot","exit_spot",
                 "entry_option_price","exit_option_price","exit_reason","net_pnl"]].to_string(index=False))
print("\nDIRECTION COHERENCE")
t["spot_move"]=t.exit_spot-t.entry_spot; t["opt_move"]=t.exit_option_price-t.entry_option_price
ce=t[t.option_type=="CE"]; pe=t[t.option_type=="PE"]
print(f"  CE: corr(spot_move, opt_move) = {ce.spot_move.corr(ce.opt_move):.3f}  n={len(ce)}")
print(f"  PE: corr(spot_move, opt_move) = {pe.spot_move.corr(pe.opt_move):.3f}  n={len(pe)}  (should be NEGATIVE)")
print("\nSPOT-ONLY P&L (was the SPOT call right, ignoring options?)")
t["spot_dir_pnl"]=np.where(t.option_type=="CE", t.spot_move, -t.spot_move)
print(f"  mean directional spot move captured: {t.spot_dir_pnl.mean():.2f} pts")
print(f"  fraction of trades where spot moved the right way: {(t.spot_dir_pnl>0).mean()*100:.1f}%")
print("\nOPTION DECAY: mean option move vs mean spot-implied move")
print(f"  mean option price change: {t.opt_move.mean():.2f} pts")
print(f"  mean |spot move|: {t.spot_move.abs().mean():.2f} pts")
print(f"  mean holding (entry->exit): {(pd.to_datetime(t.exit_time,format='%H:%M:%S')-pd.to_datetime(t.entry_time,format='%H:%M:%S')).mean()}")
print("\nEXITS:", t.exit_reason.value_counts().to_dict())
print("by exit reason, mean net:", t.groupby('exit_reason').net_pnl.mean().round(0).to_dict())
