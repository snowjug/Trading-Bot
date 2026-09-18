"""
Bot 1 — full validation battery on the authentic four-leg condor.

Runs the specified strategy, then attacks the result: break-even analysis,
sample-size inference, OOS, walk-forward, slippage and cost stress, regime
breakdown, placebo control, Monte Carlo, and a multiple-testing haircut.

No parameter is searched. Every variant executed is counted and declared.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research.bot1_condor_real import (
    adverse_fill_pnl,
    load_bhavcopy_store,
    run_real_condor_backtest,
    summarise_condor,
)
from src.research import validation as V

# Every distinct configuration this script executes, declared up front so the
# multiple-testing haircut is computed against the real number rather than 1.
VARIANTS_EXAMINED = 4          # specified, causal lag-1, calendar-DTE window, RSI band 38/70


def underlying(index_parquet: str = "data/raw/nse/index_history/nse_index_daily.parquet",
               start: str = "2019-01-01") -> pd.DataFrame:
    """
    NIFTY + India VIX daily history.

    Prefers the extended NSE archive when present, falling back to the repository's
    own history. Both are authentic; the archive simply reaches further back.
    """
    p = Path(index_parquet)
    if p.exists():
        raw = pd.read_parquet(p)
        n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
        v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
        df = n.merge(v, on="datetime", how="inner")
        df = df[df["datetime"] >= start].sort_values("datetime").reset_index(drop=True)
        if len(df) > 200:
            return df
    n = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    v = pd.read_csv("data/real_2026/INDEX_INDIAVIX_daily.csv")
    n["datetime"] = pd.to_datetime(n["datetime"])
    v["datetime"] = pd.to_datetime(v["datetime"])
    return n.merge(v[["datetime", "close"]].rename(columns={"close": "vix"}), on="datetime")


def trades_frame(trades) -> pd.DataFrame:
    return pd.DataFrame([{
        "entry_date": t.entry_date, "expiry": t.expiry, "net_pnl": t.net_pnl,
        "gross_pnl": t.gross_pnl, "costs": t.costs, "credit": t.net_credit_points,
        "max_loss": t.max_loss_points, "breached": t.breached, "vix": t.vix_entry,
        "spot_entry": t.spot_entry, "spot_settle": t.spot_settle,
        "expected_move": t.expected_move, "lot": t.lot_size,
        "short_call": next(l.strike for l in t.legs if l.role == "short_call"),
        "short_put": next(l.strike for l in t.legs if l.role == "short_put"),
    } for t in trades])


def structural_diagnostics(df: pd.DataFrame) -> dict:
    """
    Is the structure placed where its label claims?

    The specification prices the expected move over FIVE days while the position is
    actually held for SEVEN calendar days. If that under-scales time, the shorts sit
    nearer than "1.8 SD" implies and the breach probability is higher than the label
    suggests. Measured, not assumed — and deliberately NOT corrected, because
    changing the formula would change the strategy.
    """
    move = (df["spot_settle"] - df["spot_entry"]).abs()
    # The realised one-week move expressed in units of the expected move used to
    # place the strikes.
    z = move / df["expected_move"]
    short_dist_sd = ((df["short_call"] - df["spot_entry"]) / df["expected_move"])
    seven_day_scale = float(np.sqrt(7.0 / 5.0))
    return {
        "realised_move_over_expected_move": {
            "mean": float(z.mean()), "p50": float(z.median()),
            "p90": float(z.quantile(0.90)), "max": float(z.max()),
        },
        "short_strike_distance_in_expected_moves": {
            "mean": float(short_dist_sd.mean()), "min": float(short_dist_sd.min()),
        },
        "time_scaling_note": (
            "expected move uses sqrt(5/365) while the position is held ~7 calendar "
            f"days; the true holding-period sigma is {seven_day_scale:.3f}x larger, so a "
            f"strike labelled 1.8 SD sits at about {1.8 / seven_day_scale:.2f} SD of the "
            "actual holding-period distribution"
        ),
        "effective_sd_of_short_strike": round(1.8 / seven_day_scale, 4),
    }


def report(tag: str, res: dict, out: dict) -> None:
    tr = res["trades"]
    s = summarise_condor(tr)
    print(f"\n{'=' * 78}\n{tag}\n{'=' * 78}")
    print(f"entry_rule={res.get('entry_rule')}  signal_lag={res['signal_lag']}  trades={s['total_trades']}")
    if s["total_trades"] == 0:
        print("  NO TRADES.", dict(sorted(res["rejects"].items(), key=lambda x: -x[1])[:6]))
        out[tag] = {"summary": s, "rejects": res["rejects"]}
        return

    df = trades_frame(tr)
    pnl = df["net_pnl"].tolist()
    dates = df["entry_date"].tolist()

    for k in ("total_trades", "net_pnl_per_lot", "total_costs_per_lot", "win_rate",
              "breach_rate", "avg_credit_points", "avg_max_loss_points",
              "avg_win", "avg_loss", "expectancy_per_trade", "max_drawdown_rupees_per_lot"):
        v = s[k]
        print(f"  {k:34s} {v:>14.2f}" if isinstance(v, float) else f"  {k:34s} {v!s:>14}")

    # ── break-even and whether the sample can resolve it ──
    lot = int(df["lot"].mode().iloc[0])
    struct_win = float(df["credit"].mean() * lot - df["costs"].mean())
    struct_loss = -float(df["max_loss"].mean() * lot + df["costs"].mean())
    be_struct = V.breakeven_adverse_rate(struct_win, struct_loss)
    emp_win = s["avg_win"]
    emp_loss = s["avg_loss"]
    be_emp = V.breakeven_adverse_rate(emp_win, emp_loss) if emp_loss < 0 else None

    n_breach = int(df["breached"].sum())
    verdict_struct = V.sample_size_verdict(len(df), n_breach, be_struct)
    print(f"\n  STRUCTURAL break-even breach rate : {be_struct:.4f}"
          f"   (win {struct_win:,.0f} vs worst-case loss {struct_loss:,.0f})")
    print(f"  observed breach rate              : {n_breach}/{len(df)} = "
          f"{verdict_struct['adverse_rate']:.4f}  CI95 {verdict_struct['adverse_ci95']}")
    print(f"  VERDICT                           : {verdict_struct['verdict']}")
    print(f"    {verdict_struct['reason']}")
    need = V.trades_needed(be_struct, max(verdict_struct["adverse_rate"], 0.005))
    if need:
        print(f"  trades needed for a conclusive CI : ~{need} "
              f"(~{need / 45:.0f} years at ~45 weekly cycles/yr)")

    t = V.tstat(pnl)
    out[tag] = {
        "summary": s,
        "structural": structural_diagnostics(df),
        "breakeven_structural": be_struct,
        "breakeven_empirical": be_emp,
        "sample_size_verdict": verdict_struct,
        "trades_needed_for_conclusive_ci": need,
        "oos": V.chronological_split(pnl, dates),
        "walk_forward": V.walk_forward(pnl, dates, folds=4),
        "monte_carlo": V.monte_carlo_paths(pnl),
        "resample_control": V.resample_control(pnl),
        "regime_vix": V.regime_breakdown(pnl, df["vix"].tolist(), [0, 12, 14, 16, 18, 20]),
        "tstat": t,
        "multiple_testing": V.deflated_expectation(VARIANTS_EXAMINED, t, len(pnl)),
        "rejects": res["rejects"],
    }

    # ── slippage: the decisive test for a small-credit structure ──
    steps = [0.0, 0.25, 0.5, 1.0, 2.0]
    extra = [x * 4 * lot for x in steps]     # x points on each of four legs
    labels = [f"+{x} pt/leg" for x in steps]
    out[tag]["slippage_sensitivity"] = V.slippage_sensitivity(pnl, extra, labels)
    print("\n  SLIPPAGE SENSITIVITY (extra cost on each of 4 legs)")
    for r in out[tag]["slippage_sensitivity"]:
        print(f"    {r['label']:>12s}  net {r['net']:>12,.0f}  mean {r['mean']:>9,.0f}  "
              f"win% {r['win_rate']:5.1f}  {'PROFITABLE' if r['still_profitable'] else 'LOSS'}")

    # ── adverse fill: the worst price that actually traded on the entry session ──
    adv = [adverse_fill_pnl(t) for t in tr]
    usable = [a for a in adv if a is not None]
    if usable:
        a_pnl = [a["net_pnl"] for a in usable]
        base_sub = [t.net_pnl for t, a in zip(tr, adv) if a is not None]
        out[tag]["adverse_fill"] = {
            "trades_repriced": len(usable),
            "trades_unpriceable": len(adv) - len(usable),
            "net_at_close_fills": float(sum(base_sub)),
            "net_at_worst_traded_fills": float(sum(a_pnl)),
            "mean_credit_at_close": float(np.mean([t.net_credit_points for t, x in zip(tr, adv) if x is not None])),
            "mean_credit_at_worst": float(np.mean([a["net_credit_points"] for a in usable])),
            "win_rate": float(np.mean([p > 0 for p in a_pnl]) * 100),
            "still_profitable": bool(sum(a_pnl) > 0),
        }
        af = out[tag]["adverse_fill"]
        print("\n  ADVERSE FILL (sell the day's LOW, buy the day's HIGH — real prints)")
        print(f"    credit {af['mean_credit_at_close']:.2f} pts -> {af['mean_credit_at_worst']:.2f} pts")
        print(f"    net {af['net_at_close_fills']:,.0f} -> {af['net_at_worst_traded_fills']:,.0f}"
              f"   win% {af['win_rate']:.1f}   "
              f"{'PROFITABLE' if af['still_profitable'] else 'LOSS'}"
              f"   ({af['trades_unpriceable']} unpriceable)")

    # ── capital viability: what this structure actually ties up ──
    max_loss_rupees = float(df["max_loss"].mean() * lot)
    out[tag]["capital_viability"] = {
        "lot_size": lot,
        "avg_max_loss_per_lot_rupees": round(max_loss_rupees, 2),
        "avg_credit_per_lot_rupees": round(float(df["credit"].mean() * lot), 2),
        "expectancy_per_lot_rupees": round(float(df["net_pnl"].mean()), 2),
        "margin_basis": (
            "DEFINED_RISK_MAX_LOSS. SPAN/exposure margin is not obtainable "
            "read-only, so capital is sized on the structural maximum loss, which "
            "is computable exactly. Real SPAN for a hedged condor is close to but "
            "not identical to this — treat lot counts as indicative."
        ),
    }
    for cap in (50_000, 100_000):
        lots = int((cap * 0.65) // max_loss_rupees) if max_loss_rupees > 0 else 0
        out[tag]["capital_viability"][f"lots_at_{cap}"] = lots
        out[tag]["capital_viability"][f"weekly_expectancy_at_{cap}"] = round(
            lots * float(df["net_pnl"].mean()), 2)
    cv = out[tag]["capital_viability"]
    print(f"\n  CAPITAL: max loss {cv['avg_max_loss_per_lot_rupees']:,.0f}/lot "
          f"(credit {cv['avg_credit_per_lot_rupees']:,.0f}) -> "
          f"50k: {cv['lots_at_50000']} lot(s), 1L: {cv['lots_at_100000']} lot(s)")

    o = out[tag]["oos"]
    if "is" in o:
        print(f"\n  OOS 70/30 @ {o['split_date']}: IS net {o['is']['net']:,.0f} (n={o['is']['n']})"
              f" | OOS net {o['oos']['net']:,.0f} (n={o['oos']['n']})"
              f" | sign agrees: {o['sign_agreement']}")
    wf = out[tag]["walk_forward"]
    if "folds" in wf:
        print(f"  WALK-FORWARD: {wf['folds_positive']}/{wf['folds_total']} folds positive"
              + "".join(f"\n    fold {f['fold']} from {f['start']}: n={f['n']:>3d} net={f['net']:>12,.0f}"
                        for f in wf["folds"]))
    mc = out[tag]["monte_carlo"]
    if "paths" in mc:
        print(f"  MONTE CARLO ({mc['paths']} reorderings): median MaxDD {mc['max_drawdown_median']:,.0f}, "
              f"5th-pct MaxDD {mc['max_drawdown_p05_worst']:,.0f}")
    st = out[tag]["structural"]
    print(f"\n  STRUCTURE: {st['time_scaling_note']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/bot1_validation.json")
    args = ap.parse_args()

    store = load_bhavcopy_store()
    if store is None:
        print("NO BHAVCOPY STORE"); return 1
    d = underlying()
    print(f"underlying: {len(d)} sessions {d['datetime'].min().date()} .. {d['datetime'].max().date()}")
    print(f"bhavcopy  : {len(store):,} rows, {store['TradDt'].nunique()} sessions, "
          f"{store['XpryDt'].nunique()} expiries")

    out: dict = {"variants_examined": VARIANTS_EXAMINED, "coverage": {
        "underlying_sessions": int(len(d)),
        "bhavcopy_sessions": int(store["TradDt"].nunique()),
        "first": str(store["TradDt"].min()), "last": str(store["TradDt"].max()),
    }}

    report("AS_SPECIFIED", run_real_condor_backtest(d, store, signal_lag=0), out)
    report("CAUSAL_LAG1", run_real_condor_backtest(d, store, signal_lag=1), out)
    report("CALENDAR_DTE_WINDOW_3_9",
           run_real_condor_backtest(d, store, signal_lag=0, entry_dte_min=3, entry_dte_max=9), out)
    report("RSI_BAND_38_70_AS_IN_SIMULATOR",
           run_real_condor_backtest(d, store, signal_lag=0, min_rsi=38.0, max_rsi=70.0), out)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
