"""
Does the VWAP_REVERSION inversion pay for the option? Authentic premium only.

    python scripts/research/vwap_inversion_pnl.py --start 2022-01-01 --end 2023-12-31

PRE-REGISTERED BEFORE RUNNING. Written from the two-window calibration result in
`reports/CALIBRATION_DEV_VS_VAL.md` and fixed here so the outcome cannot reshape it:

  HYPOTHESIS   After a VWAP stretch that `VWAP_REVERSION` flags, NIFTY CONTINUES rather
               than reverting, at a 60-minute horizon, on EITHER side. The family was
               wrong at 41.9% (z=+2.73) on 2022-2023 and 39.9% (z=+2.86) on 2024-2025.

  RULE         At every bar the family fires, buy the ATM option OPPOSITE to the stated
               direction. Detector says -1 (expect down) -> buy CE. Says +1 -> buy PE.
               Hold 60 minutes, exit at that bar's close, same session only.

  WHY FAMILY-LEVEL AND NOT PER SIDE  The side attribution FAILED validation: dir=-1 was
               z=+3.26 on DEV and +1.71 on VAL, while dir=+1 went from +0.04 to +2.48.
               The wrong side swapped, so a per-side rule would be fitted to one window.

  NO FREE PARAMETERS  Strike = nearest to spot at entry, held to exit (never
               re-selected). Hold = 60 minutes, the calibration horizon. Two expressions
               are reported, both stated here: a single long ATM option, and an ATM debit
               vertical one strike (50 points) further out. Two expressions x two
               windows = 4 tests; that is the multiple-testing count.

  CONTROL      At each signal bar BOTH the CE and the PE outcome are computed. INVERTED
               picks one by the detector's sign, AS-IS picks the other, and UNCONDITIONAL
               is their mean - exactly what picking at random would earn. So
               INVERTED - UNCONDITIONAL isolates the SELECTION edge from the cost of
               simply being long an option, and INVERTED + AS-IS = 2 x UNCONDITIONAL is
               an internal consistency check the output prints.

UNPRICEABLE, NEVER SUBSTITUTED. A leg with no authentic traded bar at entry or exit is
excluded and counted. No synthetic premium, no fixed premium, no theoretical value, no
carried-forward price.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.cost_model import IndianCostModel
from src.market.market_state import StateBuilder, resample
from src.market.setups import detect
from src.research.option_lots import lot_map

SPOT5 = "data/derived/nifty_spot_5m.parquet"
GRID = {"CE": "data/derived/grid5m_ce.parquet", "PE": "data/derived/grid5m_pe.parquet"}
PANEL = "data/derived/chain_panel.parquet"
STRIKE_STEP = 50.0
KEY_MUL = 100_000          # ts_seconds * KEY_MUL + strike, both fit in int64


class PriceBook:
    """
    Authentic traded 5-minute option closes, looked up by (timestamp, strike).

    Stored as sorted int64 keys + a float array and queried with searchsorted, so a
    six-year grid costs a few tens of MB instead of a dict with millions of tuple keys.
    A miss returns None and the caller must treat the trade as UNPRICEABLE.
    """

    def __init__(self, path: str):
        d = pd.read_parquet(path, columns=["datetime", "strike", "close"])
        d = d[d["close"] > 0]
        ts = (d["datetime"].astype("int64") // 1_000_000_000).to_numpy()
        key = ts * KEY_MUL + d["strike"].to_numpy(np.int64)
        order = np.argsort(key, kind="stable")
        self.key = key[order]
        self.val = d["close"].to_numpy(float)[order]

    def at(self, ts_sec: int, strike: float):
        k = int(ts_sec) * KEY_MUL + int(strike)
        i = np.searchsorted(self.key, k)
        if i < len(self.key) and self.key[i] == k:
            return float(self.val[i])
        return None


def leg_pnl_points(book: PriceBook, ts_in: int, ts_out: int, strike: float):
    """Long one option: (entry, exit, points). None if either end is unpriceable."""
    e = book.at(ts_in, strike)
    x = book.at(ts_out, strike)
    if e is None or x is None:
        return None
    return e, x, x - e


def spread_pnl_points(book: PriceBook, ts_in: int, ts_out: int,
                      long_k: float, short_k: float):
    """
    Debit vertical: long the nearer strike, short one further out.

    Returns the net debit, net exit, net points AND both legs' own entry/exit prices, so
    friction can be charged per leg on the turnover each leg actually generates rather
    than on the net.
    """
    a = leg_pnl_points(book, ts_in, ts_out, long_k)
    b = leg_pnl_points(book, ts_in, ts_out, short_k)
    if a is None or b is None:
        return None
    debit = a[0] - b[0]
    if debit <= 0:                     # not a debit spread; refuse rather than model it
        return None
    return (debit, (a[1] - b[1]), (a[2] - b[2]),
            {"long_in": a[0], "long_out": a[1], "short_in": b[0], "short_out": b[1]})


def leg_cost_rs(open_pts: float, close_pts: float, side: str, lot: int,
                half_spread_pts: float) -> float:
    """
    Statutory friction for ONE leg of one round trip.

    The cost model charges STT on the price it is given as `exit_price` and stamp duty on
    `entry_price`, because it assumes buy-then-sell. A SHORT leg sells first, so its
    arguments are swapped: that puts STT on the opening sale and stamp duty on the
    closing purchase, which is where they actually fall. Charging a spread's net debit as
    a single two-order round trip would understate brokerage by half and put STT on the
    wrong side, so every leg is priced separately.
    """
    buy_px, sell_px = ((open_pts, close_pts) if side == "BUY"
                       else (close_pts, open_pts))
    cb = IndianCostModel.calculate_roundtrip_costs(
        entry_price=max(0.05, float(buy_px)), exit_price=max(0.0, float(sell_px)),
        quantity=int(lot), slippage_points=0.10)
    # half-spread paid on entry and exit of this leg
    return float(cb.total_costs) + 2.0 * float(half_spread_pts) * int(lot)


def money(legs, pnl_pts: float, lot: int, half_spread_pts: float) -> float:
    """
    Rupee P&L of a structure: gross points x lot, minus per-leg friction.

    `legs` is [(open_pts, close_pts, "BUY"|"SELL"), ...] so a 2-leg vertical is charged
    four orders and two spreads, not two and one.
    """
    gross = float(pnl_pts) * int(lot)
    cost = sum(leg_cost_rs(o, c, side, lot, half_spread_pts) for o, c, side in legs)
    return gross - cost


def thinned_t(vals, times, hold_min):
    """t-stat on a maximal non-overlapping subset, so shared windows cannot inflate it."""
    if not vals:
        return 0, float("nan"), float("nan")
    order = np.argsort(times)
    keep, cutoff = [], None
    for i in order:
        t = times[i]
        if cutoff is None or t >= cutoff:
            keep.append(i)
            cutoff = t + pd.Timedelta(minutes=hold_min)
    v = np.array([vals[i] for i in keep], float)
    if len(v) < 2 or v.std(ddof=1) == 0:
        return len(v), float(v.mean()) if len(v) else float("nan"), float("nan")
    return len(v), float(v.mean()), float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--hold", type=int, default=60)
    ap.add_argument("--out", default=None)
    ap.add_argument("--events-out", default=None,
                    help="save the detected signal bars so a later study need not re-detect")
    args = ap.parse_args()

    s5 = pd.read_parquet(SPOT5)
    s5["datetime"] = pd.to_datetime(s5["datetime"])
    s5 = s5.sort_values("datetime").reset_index(drop=True)
    frames = {"5m": s5, "15m": resample(s5, "15min"), "30m": resample(s5, "30min"),
              "1h": resample(s5, "60min"), "1d": resample(s5, "1D")}
    sb = StateBuilder("NIFTY", frames, primary_tf="5m", source="REPLAY_GRID")

    print("loading authentic option grids ...", flush=True)
    books = {k: PriceBook(v) for k, v in GRID.items()}
    print(f"  CE {len(books['CE'].key):,} priced bars   PE {len(books['PE'].key):,}",
          flush=True)

    # AUTHENTIC LOT SIZE. `chain_panel.lot_size` is populated only from 2024 (668 of
    # 1,903 sessions), so a 2022-2023 window has none and the first run of this script
    # dropped every single signal as NO_LOT rather than inventing one. The lot is instead
    # derived from the exchange's own notional turnover, which agrees with chain_panel on
    # 33 of 33 overlapping months and covers all 1,904 sessions.
    lots = lot_map("NIFTY")
    p = pd.read_parquet(PANEL, columns=["date", "lot_size"])
    ref = {d.date(): int(v) for d, v in zip(pd.to_datetime(p["date"]), p["lot_size"])
           if np.isfinite(v) and v > 0}
    clash = [(d, lots[d], ref[d]) for d in ref if d in lots and lots[d] != ref[d]]
    if clash:
        print(f"REFUSING TO RUN: derived lot disagrees with chain_panel on "
              f"{len(clash)} sessions, e.g. {clash[:3]}")
        return 1
    print(f"  authentic lot size for {len(lots):,} sessions "
          f"(agrees with chain_panel on all {len(ref):,} it covers)", flush=True)

    close = s5["close"].to_numpy(float)
    sess = s5["datetime"].dt.date.to_numpy()
    ts = s5["datetime"].to_numpy()
    ts_sec = (s5["datetime"].astype("int64") // 1_000_000_000).to_numpy()
    a, b = pd.Timestamp(args.start).date(), pd.Timestamp(args.end).date()
    idxs = np.flatnonzero(np.array([(a <= d <= b) for d in sess]))
    n_bars = max(1, args.hold // 5)
    print(f"window {a} .. {b}   bars {len(idxs):,}   hold {args.hold}min", flush=True)

    rows, events = [], []
    skip = {"CROSSES_SESSION": 0, "NO_LOT": 0,
            "UNPRICEABLE_OPTION": 0, "UNPRICEABLE_SPREAD": 0}
    for c_i, i in enumerate(idxs):
        if c_i % 5000 == 0 and c_i:
            print(f"  ...{c_i:,}/{len(idxs):,}  signals={len(rows):,}", flush=True)
        j = i + n_bars
        if j >= len(close) or sess[j] != sess[i]:
            skip["CROSSES_SESSION"] += 1
            continue
        try:
            st = sb.at(pd.Timestamp(ts[i]))
        except Exception:                                        # noqa: BLE001
            continue
        sig = next((c for c in detect(st) if c.kind == "VWAP_REVERSION"), None)
        if sig is None:
            continue
        lot = lots.get(sess[i])
        if not lot:
            skip["NO_LOT"] += 1
            continue

        atm = round(float(close[i]) / STRIKE_STEP) * STRIKE_STEP
        ti, to = int(ts_sec[i]), int(ts_sec[j])
        ce = leg_pnl_points(books["CE"], ti, to, atm)
        pe = leg_pnl_points(books["PE"], ti, to, atm)
        if ce is None or pe is None:
            skip["UNPRICEABLE_OPTION"] += 1
            continue
        ce_sp = spread_pnl_points(books["CE"], ti, to, atm, atm + STRIKE_STEP)
        pe_sp = spread_pnl_points(books["PE"], ti, to, atm, atm - STRIKE_STEP)
        if ce_sp is None or pe_sp is None:
            skip["UNPRICEABLE_SPREAD"] += 1

        # inverted = buy the side OPPOSITE the detector: -1 (expect down) -> CE
        inv_is_ce = sig.direction < 0
        rows.append({
            "bar_time": pd.Timestamp(ts[i]), "sess": str(sess[i]),
            "direction": int(sig.direction), "quality": sig.quality_hint,
            "atm": atm, "lot": lot, "inv_is_ce": bool(inv_is_ce),
            "spot_in": float(close[i]), "spot_out": float(close[j]),
            "ce_entry": ce[0], "ce_pts": ce[2], "pe_entry": pe[0], "pe_pts": pe[2],
            "ce_sp_entry": (ce_sp[0] if ce_sp else None),
            "ce_sp_pts": (ce_sp[2] if ce_sp else None),
            "pe_sp_entry": (pe_sp[0] if pe_sp else None),
            "pe_sp_pts": (pe_sp[2] if pe_sp else None),
            **{f"ce_sp_{k}": (ce_sp[3][k] if ce_sp else None)
               for k in ("long_in", "long_out", "short_in", "short_out")},
            **{f"pe_sp_{k}": (pe_sp[3][k] if pe_sp else None)
               for k in ("long_in", "long_out", "short_in", "short_out")},
        })
        events.append({"bar_time": pd.Timestamp(ts[i]), "bar_index": int(i),
                       "family": sig.kind, "direction": int(sig.direction),
                       "quality_hint": sig.quality_hint,
                       "expected_move_pts": float(sig.expected_move_pts or 0.0),
                       "expected_move_horizon_minutes":
                           int(sig.expected_move_horizon_minutes)})

    print(f"\nsignals priced: {len(rows):,}   skipped: {skip}")
    if not rows:
        print("nothing to measure")
        return 0
    df = pd.DataFrame(rows)
    if args.events_out:
        os.makedirs(os.path.dirname(args.events_out) or ".", exist_ok=True)
        pd.DataFrame(events).to_parquet(args.events_out, index=False)
        print(f"wrote {args.events_out} ({len(events):,} events)")

    def legs_for(expr, r, opt):
        """
        The orders actually sent, with each leg's OWN authentic prices, so STT lands on
        the turnover that leg really generated. `opt` is "ce" or "pe".
        """
        if expr == "LONG_ATM_OPTION":
            e = r[f"{opt}_entry"]
            return [(e, e + r[f"{opt}_pts"], "BUY")]
        return [(r[f"{opt}_sp_long_in"], r[f"{opt}_sp_long_out"], "BUY"),
                (r[f"{opt}_sp_short_in"], r[f"{opt}_sp_short_out"], "SELL")]

    results = {}
    for expr, ce_p, pe_p, ce_e, pe_e in (
            ("LONG_ATM_OPTION", "ce_pts", "pe_pts", "ce_entry", "pe_entry"),
            ("ATM_DEBIT_VERTICAL", "ce_sp_pts", "pe_sp_pts", "ce_sp_entry", "pe_sp_entry")):
        need = [ce_p, pe_p, ce_e, pe_e]
        if expr == "ATM_DEBIT_VERTICAL":
            need += [f"{o}_sp_{k}" for o in ("ce", "pe")
                     for k in ("long_in", "long_out", "short_in", "short_out")]
        d = df.dropna(subset=need)
        if d.empty:
            continue
        print("\n" + "=" * 104)
        print(f"{expr}   n={len(d):,} priced signals   hold {args.hold}min")
        print("=" * 104)
        print(f"{'half-spread':>12}{'rule':>16}{'trades':>8}{'indep':>7}"
              f"{'mean Rs':>11}{'t':>8}{'win%':>7}{'total Rs':>13}")
        for hs in (0.0, 0.5, 1.0):
            per = {}
            for rule in ("INVERTED", "AS_IS", "UNCONDITIONAL"):
                vals, times = [], []
                for _, r in d.iterrows():
                    ce_m = money(legs_for(expr, r, "ce"), r[ce_p], r["lot"], hs)
                    pe_m = money(legs_for(expr, r, "pe"), r[pe_p], r["lot"], hs)
                    pick = (ce_m if r["inv_is_ce"] else pe_m)
                    other = (pe_m if r["inv_is_ce"] else ce_m)
                    v = (pick if rule == "INVERTED" else
                         other if rule == "AS_IS" else 0.5 * (pick + other))
                    vals.append(v)
                    times.append(r["bar_time"])
                n_i, mean_i, t_i = thinned_t(vals, times, args.hold)
                win = 100.0 * float(np.mean(np.array(vals) > 0))
                per[rule] = {"trades": len(vals), "n_independent": n_i,
                             "mean_rs_independent": round(mean_i, 2),
                             "t_independent": round(t_i, 2),
                             "win_pct_all": round(win, 1),
                             "total_rs_all": round(float(np.sum(vals)), 0)}
                print(f"{hs:>12.1f}{rule:>16}{len(vals):>8}{n_i:>7}"
                      f"{mean_i:>11.0f}{t_i:>8.2f}{win:>7.1f}{np.sum(vals):>13,.0f}")
            chk = (per["INVERTED"]["mean_rs_independent"]
                   + per["AS_IS"]["mean_rs_independent"]
                   - 2 * per["UNCONDITIONAL"]["mean_rs_independent"])
            print(f"{'':>12}{'consistency':>16}  INVERTED + AS_IS - 2*UNCONDITIONAL "
                  f"= {chk:+.2f} (must be ~0)")
            results[f"{expr}|half_spread={hs}"] = per
        print("\nby year, INVERTED, half-spread 0.5:")
        for y, g in d.groupby(d["bar_time"].dt.year):
            vals = [money(legs_for(expr, r, "ce"), r[ce_p], r["lot"], 0.5)
                    if r["inv_is_ce"] else
                    money(legs_for(expr, r, "pe"), r[pe_p], r["lot"], 0.5)
                    for _, r in g.iterrows()]
            n_i, mean_i, t_i = thinned_t(vals, list(g["bar_time"]), args.hold)
            print(f"  {y}  n={len(vals):>4}  indep={n_i:>4}  mean Rs {mean_i:>8.0f}  "
                  f"t={t_i:>6.2f}  total Rs {np.sum(vals):>12,.0f}")

    out = args.out or f"reports/vwap_inversion_pnl_{a}_{b}.json"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"window": {"start": str(a), "end": str(b)},
                   "hold_minutes": args.hold, "signals_priced": len(df),
                   "skipped": skip, "cost_model_version": IndianCostModel.VERSION,
                   "results": results}, f, indent=2, default=float)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
