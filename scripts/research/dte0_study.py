"""
ZERO-DTE INTRADAY IRON CONDOR — development sweep, then validation.

The lead came from a monotone measurement, not from a search. Holding the same
structure fixed and varying only days-to-expiry on the development set:

    DTE 0 -> +Rs 141,174 (t=8.07)   DTE 1 -> +Rs 705 (t=0.07)
    DTE 2 ->   -Rs 9,772 (t=-1.62)  DTE 3 -> -Rs 31,882 (t=-8.34)
    DTE 6 ->  -Rs 35,096 (t=-12.35)

The economics are the reason. On expiry day the whole remaining extrinsic value of
the sold strikes decays inside one session, so a single four-leg round trip buys
the entire decay. On any other day the same round trip buys one day of theta, and
the spread on four legs costs more than that. The gradient is the mechanism
showing through, which is why this is worth validating rather than discarding as
another cell in a grid.

Days-to-expiry is derived from the NSE F&O bhavcopy expiry calendar, not guessed
from premium levels.

TWO SELECTION HAZARDS are measured here rather than assumed away:
  * wings must be priceable — the 5-minute grid spans ATM+/-6 strikes, so a wide
    wing is unavailable exactly on high-ATR sessions;
  * the exit mark must be fresh — trades whose exit is priced off a quote more
    than two bars old are refused.
Both refusals are counted and the refused sessions are compared against the taken
ones, so a filter that quietly removes the dangerous days cannot pass unnoticed.
"""

import os
import pickle
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.bot56_real_option_model import available_option_days, load_option_grid_5m
from src.research.intraday_premium import IPSpec, ip_metrics, run_intraday_premium
from src.research.lab2 import daily_frame, option_index, session_panels, split_sessions

E = dtime


def dte_map():
    return pickle.load(open("data/derived/session_dte.pkl", "rb"))


def build():
    C = []
    for sa in (0.25, 0.35, 0.45, 0.60):
        C.append(IPSpec(f"Z_sa{sa:.2f}", "condor", sa, 3, stop_mult=99.0,
                        notes=f"shorts {sa} ATR, 3-step wings, hold to 15:10"))
    for t, lbl in ((E(9, 30), "0930"), (E(9, 45), "0945"), (E(10, 30), "1030"),
                   (E(11, 30), "1130"), (E(13, 0), "1300")):
        C.append(IPSpec(f"T_{lbl}", "condor", 0.35, 3, entry_t=t, stop_mult=99.0,
                        notes=f"enter {lbl}"))
    for sm in (1.5, 2.0, 99.0):
        C.append(IPSpec(f"S_stop{sm:g}", "condor", 0.35, 3, stop_mult=sm,
                        notes="stop on spread mark" if sm < 99 else "no stop"))
    for xt, lbl in ((E(14, 30), "1430"), (E(15, 10), "1510")):
        C.append(IPSpec(f"X_{lbl}", "condor", 0.35, 3, exit_t=xt, stop_mult=99.0,
                        notes=f"exit {lbl}"))
    C.append(IPSpec("V_vix18", "condor", 0.35, 3, stop_mult=99.0, max_vix=18.0,
                    notes="VIX < 18"))
    C.append(IPSpec("L_put_only", "vertical_put", 0.35, 3, stop_mult=99.0,
                    notes="put side only"))
    C.append(IPSpec("L_call_only", "vertical_call", 0.35, 3, stop_mult=99.0,
                    notes="call side only"))
    return C


def conc(tr):
    a = np.array([t.net for t in tr], float)
    s = np.sort(a)[::-1]
    tot = a.sum()
    if tot <= 0:
        return "net<=0"
    return (f"top1 {s[0]/tot*100:>5.1f}%  w/o top2 {tot-s[0]-s[1]:>9,.0f}  "
            f"median {np.median(a):>7,.0f}  worst {a.min():>8,.0f}")


def hdr():
    return (f"{'candidate':16}{'n':>5}{'win%':>7}{'gross':>10}{'costs':>9}{'net':>10}"
            f"{'exp':>8}{'PF':>7}{'maxDD':>9}{'brch%':>7}{'credit':>8}{'risk':>9}{'t':>7}")


def row(n, m):
    if not m.get("trades"):
        return f"{n:16}{'NO TRADES':>10}"
    return (f"{n:16}{m['trades']:>5}{m['win_rate']:>7.1f}{m['gross']:>10,.0f}"
            f"{m['costs']:>9,.0f}{m['net']:>10,.0f}{m['expectancy']:>8,.0f}"
            f"{str(m['profit_factor']):>7}{m['max_dd']:>9,.0f}{m['breach_pct']:>7.1f}"
            f"{m['avg_credit_pts']:>8.2f}{m['avg_max_risk']:>9,.0f}{str(m['tstat']):>7}")


def main() -> int:
    daily = daily_frame()
    grid = load_option_grid_5m()
    panels = session_panels(grid)
    opts = option_index(grid)
    dev, val, hold = split_sessions(available_option_days(grid))
    dte = dte_map()
    d0 = [s for s in dev if dte.get(s) == 0]
    v0 = [s for s in val if dte.get(s) == 0]
    h0 = [s for s in hold if dte.get(s) == 0]
    print(f"expiry sessions — DEV {len(d0)} | VAL {len(v0)} | HOLDOUT {len(h0)} (frozen)")

    C = build()
    print(f"\ncandidates: {len(C)}\n" + "=" * 118)
    print("DEV (expiry sessions only)")
    print("=" * 118 + "\n" + hdr())
    res = {}
    for spec in C:
        sk = {}
        tr = run_intraday_premium(spec, d0, daily, panels, opts, skips=sk)
        m = ip_metrics(tr, d0)
        res[spec.name] = (spec, tr, m, sk)
        print(row(spec.name, m) + f"  {spec.notes}")

    base = res["Z_sa0.35"]
    print(f"\nrefusals on the base spec: {dict(sorted(base[3].items(), key=lambda x: -x[1]))}")
    taken = {t.sess for t in base[1]}
    refused = [s for s in d0 if s not in taken]
    dd = daily.set_index("sess")
    if refused:
        at = np.array([float(dd.loc[s, "atr14"]) for s in taken if s in dd.index])
        ar = np.array([float(dd.loc[s, "atr14"]) for s in refused if s in dd.index])
        vt = np.array([float(dd.loc[s, "vix"]) for s in taken if s in dd.index])
        vr = np.array([float(dd.loc[s, "vix"]) for s in refused if s in dd.index])
        print(f"SELECTION CHECK — taken {len(taken)}, refused {len(refused)}")
        print(f"  ATR taken {at.mean():>7.1f} / refused {ar.mean():>7.1f}")
        print(f"  VIX taken {vt.mean():>7.2f} / refused {vr.mean():>7.2f}")
        rng = {s: float(dd.loc[s, "range_pct"]) for s in dd.index}
        print(f"  prior-day range%% taken "
              f"{np.mean([rng[s] for s in taken if s in rng]):.3f} / refused "
              f"{np.mean([rng[s] for s in refused if s in rng]):.3f}")

    ok = [(n, r) for n, r in res.items() if r[2].get("trades", 0) > 0 and r[2]["net"] > 0]
    ok.sort(key=lambda x: -(x[1][2]["tstat"] or 0))
    print("\n" + "=" * 118)
    print(f"NET-POSITIVE ON DEV: {len(ok)} of {len(C)}")
    print("=" * 118)
    for n, (spec, tr, m, sk) in ok[:8]:
        print(f"  {n:16} t {str(m['tstat']):>6}  net {m['net']:>9,.0f}  "
              f"exp {m['expectancy']:>6,.0f}  n {m['trades']:>4}  win {m['win_rate']:>5.1f}%  "
              f"streak {m['max_losing_streak']}")
        print(f"      {conc(tr)}")

    # ── VALIDATION on the three strongest, unchanged ──
    keep = [n for n, _ in ok[:3]]
    print("\n" + "=" * 118)
    print(f"VALIDATION (expiry sessions, {val[0]} .. {val[-1]}) — {keep}")
    print("=" * 118 + "\n" + hdr())
    for n in keep:
        spec = res[n][0]
        tr = run_intraday_premium(spec, v0, daily, panels, opts, skips={})
        m = ip_metrics(tr, v0)
        print(row(n, m))
        if m.get("trades"):
            print(f"      {conc(tr)}")

    print("\n" + "=" * 118)
    print("COST SENSITIVITY ON VALIDATION")
    print("=" * 118)
    print(f"{'candidate':16}{'1.0x':>12}{'1.5x':>12}{'2.0x':>12}  survives 2x?")
    for n in keep:
        spec = res[n][0]
        nets = []
        for mlt in (1.0, 1.5, 2.0):
            tr = run_intraday_premium(spec, v0, daily, panels, opts, cost_mult=mlt, skips={})
            nets.append(ip_metrics(tr, v0).get("net", 0.0))
        print(f"{n:16}{nets[0]:>12,.0f}{nets[1]:>12,.0f}{nets[2]:>12,.0f}"
              f"  {'YES' if nets[2] > 0 else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
