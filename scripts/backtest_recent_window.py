"""
STRICT RECENT-WINDOW BACKTEST — measurement only.

Replays the EXACT frozen strategy functions from `src/execution/bot_signals.py` and
`src/execution/bot8_price_action.py` over a recent window. No strategy logic is
imported in modified form, no parameter is passed that differs from the live
runtime's defaults, and no session or trade is filtered out for its outcome.

WHAT "EXACT" MEANS HERE
  * Bots 1, 2, 6, 7 call `BS.bot1_apex_vrp`, `BS.bot2_zen_curvature`,
    `BS.bot6_micro_momentum`, `BS.bot7_displacement` with the same arguments
    `scripts/run_paper_session.py` passes them.
  * Bot 8 calls `BS.bot8_price_action`, which wraps the frozen state machine.
  * Exits run through `PaperBroker.exit_signal` and `close_position`, the same
    code the live session uses, so target/stop/trail/EOD behave identically.
  * Costs come from `IndianCostModel` via the broker, per leg, entry and exit.

EXECUTION ASSUMPTION — STATED, NOT HIDDEN
There is NO historical bid/ask anywhere in this repository. The documented basis
is `TRADED_PRICE_NO_BIDASK`: a fill is modelled at the traded price of the bar,
with the live engine's slippage (0.50 points) charged against the trader on both
sides. Here that is expressed by quoting bid = ask = the bar's traded price and
letting the broker's own `fill_price` apply slippage, so a BUY pays price+0.50 and
a SELL receives price−0.50. Real fills would be worse by at least the half-spread.

The quote-freshness gate is a LIVE safety control against a stale feed. In replay
the historical bar IS the authoritative price for its own timestamp, so quotes are
stamped at call time to let that gate pass. Nothing else about the gate is relaxed:
missing, zero or inverted prices are still refused and counted.

Intraday bots are driven bar by bar across the session with only the path up to
that bar visible. Daily bots see only sessions strictly before the decision day.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.execution import bot_signals as BS
from src.execution.cost_model import IndianCostModel
from src.execution.multileg_paper_broker import DEFAULT_SLIPPAGE, PaperBroker
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m

LOT = 65
FLAT_TIME = dtime(15, 10)


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def quote(price: float) -> Dict[str, Any]:
    """
    A replay quote. bid = ask = the bar's traded price; slippage is applied by the
    broker exactly as it is live. See the module docstring for why.
    """
    return {"bid": float(price), "ask": float(price), "quote_timestamp": now_stamp()}


def load_index() -> pd.DataFrame:
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    d["volume"] = 0.0
    return d


def session_path(grid: Dict[str, pd.DataFrame], sess: date) -> Optional[pd.DataFrame]:
    g = grid["ce"]
    day = g[g["datetime"].dt.date == sess]
    if day.empty:
        return None
    return (day.groupby("datetime")["spot"].first().sort_index().reset_index())


def day_slice(grid: Dict[str, pd.DataFrame], side: str, sess: date) -> pd.DataFrame:
    g = grid[side]
    return g[g["datetime"].dt.date == sess]


def atm_contract(dg: pd.DataFrame, ts, spot: float) -> Optional[tuple]:
    """Fix the ATM strike at this instant and return (strike, traded price)."""
    at = dg[dg["datetime"] == ts]
    if at.empty:
        return None
    row = at.iloc[(at["strike"] - spot).abs().argsort()].iloc[0]
    px = float(row["close"])
    return (float(row["strike"]), px) if px > 0 else None


# ───────────────────────── INTRADAY BOTS (6, 7, 8) ─────────────────────────

def run_intraday_bot(bot: str, sessions: List[date], hist: pd.DataFrame,
                     grid: Dict[str, pd.DataFrame], broker: PaperBroker,
                     skips: Dict[str, int]) -> List[Dict[str, Any]]:
    """
    Walk each session bar by bar, passing the frozen signal only what existed then.

    One position at a time per bot, matching the live runner, which evaluates a bot
    for entry only when it holds nothing.
    """
    trades: List[Dict[str, Any]] = []
    hist_by_day = {d: i for i, d in enumerate(pd.to_datetime(hist["datetime"]).dt.date)}

    for sess in sessions:
        if sess not in hist_by_day:
            skips[f"{bot}:NO_INDEX_SESSION"] += 1
            continue
        sp = session_path(grid, sess)
        if sp is None or len(sp) < 12:
            skips[f"{bot}:NO_INTRADAY_PATH"] += 1
            continue

        prev_row = hist.iloc[hist_by_day[sess] - 1] if hist_by_day[sess] > 0 else None
        prev_high = float(prev_row["high"]) if prev_row is not None else None
        prev_low = float(prev_row["low"]) if prev_row is not None else None
        vix_today = float(hist.iloc[hist_by_day[sess]]["vix"])

        path: List[float] = []
        s_hi = s_lo = None
        open_pos = None
        entry_ctx: Dict[str, Any] = {}

        for i in range(len(sp)):
            ts = sp.iloc[i]["datetime"]
            spot = float(sp.iloc[i]["spot"])
            t = ts.time()
            path.append(spot)
            s_hi = spot if s_hi is None else max(s_hi, spot)
            s_lo = spot if s_lo is None else min(s_lo, spot)
            twap = sum(path) / len(path)

            # ── mark and exit an open position, exactly as the live loop does ──
            if open_pos is not None:
                leg = open_pos.legs[0]
                side = "ce" if leg.option_type == "CE" else "pe"
                dg = day_slice(grid, side, sess)
                bar = dg[(dg["strike"] == leg.strike) & (dg["datetime"] == ts)]
                if bar.empty:
                    skips[f"{bot}:CONTRACT_UNQUOTED_MIDTRADE"] += 1
                else:
                    px = float(bar.iloc[0]["close"])
                    q = {str(leg.security_id): quote(px)}
                    broker.mark_position(open_pos, q, spot)
                    reason = broker.exit_signal(open_pos, t.strftime("%H:%M"))
                    if reason is None and t >= FLAT_TIME:
                        reason = "SESSION_FLAT"
                    if reason:
                        broker.close_position(open_pos, q, reason, spot)
                        trades.append({
                            "bot": bot, "date": str(sess),
                            "entry_time": entry_ctx["entry_time"], "exit_time": str(t),
                            "option_type": leg.option_type, "strike": leg.strike,
                            "entry_fill": leg.entry_fill, "exit_fill": leg.exit_fill,
                            "qty": leg.qty, "gross": round(leg.realized() or 0.0, 2),
                            "costs": round(open_pos.total_costs, 2),
                            "slippage_cost": round(2 * DEFAULT_SLIPPAGE * leg.qty, 2),
                            "net": open_pos.realized_pnl, "exit_reason": reason,
                            "mae": open_pos.mae, "mfe": open_pos.mfe,
                            "reason": entry_ctx["signal"],
                        })
                        open_pos = None
                if open_pos is not None:
                    continue

            # ── evaluate for entry only when flat, exactly as the live loop does ──
            if bot == "BOT6":
                dec = BS.bot6_micro_momentum(spot, vix_today, hist, sess, t, s_hi, s_lo)
            elif bot == "BOT7":
                dec = BS.bot7_displacement(spot, vix_today, hist, sess, t, twap, s_hi, s_lo)
            else:
                dec = BS.bot8_price_action(spot, vix_today, hist, sess, t, path,
                                           prev_high, prev_low)
            if dec.action != "ENTER":
                continue

            spec = dec.legs[0]
            side = "ce" if spec.option_type == "CE" else "pe"
            dg = day_slice(grid, side, sess)
            got = atm_contract(dg, ts, spot)
            if got is None:
                skips[f"{bot}:NO_ATM_CONTRACT_AT_ENTRY"] += 1
                continue
            strike, px = got
            fwd = dg[(dg["strike"] == strike) & (dg["datetime"] > ts)]
            if fwd.empty:
                skips[f"{bot}:CONTRACT_NOT_QUOTED_FORWARD"] += 1
                continue

            pos = broker.open_position(
                bot=bot, strategy=bot, underlying="NIFTY", spot=spot,
                contracts=[{
                    "role": "leg", "side": "BUY", "option_type": spec.option_type,
                    "security_id": f"{sess}-{strike:.0f}-{spec.option_type}",
                    "trading_symbol": f"NIFTY-{strike:.0f}-{spec.option_type}",
                    "custom_symbol": f"NIFTY {strike:.0f} {spec.option_type}",
                    "strike": strike, "expiry": "", "lot_size": LOT,
                    **quote(px),
                }],
                ledger="PAPER", target_pnl=dec.target_pnl, stop_pnl=dec.stop_pnl,
                trail_trigger=dec.trail_trigger, trail_giveback=dec.trail_giveback,
                flat_by=dec.flat_by, meta=dec.meta,
            )
            if pos is None:
                skips[f"{bot}:BROKER_REFUSED_FILL"] += 1
                continue
            open_pos = pos
            entry_ctx = {"entry_time": str(t), "signal": dec.reason[:90]}

        # force-close anything still open at the session's last bar
        if open_pos is not None:
            leg = open_pos.legs[0]
            side = "ce" if leg.option_type == "CE" else "pe"
            dg = day_slice(grid, side, sess)
            tail = dg[dg["strike"] == leg.strike].sort_values("datetime")
            if tail.empty:
                skips[f"{bot}:UNRESOLVED_AT_SESSION_END"] += 1
            else:
                px = float(tail.iloc[-1]["close"])
                q = {str(leg.security_id): quote(px)}
                broker.mark_position(open_pos, q, float(sp.iloc[-1]["spot"]))
                broker.close_position(open_pos, q, "SESSION_END", float(sp.iloc[-1]["spot"]))
                trades.append({
                    "bot": bot, "date": str(sess), "entry_time": entry_ctx["entry_time"],
                    "exit_time": str(tail.iloc[-1]["datetime"].time()),
                    "option_type": leg.option_type, "strike": leg.strike,
                    "entry_fill": leg.entry_fill, "exit_fill": leg.exit_fill,
                    "qty": leg.qty, "gross": round(leg.realized() or 0.0, 2),
                    "costs": round(open_pos.total_costs, 2),
                    "slippage_cost": round(2 * DEFAULT_SLIPPAGE * leg.qty, 2),
                    "net": open_pos.realized_pnl, "exit_reason": "SESSION_END",
                    "mae": open_pos.mae, "mfe": open_pos.mfe,
                    "reason": entry_ctx["signal"],
                })
    return trades


# ───────────────────────── DAILY OPTION BOTS (1, 2) ─────────────────────────

def run_daily_bot(bot: str, sessions: List[date], hist: pd.DataFrame,
                  store: pd.DataFrame, chains: ChainIndex, expiries: List[date],
                  calendar: List[date], skips: Dict[str, int]) -> List[Dict[str, Any]]:
    """
    Bots 1 and 2: decide at the session close, price every leg from that session's
    bhavcopy, hold to expiry, settle at intrinsic against the official settlement.
    """
    trades: List[Dict[str, Any]] = []
    hist_by_day = {d: i for i, d in enumerate(pd.to_datetime(hist["datetime"]).dt.date)}
    index_close = {d: float(c) for d, c in
                   zip(pd.to_datetime(hist["datetime"]).dt.date, hist["close"])}

    for sess in sessions:
        if sess not in hist_by_day:
            skips[f"{bot}:NO_INDEX_SESSION"] += 1
            continue
        row = hist.iloc[hist_by_day[sess]]
        spot, vix = float(row["close"]), float(row["vix"])
        nxt = [e for e in expiries if e > sess]
        expiry = nxt[0] if nxt else None

        # 15:00 matches the live runner's close-window gate (entry requires >= 14:45)
        if bot == "BOT1":
            dec = BS.bot1_apex_vrp(spot, vix, hist, sess, expiry, calendar, dtime(15, 0))
        else:
            dec = BS.bot2_zen_curvature(spot, vix, hist, sess, expiry, calendar, dtime(15, 0))
        if dec.action != "ENTER":
            continue

        chain = chains.chain(sess, expiry)
        if chain.empty:
            skips[f"{bot}:NO_CHAIN_FOR_EXPIRY"] += 1
            continue
        settle = chains.settlement(expiry, index_close)
        if settle is None:
            skips[f"{bot}:NO_SETTLEMENT_PRICE"] += 1
            continue

        atm = round(spot / BS.STRIKE_STEP) * BS.STRIKE_STEP
        legs, bad = [], []
        for spec in dec.legs:
            k = atm + spec.strike_offset * BS.STRIKE_STEP
            r = chain[(chain["StrkPric"] == k) & (chain["OptnTp"] == spec.option_type)]
            if r.empty:
                bad.append(f"{spec.role}@{k:.0f}{spec.option_type}:ABSENT")
                continue
            rr = r.iloc[0]
            if int(rr["TtlTradgVol"]) <= 0 or float(rr["ClsPric"]) <= 0:
                bad.append(f"{spec.role}@{k:.0f}{spec.option_type}:NO_TRADE")
                continue
            lot = int(rr["NewBrdLotQty"]) if "NewBrdLotQty" in rr.index and pd.notna(
                rr["NewBrdLotQty"]) else 0
            if lot <= 0:
                bad.append(f"{spec.role}:NO_LOT_SIZE")
                continue
            legs.append((spec, float(k), float(rr["ClsPric"]), lot,
                         str(int(rr["FinInstrmId"])) if "FinInstrmId" in rr.index else "",
                         str(rr.get("FinInstrmNm", ""))))
        if bad or len(legs) != len(dec.legs):
            skips[f"{bot}:LEG_UNPRICEABLE"] += 1
            continue

        gross = costs = credit = 0.0
        detail = []
        for spec, k, px, lot, sid, nm in legs:
            fill = round(px + DEFAULT_SLIPPAGE, 2) if spec.side == "BUY" else round(
                max(0.05, px - DEFAULT_SLIPPAGE), 2)
            intr = (max(0.0, settle - k) if spec.option_type == "CE"
                    else max(0.0, k - settle))
            sign = 1.0 if spec.side == "BUY" else -1.0
            gross += sign * (intr - fill) * lot
            credit += (-sign) * fill
            from src.research.bot1_condor_real import condor_leg_costs
            costs += condor_leg_costs(spec.side, fill, intr, lot)
            detail.append({"role": spec.role, "side": spec.side, "strike": k,
                           "type": spec.option_type, "entry": fill, "exit": round(intr, 2),
                           "qty": lot, "security_id": sid, "contract": nm})

        trades.append({
            "bot": bot, "date": str(sess), "expiry": str(expiry),
            "entry_time": "15:00", "exit_time": "EXPIRY_SETTLEMENT",
            "spot_entry": spot, "spot_settle": settle,
            "credit_points": round(credit, 2), "gross": round(gross, 2),
            "costs": round(costs, 2),
            "slippage_cost": round(sum(DEFAULT_SLIPPAGE * l[3] for l in legs), 2),
            "net": round(gross - costs, 2), "exit_reason": "EXPIRY_SETTLEMENT",
            "mae": None, "mfe": None, "reason": dec.reason[:90], "legs": detail,
        })
    return trades


# ───────────────────────────── STATISTICS ─────────────────────────────

def stats(bot: str, trades: List[Dict], sessions: List[date]) -> Dict[str, Any]:
    n_days = len(sessions)
    if not trades:
        return {"bot": bot, "trades": 0, "wins": 0, "losses": 0, "win_rate": None,
                "gross": 0.0, "costs": 0.0, "slippage": 0.0, "net": 0.0,
                "max_dd": 0.0, "avg_win": None, "avg_loss": None, "expectancy": None,
                "trading_days": n_days, "days_with_trade": 0, "avg_daily_net": 0.0,
                "best_day": None, "worst_day": None}
    df = pd.DataFrame(trades)
    net = df["net"].astype(float)
    wins, losses = net[net > 0], net[net <= 0]
    eq = net.cumsum()
    dd = float((eq - eq.cummax()).min())
    daily = df.groupby("date")["net"].sum()
    return {
        "bot": bot, "trades": int(len(df)),
        "wins": int((net > 0).sum()), "losses": int((net <= 0).sum()),
        "win_rate": round(float((net > 0).mean() * 100), 1),
        "gross": round(float(df["gross"].sum()), 2),
        "costs": round(float(df["costs"].sum()), 2),
        "slippage": round(float(df["slippage_cost"].sum()), 2),
        "net": round(float(net.sum()), 2),
        "max_dd": round(abs(dd), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else None,
        "expectancy": round(float(net.mean()), 2),
        "trading_days": n_days, "days_with_trade": int(daily.shape[0]),
        "avg_daily_net": round(float(net.sum() / n_days), 2),
        "best_day": f"{daily.idxmax()} {daily.max():+,.0f}",
        "worst_day": f"{daily.idxmin()} {daily.min():+,.0f}",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-09-01")
    ap.add_argument("--end", default="2026-09-18")
    ap.add_argument("--out", default="reports/backtest_recent_window.json")
    args = ap.parse_args()
    lo, hi = pd.Timestamp(args.start).date(), pd.Timestamp(args.end).date()

    hist = load_index()
    grid = load_option_grid_5m()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)

    idx_days = sorted({d for d in pd.to_datetime(hist["datetime"]).dt.date if lo <= d <= hi})
    grid_days = sorted({d for d in available_option_days(grid) if lo <= d <= hi})
    bhav_days = sorted({d for d in store["TradDt"].unique() if lo <= d <= hi})
    calendar = sorted({d for d in pd.to_datetime(hist["datetime"]).dt.date})

    print("=" * 74)
    print(f"STRICT RECENT-WINDOW BACKTEST  {lo} .. {hi}")
    print("=" * 74)
    print(f"index sessions    : {len(idx_days)}  {idx_days[0]} .. {idx_days[-1]}")
    print(f"intraday grid     : {len(grid_days)} sessions")
    print(f"bhavcopy chains   : {len(bhav_days)} sessions")
    missing_grid = [str(d) for d in idx_days if d not in grid_days]
    missing_bhav = [str(d) for d in idx_days if d not in bhav_days]
    print(f"sessions WITHOUT intraday grid : {missing_grid or 'none'}")
    print(f"sessions WITHOUT option chain  : {missing_bhav or 'none'}")
    print(f"execution basis   : TRADED_PRICE_NO_BIDASK, slippage {DEFAULT_SLIPPAGE} pts/side")

    skips: Dict[str, int] = defaultdict(int)
    broker = PaperBroker(session_dir=str(Path(
        os.environ.get("TEMP", "/tmp")) / "bt_recent"))
    all_trades: Dict[str, List[Dict]] = {}

    for bot in ("BOT6", "BOT7", "BOT8"):
        all_trades[bot] = run_intraday_bot(bot, grid_days, hist, grid, broker, skips)
    for bot in ("BOT1", "BOT2"):
        all_trades[bot] = run_daily_bot(bot, bhav_days, hist, store, chains,
                                        expiries, calendar, skips)

    rows = [stats(b, all_trades[b],
                  grid_days if b in ("BOT6", "BOT7", "BOT8") else bhav_days)
            for b in ("BOT1", "BOT2", "BOT6", "BOT7", "BOT8")]

    print("\n" + "=" * 74)
    print("COMPARISON")
    print("=" * 74)
    print(f"{'Bot':6} {'Trades':>7} {'WinRate':>8} {'Gross':>11} {'Costs':>10} "
          f"{'Net':>11} {'MaxDD':>10} {'AvgDaily':>10}")
    for r in rows:
        wr = f"{r['win_rate']:.1f}%" if r["win_rate"] is not None else "n/a"
        print(f"{r['bot']:6} {r['trades']:>7} {wr:>8} {r['gross']:>11,.0f} "
              f"{r['costs']:>10,.0f} {r['net']:>11,.0f} {r['max_dd']:>10,.0f} "
              f"{r['avg_daily_net']:>10,.0f}")

    print("\nPER-BOT DETAIL")
    for r in rows:
        print(f"\n  {r['bot']}")
        for k in ("trades", "wins", "losses", "win_rate", "gross", "costs", "slippage",
                  "net", "max_dd", "avg_win", "avg_loss", "expectancy", "trading_days",
                  "days_with_trade", "avg_daily_net", "best_day", "worst_day"):
            print(f"    {k:16s} {r[k]}")

    print("\nSKIPPED SESSIONS / TRADES (reason -> count)")
    if skips:
        for k, v in sorted(skips.items(), key=lambda x: -x[1]):
            print(f"    {k:45s} {v}")
    else:
        print("    none")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "window": [str(lo), str(hi)],
        "coverage": {"index": len(idx_days), "grid": len(grid_days),
                     "bhavcopy": len(bhav_days),
                     "missing_grid": missing_grid, "missing_chain": missing_bhav},
        "execution_basis": f"TRADED_PRICE_NO_BIDASK slippage={DEFAULT_SLIPPAGE}",
        "summary": rows, "skips": dict(skips),
        "trades": all_trades,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
