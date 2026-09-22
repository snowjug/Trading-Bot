"""
Health check. Read-only, safe to run any time, exits non-zero if anything is unsafe.

Checks the invariants the agent's safety argument depends on, in the order that
matters most: live trading disabled, no secrets in source control, data present,
and the module graph importable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FAIL, WARN, OK = "FAIL", "WARN", "OK"
rows = []


def check(name, status, detail=""):
    rows.append((status, name, detail))


# 1. the invariant that matters most
try:
    from src.config import Config
    live = bool(getattr(Config, "LIVE_TRADING_ENABLED", False))
    check("LIVE_TRADING_ENABLED is false", OK if not live else FAIL, str(live))
except Exception as e:
    check("config importable", FAIL, f"{type(e).__name__}: {e}")

# 2. no secrets tracked by git
try:
    tracked = subprocess.run(["git", "ls-files", ".env"], capture_output=True,
                             text=True, timeout=30).stdout.strip()
    check(".env not tracked by git", OK if not tracked else FAIL, tracked or "untracked")
except Exception as e:
    check(".env tracking check", WARN, str(e))

# 3. credentials present but never printed
for var in ("DHAN_ACCESS_TOKEN", "DHAN_CLIENT_ID"):
    try:
        from src.config import Config as C
        v = str(getattr(C, var, "") or "")
        check(f"{var} present", OK if v else WARN, f"len={len(v)}" if v else "absent")
    except Exception as e:
        check(f"{var} present", WARN, str(e))

# 4. the agent module graph imports cleanly
for mod in ("src.market.market_state", "src.market.setups", "src.agent.decision_schema",
            "src.agent.deciders", "src.agent.trading_agent", "src.options.structures",
            "src.options.chain", "src.risk.structure_risk",
            "src.execution.agent_paper_executor", "src.research.agent_replay"):
    try:
        __import__(mod)
        check(f"import {mod}", OK)
    except Exception as e:
        check(f"import {mod}", FAIL, f"{type(e).__name__}: {e}")

# 5. configs parse
try:
    import yaml
    for f in ("configs/risk.yaml", "configs/market.yaml", "configs/agent.yaml"):
        yaml.safe_load(open(f, encoding="utf-8"))
    check("configs parse", OK)
except Exception as e:
    check("configs parse", FAIL, str(e))

# 6. naked short risk is structurally impossible
try:
    from src.agent.decision_schema import ALLOWED_STRUCTURES, BANNED_STRUCTURES
    from src.options.structures import build, validate_defined_risk
    bad = []
    for s in sorted(ALLOWED_STRUCTURES - {"NONE"}):
        if validate_defined_risk(build(s, 23000.0, width_steps=4, otm_steps=2)):
            bad.append(s)
    for s in sorted(BANNED_STRUCTURES):
        try:
            build(s, 23000.0)
            bad.append(f"{s}(builder exists!)")
        except ValueError:
            pass
    check("no allowed structure carries undefined risk", OK if not bad else FAIL,
          ",".join(bad))
except Exception as e:
    check("defined-risk invariant", FAIL, str(e))

# 7. the AI schema cannot touch sizing
try:
    from src.agent.decision_schema import AgentDecision
    forbidden = {"lots", "quantity", "size", "margin", "override", "force", "capital"}
    hit = set(AgentDecision.__dataclass_fields__) & forbidden
    check("AI schema exposes no sizing field", OK if not hit else FAIL, str(hit))
except Exception as e:
    check("AI schema check", FAIL, str(e))

# 8. data the replay needs
for p in ("data/derived/nifty_spot_5m.parquet", "data/derived/grid5m_ce.parquet",
          "data/derived/grid5m_pe.parquet", "data/catalog/lot_size_calendar.csv"):
    ok = os.path.exists(p)
    size = f"{os.path.getsize(p)/1e6:.1f}MB" if ok else "missing"
    check(f"data {p}", OK if ok else WARN, size)

worst = FAIL if any(r[0] == FAIL for r in rows) else (
    WARN if any(r[0] == WARN for r in rows) else OK)
print(f"HEALTH CHECK  {datetime.now():%Y-%m-%d %H:%M:%S}   overall={worst}")
print("-" * 78)
for status, name, detail in rows:
    print(f"  [{status:4}] {name:52} {detail}")
print("-" * 78)
print("no secret value is printed by this script, by design")
sys.exit(1 if worst == FAIL else 0)
