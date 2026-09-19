"""
OVERNIGHT DEV SWEEP — development set only (2020-09-01 .. 2024-09-17).

Round 1 asks one question: which tradable structure keeps the most of the index's
overnight drift after real fills and statutory charges? Nothing is filtered, so
there is no selection to overfit yet; the only choices are structural.

Validation (2024-09-18 .. 2025-09-17) and the one-year holdout (2025-09-18 ..
2026-09-18) are not read. The script asserts that.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.research.overnight import (
    DEV_END, HDR, Leg, OSpec, line, load_data, metrics, simulate_overnight, split,
)


def structures():
    C = []
    # ── A. short put verticals: drift + one night of decay, risk capped by width
    for off in (-2, -1, 0, 1, 2, 3):
        for width in (2, 3, 4):
            C.append(OSpec(
                f"PS_{off:+d}_w{width*50}", "put_spread",
                [Leg("PE", -1, off), Leg("PE", +1, off - width)],
                notes=f"short PE at ATM{off:+d}, long PE {width*50} lower"))
    # ── B. naked short put, for reference only: margin makes it a different animal
    for off in (0, 2):
        C.append(OSpec(f"PS_naked_{off:+d}", "naked_put", [Leg("PE", -1, off)],
                       notes="unprotected short put, SPAN margin"))
    # ── C. long call: the obvious way to be long overnight, and the expensive one
    for off in (0, 1, -1):
        C.append(OSpec(f"LC_{off:+d}", "long_call", [Leg("CE", +1, off)],
                       notes="long call held overnight, pays one night of theta"))
    # ── D. synthetic long future: delta 1, theta ~0, four crossings
    C.append(OSpec("SYNTH_0", "synthetic", [Leg("CE", +1, 0), Leg("PE", -1, 0)],
                   notes="long ATM call + short ATM put"))
    # ── E. call verticals: cheaper delta than a naked long call
    for off in (0, -1):
        for width in (2, 4):
            C.append(OSpec(f"CS_{off:+d}_w{width*50}", "call_spread",
                           [Leg("CE", +1, off), Leg("CE", -1, off + width)],
                           notes="bull call spread"))
    # ── F. CONTROL: the same structures on the wrong side. These must lose.
    for off in (0, -2):
        C.append(OSpec(f"CTRL_CS_short_{off:+d}", "control",
                       [Leg("CE", -1, off), Leg("CE", +1, off + 3)],
                       notes="bear call spread — control, should lose to the drift"))
    C.append(OSpec("CTRL_LP_0", "control", [Leg("PE", +1, 0)],
                   notes="long put overnight — control, should lose twice"))
    return C


def main() -> None:
    d = load_data()
    dev, val, hold = split(d.sessions)
    assert max(dev) <= DEV_END
    print(f"sessions: DEV {len(dev)} ({dev[0]} -> {dev[-1]})  "
          f"VAL {len(val)}  HOLDOUT {len(hold)}  [VAL/HOLDOUT NOT READ]\n")

    rows = []
    print(HDR)
    for spec in structures():
        skips = {}
        nights = simulate_overnight(spec, dev, d, skips=skips)
        m = metrics(nights, len(dev))
        print(line(spec.name, m))
        rows.append({"name": spec.name, "family": spec.family, **m,
                     "skips": str({k: v for k, v in skips.items() if k != "DTE_GATE"}),
                     "dte_gate": skips.get("DTE_GATE", 0), "notes": spec.notes})

    r = pd.DataFrame(rows)
    os.makedirs("reports", exist_ok=True)
    r.to_csv("reports/overnight_dev.csv", index=False)
    print("\nwrote reports/overnight_dev.csv")

    print("\nSKIP ACCOUNTING (must be complete — every DEV session in exactly one bucket)")
    for _, x in r.iterrows():
        traded = x["trades"] if x["trades"] else 0
        print(f"  {x['name']:22} traded={traded:>4}  dte_gate={x['dte_gate']:>4}  other={x['skips']}")


if __name__ == "__main__":
    main()
