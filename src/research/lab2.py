"""
LAB2 — level-based intraday strategy engine for the 6-month money study.

WHY A SECOND ENGINE. `strategy_lab` expresses a trade as ATR multiples of spot
movement. That cannot express "stop at the opening-range low, target 1.5x the
distance to it", which is how essentially every price-action strategy is actually
specified, and it cannot express a reward/risk ratio at all. LAB2 takes SPOT
LEVELS from the signal, so R:R is a property of the setup rather than a constant.

CAUSALITY. At decision bar i a signal sees session bars 0..i and daily rows
strictly before the session. Nothing else. Forward bars resolve only an exit the
rules already committed to. Exits resolve at BAR CLOSE: the dataset carries one
spot per timestamp, so there is no intrabar path to peek at and no ambiguity about
whether a stop or a target was touched first. A level crossed mid-bar is filled at
that bar's close, which is where it actually would have filled, adverse gap
included.

EXECUTION. No historical bid/ask exists. Each side pays
    half-spread = max(1 tick, SPREAD_PCT x premium)
    slippage    = SLIP_TICKS x tick
on top of statutory charges (IndianCostModel). Observed live NIFTY ATM spread on
2026-09-18 was ~0.22% of mid, so 0.30% per side is ~1.4x that, and slippage is
charged on top. `cost_mult` scales the whole package for sensitivity testing.

VWAP. The dataset has no index volume. Two anchors are exposed and both are named
for what they are: `twap` (unweighted session mean) and `vwap_opt` (session spot
weighted by total CE+PE option volume traded at each bar — authentic traded
activity, but option volume, not index volume). No candidate is allowed to call
either one "VWAP" without that qualification appearing in its notes.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import date, time as dtime
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel

TICK = 0.05
SPREAD_PCT = 0.0030
SLIP_TICKS = 2
LOT = 65
STRIKE_STEP = 50.0

# ── 6-MONTH HOLDOUT SPLITS. Fixed here, before any candidate is written. ──
DEV_END = pd.Timestamp("2024-09-17").date()
VAL_END = pd.Timestamp("2026-03-17").date()
HOLDOUT_START = pd.Timestamp("2026-03-18").date()
HOLDOUT_END = pd.Timestamp("2026-09-18").date()


def buy_fill(px: float, m: float = 1.0) -> float:
    return round(px + max(TICK, px * SPREAD_PCT) * m + SLIP_TICKS * TICK * m, 2)


def sell_fill(px: float, m: float = 1.0) -> float:
    return round(max(TICK, px - max(TICK, px * SPREAD_PCT) * m - SLIP_TICKS * TICK * m), 2)


@dataclass
class Setup:
    """What a signal commits to at the decision bar. Levels are SPOT prices."""
    direction: int                  # +1 buy CE, -1 buy PE
    stop: float                     # spot level that invalidates the idea
    target: float                   # spot level that completes it
    tag: str = ""
    strike_offset: int = 0          # 0 ATM, +1 one step OTM, -1 one step ITM
    max_hold_bars: Optional[int] = None


@dataclass
class Spec2:
    name: str
    family: str
    signal: Callable                # (Ctx2) -> Optional[Setup]
    entry_from: dtime = dtime(9, 30)
    entry_to: dtime = dtime(14, 45)
    flat_at: dtime = dtime(15, 15)
    max_trades_per_day: int = 1
    min_rr: float = 0.0             # reject setups below this reward/risk
    max_risk_pts: float = 1e9       # reject setups whose stop is absurdly far
    notes: str = ""


@dataclass
class Trade2:
    bot: str
    family: str
    sess: date
    entry_time: str
    exit_time: str
    option_type: str
    strike: float
    qty: int
    direction: int
    entry_spot: float
    exit_spot: float
    stop_spot: float
    target_spot: float
    rr: float
    entry_px: float
    entry_fill: float
    exit_px: float
    exit_fill: float
    gross: float
    costs: float
    net: float
    capital: float
    exit_reason: str
    bars_held: int
    mfe: float = 0.0
    mae: float = 0.0
    tag: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


# ───────────────────────────── DATA ─────────────────────────────

def daily_frame() -> pd.DataFrame:
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    c = d["close"]
    prev = c.shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev).abs(),
                    (d["low"] - prev).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    d["ema9"] = c.ewm(span=9, adjust=False).mean()
    d["ema21"] = c.ewm(span=21, adjust=False).mean()
    d["ema50"] = c.ewm(span=50, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi14"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    d["range_pct"] = (d["high"] - d["low"]) / c * 100
    d["range20"] = d["range_pct"].rolling(20).mean()
    d["sess"] = d["datetime"].dt.date
    return d


def session_panels(grid: Dict[str, pd.DataFrame]) -> Dict[date, Dict[str, Any]]:
    """
    One pass over the grid producing, per session, the spot path and the per-bar
    option volume. Built once; the candidate loop then does no groupby at all.
    """
    ce, pe = grid["ce"], grid["pe"]
    vol = (pd.concat([ce[["datetime", "volume"]], pe[["datetime", "volume"]]])
           .groupby("datetime")["volume"].sum())
    spot = ce.groupby("datetime")["spot"].first()
    df = pd.DataFrame({"spot": spot, "vol": vol}).dropna().sort_index()
    df["sess"] = df.index.date
    df["t"] = df.index.time
    df = df[(df["t"] >= dtime(9, 15)) & (df["t"] <= dtime(15, 25))]
    out: Dict[date, Dict[str, Any]] = {}
    for s, g in df.groupby("sess", sort=False):
        if len(g) < 40:
            continue
        out[s] = {"stamps": list(g.index), "times": list(g["t"]),
                  "spot": g["spot"].to_numpy(float), "vol": g["vol"].to_numpy(float)}
    return out


def option_index(grid: Dict[str, pd.DataFrame]) -> Dict[str, Dict[date, pd.DataFrame]]:
    return {s: {k: v.sort_values("datetime")
                for k, v in grid[s].groupby(grid[s]["datetime"].dt.date, sort=False)}
            for s in ("ce", "pe")}


# ───────────────────────────── CONTEXT ─────────────────────────────

@dataclass
class Ctx2:
    t: dtime
    i: int
    sess: date
    spot: float
    path: np.ndarray                # spot, bars 0..i
    vol: np.ndarray                 # option volume, bars 0..i
    times: List[dtime]
    atr: float
    prev_close: float
    prev_high: float
    prev_low: float
    prev_range_pct: float
    range20: float
    vix: float
    rsi: float
    ema_stack: int
    or_hi: float                    # 09:15-09:29 range
    or_lo: float
    or30_hi: float                  # 09:15-09:44 range
    or30_lo: float

    @property
    def open_px(self) -> float:
        return float(self.path[0])

    @property
    def twap(self) -> float:
        return float(self.path.mean())

    @property
    def vwap_opt(self) -> float:
        w = self.vol
        return float((self.path * w).sum() / w.sum()) if w.sum() > 0 else self.twap

    @property
    def sess_hi(self) -> float:
        return float(self.path.max())

    @property
    def sess_lo(self) -> float:
        return float(self.path.min())

    @property
    def gap_pct(self) -> float:
        return (self.open_px - self.prev_close) / self.prev_close * 100

    @property
    def first30_ret(self) -> float:
        """Return from previous close to the 09:45 bar. NaN before 09:45."""
        idx = [j for j, tt in enumerate(self.times[:self.i + 1]) if tt <= dtime(9, 45)]
        if not idx or self.times[self.i] < dtime(9, 45):
            return float("nan")
        return (float(self.path[idx[-1]]) - self.prev_close) / self.prev_close * 100

    def ret_over(self, bars: int) -> float:
        j = max(self.i - bars, 0)
        return float(self.path[self.i] - self.path[j])

    def rel_vol(self, bars: int = 6) -> float:
        """Recent bar volume against the session's own average so far."""
        if self.i < bars:
            return 1.0
        recent = self.vol[self.i - bars + 1:self.i + 1].mean()
        base = self.vol[:self.i + 1].mean()
        return float(recent / base) if base > 0 else 1.0


# ───────────────────────────── SIMULATION ─────────────────────────────

def simulate2(spec: Spec2, sessions: List[date], daily: pd.DataFrame,
              panels: Dict[date, Dict[str, Any]],
              opts: Dict[str, Dict[date, pd.DataFrame]],
              cost_mult: float = 1.0,
              skips: Optional[Dict[str, int]] = None) -> List[Trade2]:
    skips = skips if skips is not None else {}
    dpos = {d: i for i, d in enumerate(daily["sess"])}
    trades: List[Trade2] = []

    def bump(k: str) -> None:
        skips[k] = skips.get(k, 0) + 1

    for sess in sessions:
        p = panels.get(sess)
        if p is None:
            bump("NO_PANEL"); continue
        if sess not in dpos or dpos[sess] < 60:
            bump("NO_PRIOR_HISTORY"); continue
        prior = daily.iloc[dpos[sess] - 1]
        atr = float(prior["atr14"])
        if not np.isfinite(atr) or atr <= 0:
            bump("NO_ATR"); continue
        dce, dpe = opts["ce"].get(sess), opts["pe"].get(sess)
        if dce is None or dpe is None:
            bump("NO_OPTION_DATA"); continue

        vals, times, stamps, vols = p["spot"], p["times"], p["stamps"], p["vol"]
        m15 = [j for j, tt in enumerate(times) if tt < dtime(9, 30)]
        m30 = [j for j, tt in enumerate(times) if tt < dtime(9, 45)]
        or_hi = float(vals[m15].max()) if m15 else np.nan
        or_lo = float(vals[m15].min()) if m15 else np.nan
        or30_hi = float(vals[m30].max()) if m30 else np.nan
        or30_lo = float(vals[m30].min()) if m30 else np.nan

        ema_stack = (1 if prior["ema9"] > prior["ema21"] > prior["ema50"]
                     else (-1 if prior["ema9"] < prior["ema21"] < prior["ema50"] else 0))

        taken, i = 0, 0
        while i < len(vals) and taken < spec.max_trades_per_day:
            t = times[i]
            if t < spec.entry_from or t > spec.entry_to:
                i += 1; continue
            ctx = Ctx2(t=t, i=i, sess=sess, spot=float(vals[i]), path=vals[:i + 1],
                       vol=vols[:i + 1], times=times, atr=atr,
                       prev_close=float(prior["close"]), prev_high=float(prior["high"]),
                       prev_low=float(prior["low"]),
                       prev_range_pct=float(prior["range_pct"]),
                       range20=float(prior["range20"]), vix=float(prior["vix"]),
                       rsi=float(prior["rsi14"]), ema_stack=ema_stack,
                       or_hi=or_hi, or_lo=or_lo, or30_hi=or30_hi, or30_lo=or30_lo)
            try:
                su = spec.signal(ctx)
            except Exception:                                    # noqa: BLE001
                su = None
            if su is None or su.direction == 0:
                i += 1; continue

            risk = (ctx.spot - su.stop) * su.direction
            reward = (su.target - ctx.spot) * su.direction
            if risk <= 0 or reward <= 0:
                bump("BAD_LEVELS"); i += 1; continue
            if risk > spec.max_risk_pts:
                bump("RISK_TOO_WIDE"); i += 1; continue
            rr = reward / risk
            if rr < spec.min_rr:
                bump("RR_BELOW_MIN"); i += 1; continue

            dg = dce if su.direction > 0 else dpe
            ts = stamps[i]
            at = dg[dg["datetime"] == ts]
            if at.empty:
                bump("NO_OPTION_BAR"); i += 1; continue
            atm = round(ctx.spot / STRIKE_STEP) * STRIKE_STEP
            want = atm + su.strike_offset * STRIKE_STEP * su.direction
            cand = at.iloc[(at["strike"] - want).abs().argsort()]
            row = cand.iloc[0]
            if abs(float(row["strike"]) - want) > STRIKE_STEP:
                bump("STRIKE_UNAVAILABLE"); i += 1; continue
            strike, entry_px = float(row["strike"]), float(row["close"])
            if entry_px <= 0:
                bump("ZERO_PREMIUM"); i += 1; continue

            leg = dg[(dg["strike"] == strike) & (dg["datetime"] >= ts)]
            if len(leg) < 2:
                bump("NOT_QUOTED_FORWARD"); i += 1; continue

            e_fill = buy_fill(entry_px, cost_mult)
            capital = round(e_fill * LOT, 2)
            legmap = dict(zip(leg["datetime"], leg["close"]))

            exit_j, reason = None, "EOD"
            mfe = mae = 0.0
            bars = 0
            for j in range(i + 1, len(vals)):
                bars += 1
                s = float(vals[j])
                px = legmap.get(stamps[j])
                if px is not None and px > 0:
                    m = (float(px) - e_fill) * LOT
                    mfe, mae = max(mfe, m), min(mae, m)
                # stop is checked before target: on a bar that closes through both,
                # the adverse outcome is assumed
                if (s - su.stop) * su.direction <= 0:
                    exit_j, reason = j, "STOP"; break
                if (s - su.target) * su.direction >= 0:
                    exit_j, reason = j, "TARGET"; break
                if su.max_hold_bars and bars >= su.max_hold_bars:
                    exit_j, reason = j, "TIME"; break
                if times[j] >= spec.flat_at:
                    exit_j, reason = j, "EOD"; break
            if exit_j is None:
                exit_j, reason = len(vals) - 1, "SESSION_END"

            xpx = legmap.get(stamps[exit_j])
            if xpx is None or float(xpx) <= 0:
                back = [j for j in range(exit_j, i, -1) if legmap.get(stamps[j], 0) > 0]
                if not back:
                    bump("NO_EXIT_QUOTE"); i += 1; continue
                exit_j = back[0]
                xpx = legmap[stamps[exit_j]]
            exit_px = float(xpx)
            x_fill = sell_fill(exit_px, cost_mult)
            gross = round((x_fill - e_fill) * LOT, 2)
            costs = round(IndianCostModel.calculate_roundtrip_costs(
                e_fill, x_fill, LOT).total_costs * cost_mult, 2)

            trades.append(Trade2(
                bot=spec.name, family=spec.family, sess=sess, entry_time=str(t),
                exit_time=str(times[exit_j]),
                option_type="CE" if su.direction > 0 else "PE", strike=strike, qty=LOT,
                direction=su.direction, entry_spot=ctx.spot, exit_spot=float(vals[exit_j]),
                stop_spot=round(su.stop, 2), target_spot=round(su.target, 2),
                rr=round(rr, 2), entry_px=entry_px, entry_fill=e_fill,
                exit_px=exit_px, exit_fill=x_fill, gross=gross, costs=costs,
                net=round(gross - costs, 2), capital=capital, exit_reason=reason,
                bars_held=bars, mfe=round(mfe, 2), mae=round(mae, 2), tag=su.tag,
                meta={"atr": round(atr, 1), "vix": round(ctx.vix, 2),
                      "risk_pts": round(risk, 1), "reward_pts": round(reward, 1)},
            ))
            taken += 1
            i = exit_j + 1
    return trades


# ───────────────────────────── METRICS ─────────────────────────────

def split_sessions(days: List[date]):
    dev = [d for d in days if d <= DEV_END]
    val = [d for d in days if DEV_END < d <= VAL_END]
    hold = [d for d in days if HOLDOUT_START <= d <= HOLDOUT_END]
    return dev, val, hold


def tstat(trades: List[Trade2]) -> float:
    if len(trades) < 2:
        return float("nan")
    x = np.array([t.net for t in trades], float)
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")


def metrics2(trades: List[Trade2], sessions: List[date],
             account: float = 100000.0, lots: int = 1) -> Dict[str, Any]:
    """
    Daily percentages are taken against ACCOUNT, because the question asked is
    "what did the account do today". Return-on-deployed is reported separately
    against premium actually outlaid. Neither uses notional.
    """
    n_sess = len(sessions)
    if not trades:
        return {"trades": 0, "sessions": n_sess, "net": 0.0, "note": "no trades"}
    df = pd.DataFrame([t.__dict__ for t in trades])
    net = df["net"].astype(float) * lots
    wins, losses = net[net > 0], net[net <= 0]
    eq = net.cumsum()
    dd = float((eq - eq.cummax()).min())

    streak = mx = 0
    for x in net:
        if x <= 0:
            streak += 1; mx = max(mx, streak)
        else:
            streak = 0

    per_day = pd.Series(0.0, index=pd.Index(sorted(sessions)))
    g = df.assign(net=net).groupby("sess")["net"].sum()
    for s, v in g.items():
        if s in per_day.index:
            per_day.loc[s] += v
    rp = per_day / account * 100
    traded = per_day[per_day.index.isin(set(df["sess"]))]

    deployed = float(df["capital"].sum()) * lots
    maxcap = float(df.groupby("sess")["capital"].sum().max()) * lots
    gw, gl = float(wins.sum()), float(abs(losses.sum()))

    return {
        "trades": int(len(df)), "sessions": n_sess,
        "wins": int(len(wins)), "losses": int(len(losses)),
        "win_rate": round(len(wins) / len(df) * 100, 1),
        "gross": round(float(df["gross"].sum()) * lots, 2),
        "costs": round(float(df["costs"].sum()) * lots, 2),
        "net": round(float(net.sum()), 2),
        "expectancy": round(float(net.mean()), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "payoff": round(float(wins.mean() / abs(losses.mean())), 2)
                  if len(wins) and len(losses) and losses.mean() != 0 else None,
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "realized_rr": round(float(df["rr"].mean()), 2),
        "max_dd": round(abs(dd), 2),
        "max_losing_streak": int(mx),
        "capital_deployed": round(deployed, 2),
        "max_capital_used": round(maxcap, 2),
        "avg_capital": round(float(df["capital"].mean()) * lots, 2),
        "ret_on_deployed": round(float(net.sum()) / deployed * 100, 2) if deployed else 0.0,
        "ret_on_account": round(float(net.sum()) / account * 100, 2),
        "trades_per_day": round(len(df) / n_sess, 3) if n_sess else 0.0,
        "pct_sessions_traded": round(len(set(df["sess"])) / n_sess * 100, 1) if n_sess else 0.0,
        "avg_daily_pct": round(float(rp.mean()), 4),
        "median_daily_pct": round(float(rp.median()), 4),
        "avg_traded_day_pct": round(float((traded / account * 100).mean()), 4) if len(traded) else 0.0,
        "best_day": round(float(per_day.max()), 2),
        "worst_day": round(float(per_day.min()), 2),
        "pct_days_profitable": round(float((rp > 0).mean() * 100), 1),
        "pct_days_ge_0p25": round(float((rp >= 0.25).mean() * 100), 1),
        "pct_days_ge_0p5": round(float((rp >= 0.5).mean() * 100), 1),
        "pct_days_ge_1": round(float((rp >= 1).mean() * 100), 1),
        "pct_days_ge_2": round(float((rp >= 2).mean() * 100), 1),
        "pct_days_le_m0p5": round(float((rp <= -0.5).mean() * 100), 1),
        "pct_days_le_m1": round(float((rp <= -1).mean() * 100), 1),
        "pct_days_le_m2": round(float((rp <= -2).mean() * 100), 1),
        "profitable_days": int((per_day > 0).sum()),
        "losing_days": int((per_day < 0).sum()),
        "flat_days": int((per_day == 0).sum()),
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
        "tstat": round(tstat(trades), 2),
    }


def line2(name: str, m: Dict[str, Any], extra: str = "") -> str:
    if m.get("trades", 0) == 0:
        return f"{name:28}{'NO TRADES':>10}"
    return (f"{name:28}{m['trades']:>6}{m['win_rate']:>7.1f}{m['net']:>11,.0f}"
            f"{m['expectancy']:>9,.0f}{str(m['profit_factor']):>8}{m['max_dd']:>10,.0f}"
            f"{m['ret_on_deployed']:>8.2f}%{m['trades_per_day']:>8.2f}"
            f"{m['tstat']:>7.2f}{extra}")


HDR2 = (f"{'candidate':28}{'n':>6}{'win%':>7}{'net':>11}{'exp':>9}{'PF':>8}"
        f"{'maxDD':>10}{'ret/dep':>9}{'trd/d':>8}{'t':>7}")
