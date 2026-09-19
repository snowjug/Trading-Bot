"""
OVERNIGHT FALSIFICATION — try to destroy the DEV result before believing it.

Run against the development set only. Each section is a way the number could be
fake; the candidate has to survive all of them to be worth validating.

  1. CONCENTRATION   remove the best nights. A convex strategy is allowed to earn
                     more from its winners than its losers, but not to depend on
                     two of them.
  2. REGIME          year by year, and 2020-21 removed entirely. The post-COVID
                     melt-up is the obvious way to fake a long-delta result.
  3. EXIT VENUE      the bhavcopy opening print is one trade. Re-price every exit
                     at the 09:20 grid bar instead, five minutes into a session
                     anybody could trade in, keeping the no-skip discipline.
  4. COST STRESS     1.5x and 2x the whole execution package.
  5. ENTRY VENUE     the 15:25 print replaced by the bhavcopy 30-minute VWAP.
  6. DAY STRUCTURE   day of week and days-to-expiry, to see whether the result is
                     one calendar artefact wearing a strategy's clothes.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.overnight import (
    DEV_END, Leg, OSpec, load_data, metrics, simulate_overnight, split, tstat,
)

CANDIDATES = [
    OSpec("LC_+1", "long_call", [Leg("CE", +1, 1)]),
    OSpec("LC_+0", "long_call", [Leg("CE", +1, 0)]),
    OSpec("LC_+2", "long_call", [Leg("CE", +1, 2)]),
]


def frame(nights) -> pd.DataFrame:
    return pd.DataFrame([{k: v for k, v in n.__dict__.items() if k != "legs"}
                         for n in nights])


def main() -> None:
    d = load_data()
    dev, _, _ = split(d.sessions)
    assert max(dev) <= DEV_END

    store = {}
    for spec in CANDIDATES:
        nights = simulate_overnight(spec, dev, d)
        store[spec.name] = frame(nights)

    print("=" * 96)
    print("1. CONCENTRATION — net points with the best nights removed")
    print("=" * 96)
    print(f"{'candidate':12}{'n':>5}{'net':>10}{'-top1':>10}{'-top2':>10}{'-top5':>10}"
          f"{'-top10':>10}{'t(-top2)':>10}{'best share':>12}")
    for k, df in store.items():
        s = df["net_pts"].sort_values()
        tot = s.sum()
        cuts = [s.iloc[:-i].sum() if i else tot for i in (0, 1, 2, 5, 10)]
        t2 = tstat(s.iloc[:-2].to_numpy(float))
        print(f"{k:12}{len(s):>5}{cuts[0]:>10.0f}{cuts[1]:>10.0f}{cuts[2]:>10.0f}"
              f"{cuts[3]:>10.0f}{cuts[4]:>10.0f}{t2:>10.2f}{s.iloc[-1]/tot*100:>11.1f}%")

    print("\n" + "=" * 96)
    print("2. REGIME — by calendar year, and with the post-COVID melt-up removed")
    print("=" * 96)
    for k, df in store.items():
        df["yr"] = pd.to_datetime(df["sess"]).dt.year
        print(f"\n{k}")
        print(f"  {'year':8}{'n':>5}{'exp pts':>10}{'t':>8}{'win%':>8}{'net Rs':>11}")
        for y, g in df.groupby("yr"):
            x = g["net_pts"].to_numpy(float)
            print(f"  {y:<8}{len(x):>5}{x.mean():>10.2f}{tstat(x):>8.2f}"
                  f"{(x > 0).mean()*100:>8.1f}{g['net'].sum():>11,.0f}")
        ex = df[~df["yr"].isin((2020, 2021))]["net_pts"].to_numpy(float)
        print(f"  {'ex20/21':8}{len(ex):>5}{ex.mean():>10.2f}{tstat(ex):>8.2f}"
              f"{(ex > 0).mean()*100:>8.1f}")

    print("\n" + "=" * 96)
    print("3. EXIT VENUE — 09:20 grid bar instead of the opening print")
    print("=" * 96)
    g = pd.read_parquet("data/derived/grid5m_ce.parquet",
                        columns=["datetime", "strike", "close", "sess"])
    g["t"] = g["datetime"].dt.time
    g0920 = g[g["t"].astype(str) == "09:15:00"]
    q = {(s, float(k)): float(c) for s, k, c in
         zip(g0920["sess"], g0920["strike"], g0920["close"]) if c > 0}
    print(f"{'candidate':12}{'n':>5}{'priced@0920':>13}{'exp(bhav)':>11}{'exp(0920)':>11}"
          f"{'t(0920)':>9}{'net Rs':>11}")
    for k, df in store.items():
        spec = next(s for s in CANDIDATES if s.name == k)
        nights = simulate_overnight(spec, dev, d)
        vals, npriced = [], 0
        for n in nights:
            L = n.legs[0]
            px = q.get((n.nxt, L["strike"]))
            if px is None:
                # no 09:20 print: keep the adverse assumption, worthless long leg
                px = 0.0
            else:
                npriced += 1
            from src.research.overnight import sell_fill
            gross = sell_fill(px) - L["entry_fill"]
            vals.append(gross - n.cost_pts)
        v = np.array(vals, float)
        print(f"{k:12}{len(v):>5}{npriced:>13}{df['net_pts'].mean():>11.2f}"
              f"{v.mean():>11.2f}{tstat(v):>9.2f}{v.sum()*65:>11,.0f}")

    print("\n" + "=" * 96)
    print("4. COST STRESS")
    print("=" * 96)
    print(f"{'candidate':12}{'1.0x':>10}{'t':>7}{'1.5x':>10}{'t':>7}{'2.0x':>10}{'t':>7}"
          f"{'3.0x':>10}{'t':>7}")
    for spec in CANDIDATES:
        cells = []
        for m in (1.0, 1.5, 2.0, 3.0):
            nights = simulate_overnight(spec, dev, d, cost_mult=m)
            x = np.array([n.net_pts for n in nights], float)
            cells += [f"{x.mean():>10.2f}", f"{tstat(x):>7.2f}"]
        print(f"{spec.name:12}" + "".join(cells))

    print("\n" + "=" * 96)
    print("5. ENTRY VENUE — bhavcopy 30-minute VWAP close instead of the 15:25 print")
    print("=" * 96)
    bh = pd.read_parquet(
        "data/raw/nse/fo_bhavcopy/.consolidated_1904_1789736982937725100.parquet",
        columns=["TradDt", "XpryDt", "StrkPric", "OptnTp", "ClsPric"])
    bh["sess"] = pd.to_datetime(bh["TradDt"]).dt.date
    bh = bh[(bh["OptnTp"] == "CE") & (bh["ClsPric"] > 0)]
    cl = {(s, float(k), x): float(c) for s, k, x, c in
          zip(bh["sess"], bh["StrkPric"], bh["XpryDt"], bh["ClsPric"])}
    from src.research.overnight import buy_fill
    print(f"{'candidate':12}{'n':>5}{'exp(15:25)':>12}{'exp(vwap)':>11}{'t':>9}")
    for spec in CANDIDATES:
        nights = simulate_overnight(spec, dev, d)
        vals = []
        for n in nights:
            L = n.legs[0]
            c = cl.get((n.sess, L["strike"], n.expiry))
            if c is None:
                continue
            vals.append((L["exit_fill"] - buy_fill(c)) - n.cost_pts)
        v = np.array(vals, float)
        base = np.array([n.net_pts for n in nights], float)
        print(f"{spec.name:12}{len(v):>5}{base.mean():>12.2f}{v.mean():>11.2f}{tstat(v):>9.2f}")

    print("\n" + "=" * 96)
    print("6. DAY STRUCTURE — day of week and days to expiry")
    print("=" * 96)
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for k, df in store.items():
        df["dow"] = df["meta"].apply(lambda m: m["dow"])
        print(f"\n{k}  by weekday of the ENTRY session")
        print(f"  {'dow':6}{'n':>5}{'exp pts':>10}{'t':>8}{'win%':>8}")
        for w, gg in df.groupby("dow"):
            x = gg["net_pts"].to_numpy(float)
            print(f"  {dows[int(w)]:6}{len(x):>5}{x.mean():>10.2f}{tstat(x):>8.2f}"
                  f"{(x > 0).mean()*100:>8.1f}")
        print(f"  by days to expiry")
        print(f"  {'dte':6}{'n':>5}{'exp pts':>10}{'t':>8}{'win%':>8}")
        for w, gg in df.groupby("dte"):
            if len(gg) < 20:
                continue
            x = gg["net_pts"].to_numpy(float)
            print(f"  {int(w):<6}{len(x):>5}{x.mean():>10.2f}{tstat(x):>8.2f}"
                  f"{(x > 0).mean()*100:>8.1f}")


if __name__ == "__main__":
    main()
