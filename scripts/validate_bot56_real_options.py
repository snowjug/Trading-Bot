"""
Bots 5 and 6 — real option economics on the DEEP 5-minute grid, plus validation.

SUPERSEDES the earlier n=8 / n=3 result, which rested on a 10-session cache. With
a renewed token the same endpoint serves ~6 years of 5-minute bars, so the
question moves from "there is no data" to "what does the data actually say".

Nothing about either strategy is changed. Bot 5 keeps its causal point-in-time
provider; Bot 6 is frozen and keeps its own `generate_signals`. Only the PRICING
and the SAMPLE change.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research import validation as V
from src.research.bot5_point_in_time import generate_signals_point_in_time
from src.research.bot56_real_option_model import (
    EXECUTION_BASIS,
    available_option_days,
    load_option_grid,
    load_option_grid_5m,
    simulate_real_option_trades,
    summarise_real,
)
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.strategies.micro_momentum_buyer import MicroMomentumBuyerStrategy

# Variants executed, declared up front for the multiple-testing haircut:
# Bot 5 deep, Bot 6 deep, Bot 5 legacy-cache, Bot 6 legacy-cache.
VARIANTS_EXAMINED = 4
LOT_SIZE_NOTE = (
    "NIFTY's lot size is not constant over 2020-2026 (75 -> 65, with both live "
    "during the transition). Per-lot rupee figures below use the CURRENT 65 and are "
    "therefore comparable across variants but not a historical account statement."
)


def underlying(start: str = "2020-01-01") -> pd.DataFrame:
    """NIFTY + India VIX daily history from the authentic NSE archive."""
    p = Path("data/raw/nse/index_history/nse_index_daily.parquet")
    if p.exists():
        raw = pd.read_parquet(p)
        n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
        v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
        df = n.merge(v, on="datetime", how="inner")
        df = df[df["datetime"] >= start].sort_values("datetime").reset_index(drop=True)
        if len(df) > 200:
            df["volume"] = 0.0
            return df
    n = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    v = pd.read_csv("data/real_2026/INDEX_INDIAVIX_daily.csv")
    n["datetime"] = pd.to_datetime(n["datetime"])
    v["datetime"] = pd.to_datetime(v["datetime"])
    return n.merge(v[["datetime", "close"]].rename(columns={"close": "vix"}), on="datetime")


def run_bot(name: str, strategy, signals: pd.DataFrame, daily: pd.DataFrame,
            grid: dict, lot: int, max_per_day=None) -> list:
    return simulate_real_option_trades(
        daily, signals, grid, strategy.target_atr_mult, strategy.stop_atr_mult,
        lot, max_per_day,
    )


def report(tag: str, trades: list, out: dict, lot: int) -> None:
    s = summarise_real(trades)
    print(f"\n{'=' * 78}\n{tag}\n{'=' * 78}")
    if s["total_trades"] == 0:
        print("  NO TRADES —", s.get("note"))
        out[tag] = s
        return
    df = pd.DataFrame([t.__dict__ for t in trades])
    pnl = df["net_pnl"].tolist()
    dates = df["date"].tolist()

    for k in ("total_trades", "net_profit", "gross_profit", "total_costs",
              "win_rate", "max_drawdown_pct", "avg_entry_price"):
        print(f"  {k:24s} {s[k]:>14.2f}")
    print(f"  exit_reasons            {s['exit_reasons']}")
    print(f"  sessions covered        {df['date'].nunique()}")
    print(f"  expectancy/trade        {np.mean(pnl):>14.2f}")

    wins = df[df["net_pnl"] > 0]["net_pnl"]
    loss = df[df["net_pnl"] <= 0]["net_pnl"]
    be = V.breakeven_adverse_rate(float(wins.mean()) if len(wins) else 0.0,
                                  float(loss.mean()) if len(loss) else 0.0)
    n_adverse = int((df["net_pnl"] <= 0).sum())
    verdict = V.sample_size_verdict(len(df), n_adverse, be)
    print(f"\n  break-even loss rate    {be:.4f}" if be else "\n  break-even loss rate    n/a")
    print(f"  observed loss rate      {n_adverse}/{len(df)} = {verdict.get('adverse_rate', float('nan')):.4f}"
          f"  CI95 {verdict.get('adverse_ci95')}")
    print(f"  VERDICT                 {verdict['verdict']}")
    print(f"    {verdict['reason']}")

    t = V.tstat(pnl)
    out[tag] = {
        "summary": s, "sessions_covered": int(df["date"].nunique()),
        "expectancy_per_trade": float(np.mean(pnl)),
        "breakeven_loss_rate": be, "sample_size_verdict": verdict,
        "oos": V.chronological_split(pnl, dates),
        "walk_forward": V.walk_forward(pnl, dates, folds=4),
        "monte_carlo": V.monte_carlo_paths(pnl),
        "resample_control": V.resample_control(pnl),
        "tstat": t,
        "multiple_testing": V.deflated_expectation(VARIANTS_EXAMINED, t, len(pnl)),
        "lot_size_note": LOT_SIZE_NOTE,
        "execution_basis": EXECUTION_BASIS,
    }

    # Slippage: these bots BUY options, so an adverse fill costs on entry and exit.
    steps = [0.0, 0.25, 0.5, 1.0, 2.0]
    out[tag]["slippage_sensitivity"] = V.slippage_sensitivity(
        pnl, [x * 2 * lot for x in steps], [f"+{x} pt/side" for x in steps])
    print("\n  SLIPPAGE SENSITIVITY (extra cost on entry and exit)")
    for r in out[tag]["slippage_sensitivity"]:
        print(f"    {r['label']:>13s}  net {r['net']:>12,.0f}  mean {r['mean']:>9,.0f}  "
              f"win% {r['win_rate']:5.1f}  {'PROFITABLE' if r['still_profitable'] else 'LOSS'}")

    o = out[tag]["oos"]
    if "is" in o:
        print(f"\n  OOS 70/30 @ {o['split_date']}: IS {o['is']['net']:,.0f} (n={o['is']['n']})"
              f" | OOS {o['oos']['net']:,.0f} (n={o['oos']['n']}) | sign agrees: {o['sign_agreement']}")
    wf = out[tag]["walk_forward"]
    if "folds" in wf:
        print(f"  WALK-FORWARD: {wf['folds_positive']}/{wf['folds_total']} folds positive"
              + "".join(f"\n    fold {f['fold']} from {f['start']}: n={f['n']:>4d} net={f['net']:>12,.0f}"
                        for f in wf["folds"]))
    mc = out[tag]["monte_carlo"]
    if "paths" in mc:
        print(f"  MONTE CARLO: median MaxDD {mc['max_drawdown_median']:,.0f}, "
              f"5th-pct {mc['max_drawdown_p05_worst']:,.0f}, "
              f"P(final<0) {mc['prob_final_negative']:.3f}")
    mt = out[tag]["multiple_testing"]
    print(f"  t={t:.3f}  p_raw={mt.get('p_raw')}  p_bonferroni={mt.get('p_bonferroni')}  "
          f"survives={mt.get('survives_5pct_after_adjustment')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/bot56_deep_validation.json")
    ap.add_argument("--lot", type=int, default=65)
    args = ap.parse_args()

    deep = load_option_grid_5m()
    if deep is None:
        print("deep grid missing — run scripts/ingest_dhan_option_grid.py")
        return 1
    days = available_option_days(deep)
    print(f"DEEP GRID: {len(days)} sessions {days[0]} .. {days[-1]}   "
          f"ce={len(deep['ce']):,} pe={len(deep['pe']):,} rows   "
          f"strikes={deep['ce']['strike'].nunique()}")

    d = underlying()
    print(f"underlying: {len(d)} sessions {d['datetime'].min().date()} .. {d['datetime'].max().date()}")
    out: dict = {"variants_examined": VARIANTS_EXAMINED,
                 "deep_grid_sessions": len(days),
                 "deep_grid_span": [str(days[0]), str(days[-1])],
                 "lot_size_note": LOT_SIZE_NOTE}

    b5 = ActiveMomentumOptionScalperStrategy()
    sig5 = generate_signals_point_in_time(b5, d)
    report("BOT5_CAUSAL_DEEP_GRID", run_bot("bot5", b5, sig5, d, deep, args.lot), out, args.lot)

    b6 = MicroMomentumBuyerStrategy()
    sig6 = b6.generate_signals(d)
    report("BOT6_FROZEN_DEEP_GRID",
           run_bot("bot6", b6, sig6, d, deep, args.lot, b6.max_trades_per_day), out, args.lot)

    # The superseded 10-session window, kept so the comparison is explicit.
    legacy = load_option_grid()
    if legacy is not None:
        ld = available_option_days(legacy)
        print(f"\n[legacy cache: {len(ld)} sessions — retained only for comparison]")
        report("BOT5_LEGACY_10_SESSION_CACHE",
               run_bot("bot5", b5, sig5, d, legacy, args.lot), out, args.lot)
        report("BOT6_LEGACY_10_SESSION_CACHE",
               run_bot("bot6", b6, sig6, d, legacy, args.lot, b6.max_trades_per_day), out, args.lot)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
