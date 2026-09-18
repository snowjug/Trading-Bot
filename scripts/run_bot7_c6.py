"""Bot 7 / C6 — expiry-day defined-risk iron fly, pre-registered in the ledger."""
import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd, numpy as np
from src.research import bot7_discovery as B7
from src.research import validation as V
from src.research.bot56_real_option_model import load_option_grid_5m
from src.research.bot1_condor_real import load_bhavcopy_store, weekly_expiry_calendar, ChainIndex

VARIANTS = 8   # C1, C2x3, C3, C4, C5(descriptive), C6

grid = load_option_grid_5m()
store = load_bhavcopy_store()
expiries = set(weekly_expiry_calendar(store))
sessions = sorted(set(grid["ce"]["datetime"].dt.date) & set(grid["pe"]["datetime"].dt.date))
exp_days = [d for d in sessions if d in expiries]
print(f"expiry sessions with 5-min option data: {len(exp_days)} "
      f"({exp_days[0]} .. {exp_days[-1]})")

# Exit by exact cash settlement, so no session can be dropped for having moved
# too far — the failure mode that made the first version of C6 an artefact.
chains = ChainIndex(store)
idx = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
n = idx[idx.symbol == "NIFTY50"]
closes = {d.date(): float(c) for d, c in zip(pd.to_datetime(n.datetime), n.close)}
settlements = {}
for d in exp_days:
    v = chains.settlement(d, closes)
    if v:
        settlements[d] = v
print(f"expiry sessions with a settlement price: {len(settlements)}")

tr = B7.c6_expiry_iron_fly_settled(grid, settlements)
print(f"trades priced: {len(tr)}  (entries dropped: {len(settlements)-len(tr)})")
if not tr:
    print("NO TRADES"); raise SystemExit(0)

df = pd.DataFrame([t.__dict__ for t in tr])
pnl = df.net_pnl.tolist(); dates = df.date.tolist()
a = np.array(pnl)
print(f"\n  net Rs {a.sum():,.0f}   expectancy Rs {a.mean():,.2f}   win% {(a>0).mean()*100:.1f}")
print(f"  gross Rs {df.gross_pnl.sum():,.0f}   costs Rs {df.costs.sum():,.0f}")
print(f"  mean credit {df.credit_points.mean():.2f} pts   "
      f"max loss cap {4*50:.0f} pts   worst trade Rs {a.min():,.0f}")
t = V.tstat(pnl); mt = V.deflated_expectation(VARIANTS, t, len(pnl))
print(f"  t={t:+.3f}  p_raw={mt['p_raw']}  p_bonferroni={mt['p_bonferroni']}  "
      f"survives={mt['survives_5pct_after_adjustment']}")
oos = V.chronological_split(pnl, dates)
print(f"  OOS 70/30 @ {oos['split_date']}: IS {oos['is']['mean']:+,.2f} | "
      f"OOS {oos['oos']['mean']:+,.2f} | sign agrees {oos['sign_agreement']}")
wf = V.walk_forward(pnl, dates, folds=4)
print(f"  walk-forward {wf['folds_positive']}/{wf['folds_total']} positive  "
      + str([f"{f['start'][:7]}:{f['mean']:+,.0f}" for f in wf["folds"]]))
mc = V.monte_carlo_paths(pnl)
print(f"  Monte Carlo P(total<0) {mc['prob_final_negative']}  "
      f"median MaxDD Rs {mc['max_drawdown_median']:,.0f}  "
      f"5th-pct MaxDD Rs {mc['max_drawdown_p05_worst']:,.0f}")
sl = V.slippage_sensitivity(pnl, [s*4*B7.LOT for s in (0,0.25,0.5,1.0)],
                            [f"+{s} pt/leg" for s in (0,0.25,0.5,1.0)])
print("  slippage: " + "  ".join(
    f"{r['label']}={r['net']:,.0f}{'+' if r['still_profitable'] else '-'}" for r in sl))

# The counter-hypothesis check the ledger demanded: expectancy, not win rate.
wins = a[a>0]; loss = a[a<=0]
print(f"\n  win/loss shape: {len(wins)} wins avg Rs {wins.mean():,.0f} | "
      f"{len(loss)} losses avg Rs {loss.mean() if len(loss) else 0:,.0f}")
print(f"  worst 5 trades: {sorted(a)[:5]}")

profitable = a.sum() > 0
consistent = wf["folds_positive"] == wf["folds_total"]
slip_ok = all(r["still_profitable"] for r in sl)
survives = bool(mt["survives_5pct_after_adjustment"]) and profitable
verdict = "SURVIVED" if (survives and consistent and slip_ok) else "REJECTED"
reasons = []
if not profitable: reasons.append("net negative")
if not mt["survives_5pct_after_adjustment"]: reasons.append("fails multiple-testing adjustment")
if not consistent: reasons.append(f"only {wf['folds_positive']}/{wf['folds_total']} folds positive")
if not slip_ok: reasons.append("does not survive slippage")
print(f"\n  VERDICT: {verdict}" + (f"  ({'; '.join(reasons)})" if reasons else ""))

json.dump({"trades": len(tr), "net": float(a.sum()), "expectancy": float(a.mean()),
           "win_rate": float((a>0).mean()*100), "tstat": t, "multiple_testing": mt,
           "oos": oos, "walk_forward": wf, "monte_carlo": mc, "slippage": sl,
           "verdict": verdict, "rejection_reasons": reasons},
          open("reports/bot7_c6_iron_fly.json","w"), indent=2, default=str)
print("wrote reports/bot7_c6_iron_fly.json")
