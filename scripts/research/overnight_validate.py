"""
OVERNIGHT VALIDATION — the candidate set is fixed in this file BEFORE it is run
against VAL (2024-09-18 .. 2025-09-17). The one-year holdout is not touched here.

PROMOTION GATE, stated before the numbers exist:
    VAL expectancy > 0  AND  VAL t >= 2.0  AND  VAL net > 0
    AND the control (bear call spread, unfiltered) must remain NEGATIVE on VAL,
    because if the control turns positive the engine is measuring something other
    than the direction it claims to measure.

Candidates were chosen on DEV as follows, and the DEV numbers are recorded here so
that the comparison is not reconstructed after the fact:

    ODC1  LC_-1 | PCR_OI>1.1     DEV +9.44 pts/night  t=3.00  n=195  cap Rs 11,856
    ODC2  LC_+0 | PCR_OI>1.1     DEV +8.12            t=2.93  n=195  cap Rs  9,835
    ODC3  PS_+2_w400 | PCR>1.1   DEV +7.36            t=2.39  n=195  cap Rs 21,380
    ODC4  SYNTH_0 | PCR_OI>1.1   DEV +16.25           t=3.23  n=195  cap Rs 168,862
    ODC5  PS_naked_+2 | PCR>1.1  DEV +10.79           t=3.12  n=195  cap Rs 168,862
    ODC6  LC_-1 | PCR pct>70     DEV +7.01            t=2.50  n=215  cap Rs 11,856
    REF*  the same structures unfiltered
    CTRL  bear call spread, 300 wide, unfiltered   DEV -5.76  t=-4.54

KNOWN WEAKNESS, recorded before validation: on DEV every candidate's significance
comes from 2021. Ex-2020/21 the best is ODC1 at +5.20 pts, t=1.41, and 2024 alone
is -1.59. The threshold curve from PCR 0.9 to 1.4 is smooth rather than a cliff,
so the 1.1 cut is not itself fitted, but the effect is not stable across years.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.overnight import (
    DEV_END, HDR, Leg, OSpec, VAL_END, VAL_START, line, load_data, metrics,
    simulate_overnight, split, tstat,
)

F_PCR = lambda r: r["pcr_oi"] > 1.1                       # noqa: E731
F_PCT = lambda r: r["pcr_oi_pct"] > 70                    # noqa: E731

DEV_REFERENCE = {
    "ODC1_LC-1_PCR": (9.44, 3.00), "ODC2_LC+0_PCR": (8.12, 2.93),
    "ODC3_PS+2w400_PCR": (7.36, 2.39), "ODC4_SYNTH_PCR": (16.25, 3.23),
    "ODC5_naked+2_PCR": (10.79, 3.12), "ODC6_LC-1_PCRpct": (7.01, 2.50),
    "REF_LC-1": (1.98, 1.11), "REF_PS+2w400": (4.71, 2.73),
    "REF_naked+2": (5.29, 2.45), "CTRL_CS_short": (-5.76, -4.54),
}


def candidates():
    return [
        OSpec("ODC1_LC-1_PCR", "long_call", [Leg("CE", +1, -1)], filter_fn=F_PCR),
        OSpec("ODC2_LC+0_PCR", "long_call", [Leg("CE", +1, 0)], filter_fn=F_PCR),
        OSpec("ODC3_PS+2w400_PCR", "put_spread",
              [Leg("PE", -1, 2), Leg("PE", +1, -6)], filter_fn=F_PCR),
        OSpec("ODC4_SYNTH_PCR", "synthetic",
              [Leg("CE", +1, 0), Leg("PE", -1, 0)], filter_fn=F_PCR),
        OSpec("ODC5_naked+2_PCR", "naked_put", [Leg("PE", -1, 2)], filter_fn=F_PCR),
        OSpec("ODC6_LC-1_PCRpct", "long_call", [Leg("CE", +1, -1)], filter_fn=F_PCT),
        OSpec("REF_LC-1", "long_call", [Leg("CE", +1, -1)]),
        OSpec("REF_PS+2w400", "put_spread", [Leg("PE", -1, 2), Leg("PE", +1, -6)]),
        OSpec("REF_naked+2", "naked_put", [Leg("PE", -1, 2)]),
        OSpec("CTRL_CS_short", "control",
              [Leg("CE", -1, 0), Leg("CE", +1, 6)]),
    ]


def main() -> None:
    d = load_data()
    dev, val, hold = split(d.sessions)
    assert min(val) >= VAL_START and max(val) <= VAL_END, "VAL window wrong"
    print(f"VAL sessions {len(val)}  {val[0]} -> {val[-1]}")
    print(f"HOLDOUT sessions {len(hold)}  NOT READ BY THIS SCRIPT\n")

    rows = []
    print(f"{'candidate':20}{'DEV exp':>9}{'DEV t':>7}  |{'n':>5}{'VAL exp':>9}{'VAL t':>7}"
          f"{'win%':>7}{'net Rs':>10}{'maxDD':>9}{'cap':>9}{'PF':>7}  gate")
    for spec in candidates():
        nights = simulate_overnight(spec, val, d)
        m = metrics(nights, len(val))
        de, dt = DEV_REFERENCE[spec.name]
        if m.get("trades", 0) == 0:
            print(f"{spec.name:20}{de:>9.2f}{dt:>7.2f}  |{'NO TRADES':>30}")
            rows.append({"name": spec.name, "dev_exp": de, "dev_t": dt, "trades": 0})
            continue
        passed = (m["expectancy_pts"] > 0 and m["tstat"] >= 2.0 and m["net"] > 0)
        gate = "PROMOTE" if passed else "reject"
        if spec.name.startswith("CTRL"):
            gate = "control OK (negative)" if m["expectancy_pts"] < 0 else "CONTROL POSITIVE — ENGINE SUSPECT"
        print(f"{spec.name:20}{de:>9.2f}{dt:>7.2f}  |{m['trades']:>5}"
              f"{m['expectancy_pts']:>9.2f}{m['tstat']:>7.2f}{m['win_rate']:>7.1f}"
              f"{m['net']:>10,.0f}{m['max_dd']:>9,.0f}{m['max_capital_used']:>9,.0f}"
              f"{str(m['profit_factor']):>7}  {gate}")
        rows.append({"name": spec.name, "family": spec.family, "dev_exp": de,
                     "dev_t": dt, "gate": gate,
                     **{k: v for k, v in m.items() if k != "exit_reasons"}})

    r = pd.DataFrame(rows)
    os.makedirs("reports", exist_ok=True)
    r.to_csv("reports/overnight_validation.csv", index=False)
    prom = r[r.get("gate", pd.Series(dtype=str)) == "PROMOTE"]
    print(f"\nPROMOTED: {len(prom)}  {list(prom['name']) if len(prom) else '(none)'}")
    print("wrote reports/overnight_validation.csv")


if __name__ == "__main__":
    main()
