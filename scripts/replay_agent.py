"""
Replay the AI trading agent over history. Default decider is deterministic, so this
makes ZERO model calls unless `--decider llm` is passed explicitly.

    python scripts/replay_agent.py --start 2024-01-01 --end 2024-09-17 --equity 1500000

Splits, per the directive:
    DEV         2020-2023
    VALIDATION  2024
    OOS         2025-2026   (frozen; run once, no tuning afterwards)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time as dtime

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.deciders import HeuristicDecider
from src.agent.trading_agent import TradingAgent
from src.market.market_state import StateBuilder, resample
from src.options.chain import ReplayChain
from src.research.agent_replay import (
    baseline_buy_and_hold, baseline_ema_cross, baseline_no_trade,
    baseline_random_entry, metrics, run_replay,
)
from src.risk.structure_risk import RiskLimits

SPOT5 = "data/derived/nifty_spot_5m.parquet"
GRID_CE = "data/derived/grid5m_ce.parquet"
GRID_PE = "data/derived/grid5m_pe.parquet"
LOTCAL = "data/catalog/lot_size_calendar.csv"


def load_limits(path: str = "configs/risk.yaml") -> RiskLimits:
    cfg = yaml.safe_load(open(path, encoding="utf-8"))["risk"]
    lm = RiskLimits()
    for k, v in cfg.items():
        if k in ("no_entry_before", "no_entry_after"):
            h, m = str(v).split(":")
            setattr(lm, k, dtime(int(h), int(m)))
        elif hasattr(lm, k):
            setattr(lm, k, v)
    return lm


def load_setup_cfg(path: str = "configs/market.yaml") -> dict:
    return yaml.safe_load(open(path, encoding="utf-8")).get("setups", {})


def lot_lookup(path: str = LOTCAL):
    """AUTHENTIC lot size per month. Returns None when unknown — never a guess."""
    c = pd.read_csv(path)
    c = c[c["symbol"] == "NIFTY"]
    m = {str(k): int(round(float(v))) for k, v in zip(c["month"], c["lot"])}

    def f(d: date):
        return m.get(f"{d.year}-{d.month:02d}")
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2024-09-17")
    ap.add_argument("--equity", type=float, default=1_500_000.0)
    ap.add_argument("--decider", default="heuristic", choices=["heuristic", "llm"])
    ap.add_argument("--cost-mult", type=float, default=1.0)
    ap.add_argument("--risk-pct", type=float, default=None,
                    help="override risk_per_trade_pct for a sensitivity run")
    ap.add_argument("--out", default="")
    ap.add_argument("--max-bars", type=int, default=0)
    args = ap.parse_args()

    if args.decider == "llm":
        raise SystemExit("--decider llm requires a model callable to be wired in; "
                         "the deterministic baseline is the default on purpose")

    s5 = pd.read_parquet(SPOT5)
    s5["datetime"] = pd.to_datetime(s5["datetime"])
    a, b = pd.Timestamp(args.start).date(), pd.Timestamp(args.end).date()
    win = s5[(s5["datetime"].dt.date >= a) & (s5["datetime"].dt.date <= b)]
    if win.empty:
        raise SystemExit(f"no 5-minute bars between {a} and {b}")

    frames = {"5m": s5, "15m": resample(s5, "15min"), "30m": resample(s5, "30min"),
              "1h": resample(s5, "60min"), "1d": resample(s5, "1D")}
    builder = StateBuilder("NIFTY", frames, primary_tf="5m", source="REPLAY_GRID")
    chain = ReplayChain(GRID_CE, GRID_PE, ladder_half_width=6)

    limits = load_limits()
    if args.risk_pct is not None:
        limits.risk_per_trade_pct = float(args.risk_pct)
    agent = TradingAgent(HeuristicDecider(), limits, chain, strike_step=50.0,
                         width_steps=4, otm_steps=0, setup_cfg=load_setup_cfg())

    bars = list(win["datetime"])
    if args.max_bars:
        bars = bars[:args.max_bars]

    print(f"REPLAY  NIFTY  {a} .. {b}   bars={len(bars):,}  "
          f"equity=Rs {args.equity:,.0f}  decider={agent.decider.name}  "
          f"cost_mult={args.cost_mult}  risk/trade={limits.risk_per_trade_pct:.1%}")
    res = run_replay(agent, builder, chain, bars, equity=args.equity,
                     lot_size_for=lot_lookup(), cost_mult=args.cost_mult,
                     max_trades_per_day=limits.max_trades_per_day)
    m = metrics(res, args.equity)

    print("\n-- SESSION ACCOUNTING (every bar lands in exactly one bucket) --")
    tot = sum(res.accounting.values())
    for k, n in sorted(res.accounting.items(), key=lambda kv: -kv[1]):
        print(f"  {k:34} {n:>7,}  {n/max(tot,1)*100:5.1f}%")
    print(f"  {'TOTAL':34} {tot:>7,}   offered {res.bars_offered:,}   "
          f"reconciles={res.reconciles()}")
    if not res.reconciles():
        print("  !! ACCOUNTING DOES NOT RECONCILE — a bar was lost; results not usable")

    print("\n-- AGENT RESULT --")
    if m.get("trades", 0) == 0:
        print("  no resolved trades")
    for k in ("trades", "unresolved", "win_rate", "net_rupees", "expectancy",
              "median_trade", "profit_factor", "max_dd_rupees",
              "max_dd_pct_of_equity", "longest_losing_streak", "best_trade",
              "worst_trade", "return_on_equity_pct", "tstat", "cost_pts_mean"):
        if k in m:
            print(f"  {k:24} {m[k]}")
    if m.get("exit_reasons"):
        print(f"  exit_reasons             {m['exit_reasons']}")
    if m.get("structures"):
        print(f"  structures               {m['structures']}")

    print("\n-- BASELINES (the agent is meaningless without these) --")
    n_tr = m.get("trades", 0)
    bl = [baseline_no_trade(),
          baseline_buy_and_hold(win, a, b),
          baseline_ema_cross(win, 5, 31),
          baseline_ema_cross(win, 9, 21),
          baseline_random_entry(win, n_tr, hold_bars=12, seed=1),
          baseline_random_entry(win, n_tr, hold_bars=12, seed=2)]
    for x in bl:
        print("  " + json.dumps(x))

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"window": {"start": str(a), "end": str(b)},
                       "equity": args.equity, "cost_mult": args.cost_mult,
                       "risk_per_trade_pct": limits.risk_per_trade_pct,
                       "decider": agent.decider.name, "metrics": m,
                       "baselines": bl,
                       "trades": [t.__dict__ for t in res.trades][:500]},
                      f, indent=2, default=str)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
