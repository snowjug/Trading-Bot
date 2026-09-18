"""
Bot 1 — the decisive question, answered on the FULL history.

Whether a condor makes money is dominated by how often the shorts are breached.
That depends only on spot, VIX, the strike formula and the settlement price — not
on option prices, not on lot size. So it can be measured over 2019-2026, whereas
the priced backtest is confined to the UDiFF era (2024+) where the exchange
publishes an authentic lot size.
"""
import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd, numpy as np
from src.research.bot1_condor_real import load_bhavcopy_store, run_real_condor_backtest, run_breach_study
from src.research import validation as V
sys.path.insert(0, "scripts"); from validate_bot1_condor import underlying

store = load_bhavcopy_store(); d = underlying()
print(f"underlying {len(d)} sessions {d.datetime.min().date()}..{d.datetime.max().date()}")

# Break-even comes from PRICED trades (UDiFF era); the rate comes from the full history.
priced = run_real_condor_backtest(d, store, signal_lag=0)
pt = priced["trades"]
lot = int(pd.Series([t.lot_size for t in pt]).mode().iloc[0])
credit = float(np.mean([t.net_credit_points for t in pt]))
maxloss = float(np.mean([t.max_loss_points for t in pt]))
costs = float(np.mean([t.costs for t in pt]))
be = V.breakeven_adverse_rate(credit*lot - costs, -(maxloss*lot + costs))
print(f"\nPRICED SAMPLE (lot-size available): {len(pt)} trades  credit {credit:.2f} pts  "
      f"max loss {maxloss:.2f} pts  -> break-even breach rate {be:.4f}")

res = run_breach_study(d, store, signal_lag=0)
c = res["cycles"]
print(f"\nBREACH STUDY (no prices needed): {len(c)} weekly cycles "
      f"{c.entry_date.min()} .. {c.entry_date.max()}")
print("  settlement sources:", c.settlement_source.value_counts().to_dict())
print("  rejects:", dict(sorted(res['rejects'].items(), key=lambda x:-x[1])[:6]))

nb = int(c.breached.sum())
v = V.sample_size_verdict(len(c), nb, be)
print(f"\n  breached          {nb}/{len(c)} = {v['adverse_rate']:.4f}  CI95 {v['adverse_ci95']}")
print(f"  beyond the wing   {int(c.beyond_wing.sum())}/{len(c)} = {c.beyond_wing.mean():.4f}")
print(f"  break-even        {be:.4f}")
print(f"  VERDICT           {v['verdict']}")
print(f"    {v['reason']}")

print("\n  BY YEAR")
c["yr"]=pd.to_datetime(c.entry_date).dt.year
g=c.groupby("yr").agg(cycles=("breached","size"), breached=("breached","sum"),
                      rate=("breached","mean"), med_vix=("vix","median"))
print(g.round(4).to_string())
print("\n  BY VIX BUCKET")
c["vb"]=pd.cut(c.vix,[0,12,14,16,18,20])
print(c.groupby("vb", observed=True).agg(cycles=("breached","size"),
      breached=("breached","sum"), rate=("breached","mean")).round(4).to_string())
# ── EXPECTANCY IN POINTS, over the full history ──
# A breach is not automatically a maximum loss: the settlement usually lands
# between the short strike and the wing. Charging max loss for every breach is far
# too harsh, and inferring the tail from the four realised losses in the priced
# sample is far too few. Both are avoided by computing each cycle's loss directly
# from how far the settlement actually travelled past the short, capped by the wing.
exc = np.where(c.breach_side.eq("call"), c.spot_settle - c.short_call,
      np.where(c.breach_side.eq("put"), c.short_put - c.spot_settle, 0.0))
wing = np.where(c.breach_side.eq("call"), c.long_call - c.short_call,
       np.where(c.breach_side.eq("put"), c.short_put - c.long_put, 0.0))
c["loss_points"] = np.minimum(np.clip(exc, 0, None),
                              np.where(wing > 0, wing, np.inf))
# Use the credit ACTUALLY observed for each cycle wherever all four legs priced,
# rather than importing a later era's mean into earlier volatility regimes.
priced_mask = c["legs_priced"].fillna(False).astype(bool)
c["credit_used"] = np.where(priced_mask, c["observed_credit_points"], np.nan)
c["pnl_points"] = c["credit_used"] - c["loss_points"]
print(f"\n  CREDIT SOURCE: {int(priced_mask.sum())}/{len(c)} cycles priced from four real "
      f"fills; {int((~priced_mask).sum())} unpriceable and EXCLUDED (not back-filled)")
cp = c[priced_mask]
print(f"    observed credit: mean {cp.credit_used.mean():.2f} pts  "
      f"median {cp.credit_used.median():.2f}  min {cp.credit_used.min():.2f}  "
      f"max {cp.credit_used.max():.2f}")
c = cp.reset_index(drop=True)

print(f"\n  EXPECTANCY OVER {len(c)} PRICED CYCLES — each uses its OWN observed credit")
print(f"    GROSS mean P&L       {c.pnl_points.mean():+8.2f} pts/cycle "
      f"= Rs {c.pnl_points.mean() * lot:+,.0f} per lot")

# Costs and slippage decide this. The gross edge is single-digit POINTS while a
# condor pays statutory charges on four legs and crosses a spread on each of them,
# so both are charged here rather than left to a footnote. The per-cycle cost comes
# from the priced sample's own realised charges, converted to points at that
# sample's authentic lot size.
cost_points = costs / lot
print(f"    statutory costs      {-cost_points:+8.2f} pts/cycle "
      f"(Rs {costs:,.0f} per lot, from the priced sample's realised charges)")
for slip in (0.0, 0.25, 0.5, 1.0):
    net = c.pnl_points.mean() - cost_points - slip * 4
    tt = V.tstat((c.pnl_points - cost_points - slip * 4).tolist())
    print(f"    NET @ {slip:.2f} pt/leg slippage  {net:+7.2f} pts/cycle "
          f"= Rs {net * lot:+8,.0f}/lot   t={tt:+.2f}   "
          f"{'POSITIVE' if net > 0 else 'NEGATIVE'}")
brl = c.loss_points[c.breached]
print(f"    loss when breached   {brl.mean():8.2f} pts  (max {c.loss_points.max():.2f}, "
      f"wing cap ~{wing[wing > 0].mean():.0f})")
print(f"    total over sample    Rs {c.pnl_points.sum() * lot:+,.0f} per lot")
print(f"    credit needed to break even: {c.loss_points.mean():.2f} pts vs "
      f"{c.credit_used.mean():.2f} actually collected")
tv = V.tstat(c.pnl_points.tolist())
print(f"    t-stat {tv:+.3f}  -> {'POSITIVE' if c.pnl_points.mean() > 0 else 'NEGATIVE'}")
oos = V.chronological_split(c.pnl_points.tolist(), c.entry_date.tolist())
if "is" in oos:
    print(f"    OOS 70/30 @ {oos['split_date']}: IS {oos['is']['mean']:+.2f} | "
          f"OOS {oos['oos']['mean']:+.2f} pts/cycle | sign agrees {oos['sign_agreement']}")
wf = V.walk_forward(c.pnl_points.tolist(), c.entry_date.tolist(), folds=4)
if "folds" in wf:
    print(f"    walk-forward: {wf['folds_positive']}/{wf['folds_total']} folds positive  "
          + str([f"{f['start'][:7]}:{f['mean']:+.1f}" for f in wf["folds"]]))
mc = V.monte_carlo_paths(c.pnl_points.tolist())
print(f"    Monte Carlo P(total<0) {mc['prob_final_negative']:.3f}  "
      f"median MaxDD {mc['max_drawdown_median']:.1f} pts")

print(f"\n  realised move / expected move: mean {c.move_in_expected_moves.mean():.3f} "
      f"p90 {c.move_in_expected_moves.quantile(.9):.3f} max {c.move_in_expected_moves.max():.3f}")
json.dump({"cycles":len(c),"breached":nb,"breakeven":be,"verdict":v,
           "by_year":g.reset_index().to_dict("records")},
          open("reports/bot1_breach_study.json","w"), indent=2, default=str)
print("\nwrote reports/bot1_breach_study.json")
