"""
Live paper-trading session for Bots 1, 2, 6 and 7.

REAL DHAN DATA -> SIGNAL -> RISK ENGINE -> PAPER ENTRY -> LIVE MARKING -> EXIT -> P&L

PAPER ONLY. The broker is local and simulated. Dhan is used exclusively for
read-only market data (`/marketfeed/quote`, `/marketfeed/ltp`, `/charts/*`). No
order, trade, position, super-order or forever-order endpoint is ever called.

Every cycle prints a heartbeat built from ACTUAL runtime state — each bot's last
evaluation, its reason, open positions and live P&L. A bot that has not been
evaluated inside the staleness timeout raises a warning rather than printing a
comfortable placeholder.
"""

import argparse
import os
import signal
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from src.config import Config
from src.data.dhan_client import get_dhan_client
from src.execution import bot_signals as BS
from src.execution.dhan_contract_resolver import DhanContractResolver
from src.execution.paper_engine import PaperBroker, PaperPosition, validate_quote
from src.risk.risk_engine import RiskEngine
from src.utils.logging import setup_logging

logger = setup_logging("scripts.run_paper_session")

NIFTY_SID, VIX_SID = 13, 21
MARKET_OPEN, MARKET_CLOSE = dtime(9, 15), dtime(15, 30)
HARD_FLAT = dtime(15, 20)          # square off before the close, on live quotes
EVAL_STALE_SEC = 180.0

BOTS = {
    "BOT1": "Strategy 1: Apex VRP Engine",
    "BOT2": "Strategy 2: Zen Curvature Overnight",
    "BOT6": "Strategy 6: Micro Momentum Sniper",
    "BOT7": "Strategy 7: Intraday Displacement",
}


class SessionState:
    """Everything observed this session, built only from live ticks."""

    def __init__(self) -> None:
        self.spots: List[float] = []
        self.high: Optional[float] = None
        self.low: Optional[float] = None
        self.last_spot: Optional[float] = None
        self.last_vix: Optional[float] = None
        self.last_quote_time: Optional[str] = None

    def update(self, spot: float, vix: Optional[float], qts: Optional[str]) -> None:
        self.spots.append(spot)
        self.last_spot = spot
        self.high = spot if self.high is None else max(self.high, spot)
        self.low = spot if self.low is None else min(self.low, spot)
        if vix and vix > 0:
            self.last_vix = vix
        if qts:
            self.last_quote_time = qts

    @property
    def twap(self) -> Optional[float]:
        """Running time-weighted mean of observed spot. Not a VWAP — see bot7 docs."""
        return sum(self.spots) / len(self.spots) if self.spots else None

    def seed_from_candles(self, client) -> int:
        """
        Seed the session path from today's real intraday candles.

        Without this the session high/low/TWAP would only cover the ticks observed
        since the process started, so a runner launched at 13:00 would compute a
        "session mean" over the last two hours and call it the day's. Bot 6 compares
        against the session extremes and Bot 7 against the session mean, so both
        would be judging the day on a fragment of it. The candles are the same
        authentic feed, simply back to 09:15.
        """
        today_str = date.today().strftime("%Y-%m-%d")
        try:
            df = client.fetch_intraday_candles(
                str(NIFTY_SID), "IDX_I", "INDEX", "5",
                f"{today_str} 09:15:00", f"{today_str} 15:30:00")
        except Exception as exc:                               # noqa: BLE001
            logger.warning(f"session seed unavailable: {type(exc).__name__}: {exc}")
            return 0
        if df is None or df.empty:
            logger.warning("session seed: no intraday candles returned")
            return 0
        for _, b in df.iterrows():
            self.spots.append(float(b["close"]))
            h, l = float(b["high"]), float(b["low"])
            self.high = h if self.high is None else max(self.high, h)
            self.low = l if self.low is None else min(self.low, l)
        self.last_spot = float(df.iloc[-1]["close"])
        logger.info(f"session seeded from {len(df)} authentic candles: "
                    f"high {self.high} low {self.low} twap {self.twap:.2f}")
        return len(df)


def load_history() -> pd.DataFrame:
    """Authentic completed daily bars + VIX. Nothing from today."""
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    df = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    df["volume"] = 0.0
    return df


def session_calendar(hist: pd.DataFrame, today: date) -> List[date]:
    """
    Past sessions from authentic history, plus forward weekdays.

    The forward part only has to answer "how many sessions until expiry". NSE
    publishes its holiday list a year ahead, so this is known at decision time; a
    holiday inside the window would shift the count by one and is accepted as a
    known limitation of not having the holiday file loaded here.
    """
    past = sorted({d.date() for d in pd.to_datetime(hist["datetime"])})
    fwd, d = [], today
    for _ in range(40):
        if d.weekday() < 5:
            fwd.append(d)
        d += timedelta(days=1)
    return sorted(set(past) | set(fwd))


def next_weekly_expiry(underlying: str = "NIFTY", today: Optional[date] = None) -> Optional[date]:
    """
    The next listed weekly expiry, read from the Scrip Master.

    Taken from the exchange's own contract list rather than assuming a weekday —
    NIFTY weeklies moved from Thursday to Tuesday, and a hardcoded weekday would be
    silently wrong.
    """
    from src.execution.dhan_scrip_master import DhanScripMaster
    df = DhanScripMaster.get_master_df()
    if df is None or df.empty:
        return None
    today = today or date.today()
    ex = pd.to_datetime(df[df["UNDERLYING"] == underlying]["EXPIRY_DATE_CLEAN"],
                        errors="coerce").dt.date.dropna()
    fwd = sorted({e for e in ex if e >= today})
    return fwd[0] if fwd else None


def fetch_index(client) -> Dict[str, Any]:
    """Live NIFTY and India VIX. Read-only."""
    q = client.fetch_marketfeed_quote([NIFTY_SID, VIX_SID], exchange_segment="IDX_I")
    n, v = q.get(str(NIFTY_SID), {}), q.get(str(VIX_SID), {})
    return {
        "spot": float(n.get("ltp") or 0) or None,
        "vix": float(v.get("ltp") or 0) or None,
        "quote_timestamp": n.get("market_timestamp") or n.get("received_at"),
    }


def leg_quotes(client, security_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Live two-sided quotes for the given option contracts. Read-only.

    The batch feed names its fields differently from the contract resolver, so the
    freshness field is normalised here rather than leaving the quote gate to guess.

    WHICH TIMESTAMP MEANS "FRESH". `timestamp` is when this depth snapshot was
    received; `last_trade_time` is when the contract last TRADED. For a bid/ask
    those are different questions — a far-OTM option can have a live, honest
    two-sided market and no trade for twenty minutes. Freshness of a QUOTE is
    therefore measured against the snapshot, and the last trade time is carried
    alongside as separate information rather than used as a staleness proxy.
    """
    ids = [s for s in {str(x) for x in security_ids} if s.isdigit()]
    if not ids:
        return {}
    try:
        raw = client.fetch_marketfeed_quote(ids, exchange_segment="NSE_FNO")
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"quote fetch failed: {type(exc).__name__}: {exc}")
        return {}
    for q in raw.values():
        if not q.get("quote_timestamp"):
            ts = q.get("timestamp")
            if ts:
                try:
                    q["quote_timestamp"] = datetime.fromisoformat(str(ts)).strftime(
                        "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    q["quote_timestamp"] = None
    return raw


def resolve_legs(decision, spot: float, vix: float, expiry: Optional[date]) -> Optional[List[Dict]]:
    """
    Turns the strategy's LegSpecs into real contracts with live quotes.

    Returns None if ANY leg cannot be resolved or quoted: a structure is one
    decision, and filling it partially would leave risk the strategy never chose.
    """
    atm = round(spot / BS.STRIKE_STEP) * BS.STRIKE_STEP
    out = []
    for spec in decision.legs:
        strike = spec.strike if spec.strike is not None else atm + spec.strike_offset * BS.STRIKE_STEP
        c = DhanContractResolver.resolve_option_contract(
            spot, vix, spec.option_type, strike=float(strike), target_expiry=expiry)
        if not c:
            logger.warning(f"leg unresolved: {spec.role} {spec.option_type} @ {strike}")
            return None
        out.append({
            "role": spec.role, "side": spec.side, "option_type": spec.option_type,
            "security_id": c.get("security_id"), "trading_symbol": c.get("trading_symbol"),
            "custom_symbol": c.get("custom_symbol"), "strike": c.get("strike", strike),
            "expiry": c.get("expiry") or (str(expiry) if expiry else ""),
            "lot_size": c.get("lot_size"), "bid": c.get("bid"), "ask": c.get("ask"),
            "ltp": c.get("ltp"), "quote_timestamp": c.get("quote_timestamp"),
        })
    return out


def risk_gate(risk: RiskEngine, broker: PaperBroker, bot: str,
              contracts: List[Dict]) -> tuple:
    """
    EVERY leg passes the authoritative risk engine. One rejection rejects the trade.

    Exposure is the premium actually at risk: a bought leg risks what it costs, a
    sold leg's risk is bounded by its paired wing, which the structure guarantees.
    """
    open_now = len(broker.open_positions["PAPER"])
    if open_now >= risk.max_simultaneous_positions:
        return False, f"MAX_POSITIONS {open_now}/{risk.max_simultaneous_positions}"
    for c in contracts:
        px = float(c["ask"]) if c["side"] == "BUY" else float(c["bid"])
        d = risk.evaluate_trade(symbol=str(c["security_id"]),
                                direction=1 if c["side"] == "BUY" else -1,
                                entry_price=px, atr=0.0, confidence=0.6,
                                sector="INDEX_OPTIONS")
        if not d.approved:
            return False, f"RISK_REJECTED[{c['role']}]: {d.rejection_reason}"
    return True, "APPROVED"


def heartbeat(cycle: int, sess: SessionState, states: Dict[str, Dict],
              broker: PaperBroker, now: datetime) -> None:
    """Printed from real runtime state only. Never a placeholder."""
    paper = broker.summary("PAPER")
    print(f"\n[{now.strftime('%H:%M:%S')}] CYCLE {cycle}")
    stamp = sess.last_quote_time or now.strftime("%H:%M:%S") + " (local fetch)"
    print(f"DHAN: {'LIVE ' + str(stamp) if sess.last_spot else 'NO DATA'}"
          f"   NIFTY {sess.last_spot}   VIX {sess.last_vix}   "
          f"sessHi {sess.high} sessLo {sess.low} twap "
          f"{sess.twap:.1f}" if sess.twap else "")
    for key in BOTS:
        st = states[key]
        age = (now - st["last_eval"]).total_seconds() if st["last_eval"] else 1e9
        flag = "  ** STALE **" if age > EVAL_STALE_SEC else ""
        pnl = f"  uPnL Rs {st['open_pnl']:,.2f}" if st["status"] == "IN_POSITION" else ""
        print(f"{key}: {st['status']:<13}{pnl}  | {st['reason'][:78]}{flag}")
        if flag:
            logger.warning(f"{key} not evaluated for {age:.0f}s")
    print(f"PAPER_POSITIONS: {paper['open_positions']}   CLOSED: {paper['closed_positions']}   "
          f"REALIZED: Rs {paper['realized_pnl']:,.2f}   UNREALIZED: Rs {paper['unrealized_pnl']:,.2f}"
          f"   COSTS: Rs {paper['total_costs']:,.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=20.0, help="seconds between cycles")
    ap.add_argument("--capital", type=float, default=100000.0)
    ap.add_argument("--max-cycles", type=int, default=0, help="0 = run to market close")
    ap.add_argument("--allow-closed-market", action="store_true")
    args = ap.parse_args()

    Config.assert_no_live_trading()
    logger.info(f"SAFETY: LIVE_TRADING_ENABLED={Config.LIVE_TRADING_ENABLED} — paper only")

    client = get_dhan_client()
    broker = PaperBroker()
    risk = RiskEngine(initial_capital=args.capital, max_simultaneous_positions=4,
                      max_position_pct=0.25)
    hist = load_history()
    today = date.today()
    calendar = session_calendar(hist, today)
    expiry = next_weekly_expiry("NIFTY", today)
    logger.info(f"history {len(hist)} sessions | next weekly expiry {expiry} | "
                f"sessions to expiry {BS.sessions_until(expiry, today, calendar) if expiry else '?'}")

    sess = SessionState()
    seeded = sess.seed_from_candles(client)
    if not seeded:
        logger.warning("session path NOT seeded — Bot 6/7 session references will be "
                       "partial until enough ticks accumulate")
    states = {k: {"status": "INIT", "reason": "not yet evaluated",
                  "last_eval": None, "open_pnl": 0.0, "position": None} for k in BOTS}

    stop = {"flag": False}

    def _sigint(_s, _f):
        stop["flag"] = True
        logger.info("interrupt received — finishing cycle then squaring off")
    signal.signal(signal.SIGINT, _sigint)

    cycle = 0
    try:
        while not stop["flag"]:
            cycle += 1
            now = datetime.now()
            t = now.time()
            if not args.allow_closed_market and not (MARKET_OPEN <= t <= MARKET_CLOSE):
                logger.info(f"market closed ({t}) — stopping loop")
                break
            if args.max_cycles and cycle > args.max_cycles:
                break

            # ── 1. live index data ──
            try:
                idx = fetch_index(client)
            except Exception as exc:                            # noqa: BLE001
                broker.record_error("SESSION", f"index fetch: {type(exc).__name__}: {exc}")
                time.sleep(args.interval)
                continue
            if not idx["spot"] or not idx["vix"]:
                broker.record_error("SESSION", "index quote incomplete — cycle skipped")
                time.sleep(args.interval)
                continue
            sess.update(idx["spot"], idx["vix"], idx["quote_timestamp"])
            spot, vix = sess.last_spot, sess.last_vix

            # ── 2. mark and exit open positions on live quotes ──
            open_positions = list(broker.open_positions["PAPER"])
            if open_positions:
                sids = [l.security_id for p in open_positions for l in p.legs]
                q = leg_quotes(client, sids)
                for pos in open_positions:
                    marked = broker.mark_position(pos, q, spot)
                    if marked is None:
                        broker.record_error(pos.bot, f"UNMARKABLE {pos.position_id} — no usable quote")
                        continue
                    reason = broker.exit_signal(pos, t.strftime("%H:%M"))
                    if t >= HARD_FLAT and reason is None:
                        reason = "SESSION_FLAT"
                    if reason:
                        broker.close_position(pos, q, reason, spot)

            # ── 3. evaluate every bot, every cycle ──
            for key, name in BOTS.items():
                st = states[key]
                live = [p for p in broker.open_positions["PAPER"] if p.bot == key]
                st["position"] = live[0] if live else None
                st["open_pnl"] = live[0].unrealized_pnl if live else 0.0
                try:
                    if live:
                        st["status"] = "IN_POSITION"
                        st["reason"] = (f"{live[0].legs[0].custom_symbol} "
                                        f"MFE {live[0].mfe:,.0f} MAE {live[0].mae:,.0f}")
                        st["last_eval"] = now
                        continue

                    if key == "BOT1":
                        dec = BS.bot1_apex_vrp(spot, vix, hist, today, expiry, calendar, t)
                    elif key == "BOT2":
                        dec = BS.bot2_zen_curvature(spot, vix, hist, today, expiry, calendar, t)
                    elif key == "BOT6":
                        dec = BS.bot6_micro_momentum(spot, vix, hist, today, t,
                                                     sess.high, sess.low)
                    else:
                        dec = BS.bot7_displacement(spot, vix, hist, today, t, sess.twap,
                                                   sess.high, sess.low)
                    st["last_eval"] = now
                    st["status"] = "WAIT" if dec.action == "WAIT" else "SIGNAL"
                    st["reason"] = dec.reason

                    if dec.action != "ENTER":
                        continue

                    contracts = resolve_legs(dec, spot, vix, expiry)
                    if not contracts:
                        st["status"] = "NO_EXECUTION"
                        st["reason"] = "CONTRACT_UNRESOLVED"
                        broker.record_rejection(key, "CONTRACT_UNRESOLVED", {"signal": dec.reason})
                        continue
                    bad = [f"{c['role']}:{validate_quote(c['bid'], c['ask'], c['quote_timestamp'], c['side'])[1]}"
                           for c in contracts
                           if not validate_quote(c["bid"], c["ask"], c["quote_timestamp"], c["side"])[0]]
                    if bad:
                        st["status"] = "NO_EXECUTION"
                        st["reason"] = f"QUOTE_REJECTED {bad[0]}"
                        broker.record_rejection(key, "QUOTE_REJECTED", {"detail": bad})
                        continue
                    ok, why = risk_gate(risk, broker, key, contracts)
                    if not ok:
                        st["status"] = "RISK_BLOCKED"
                        st["reason"] = why
                        broker.record_rejection(key, why, {"signal": dec.reason})
                        continue

                    pos = broker.open_position(
                        bot=key, strategy=name, underlying="NIFTY", spot=spot,
                        contracts=contracts, ledger="PAPER",
                        target_pnl=dec.target_pnl, stop_pnl=dec.stop_pnl,
                        trail_trigger=dec.trail_trigger, trail_giveback=dec.trail_giveback,
                        flat_by=dec.flat_by, meta={**dec.meta, "signal_reason": dec.reason},
                    )
                    if pos:
                        st["status"] = "IN_POSITION"
                        st["reason"] = f"ENTERED {dec.reason[:60]}"
                        st["position"] = pos
                    else:
                        st["status"] = "NO_EXECUTION"
                        st["reason"] = "BROKER_REFUSED_FILL"
                except Exception as exc:                        # noqa: BLE001
                    st["status"] = "ERROR"
                    st["reason"] = f"{type(exc).__name__}: {exc}"
                    st["last_eval"] = now
                    broker.record_error(key, f"{type(exc).__name__}: {exc}")

            heartbeat(cycle, sess, states, broker, now)
            broker.persist()
            time.sleep(args.interval)

    finally:
        # ── square off on live quotes; never on an invented price ──
        remaining = list(broker.open_positions["PAPER"])
        if remaining:
            logger.info(f"squaring off {len(remaining)} open position(s) on live quotes")
            q = leg_quotes(client, [l.security_id for p in remaining for l in p.legs])
            for pos in remaining:
                broker.mark_position(pos, q, sess.last_spot)
                broker.close_position(pos, q, "SESSION_END", sess.last_spot)
        path = broker.persist()
        s = broker.summary("PAPER")
        print("\n" + "=" * 70)
        print("PAPER SESSION SUMMARY")
        print("=" * 70)
        for k, v in s.items():
            print(f"  {k:20s} {v}")
        print(f"  rejections           {len(broker.rejections)}")
        print(f"  execution errors     {len(broker.errors)}")
        print(f"  ledger               {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
