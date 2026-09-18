"""
End-to-end proof that each bot's execution path works, on LIVE quotes.

WHY THIS EXISTS. A strategy may legitimately sit in WAIT all session, so "no trade
happened" cannot be evidence that the path works. This drives each bot's ACTUAL
structure — Bot 1's four-leg condor, Bot 2's two-leg vertical, Bot 6's and Bot 7's
single long option — through the real chain:

  real contract resolution -> live two-sided quote -> risk engine -> paper fill
  -> live marking -> exit -> realised P&L

Everything is real except the decision to enter, which is forced. Because the
decision is forced, every position is written to the SHADOW ledger and never to
PAPER. Shadow and paper are separate objects in the broker and separate keys in
the ledger file; nothing here can reach the paper P&L.
"""
import os, sys, json, time
from datetime import date, datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv; load_dotenv()

from src.config import Config
from src.data.dhan_client import get_dhan_client
from src.execution import bot_signals as BS
from src.execution.paper_engine import PaperBroker, validate_quote
from src.execution.paper_engine import LegSpec
from src.risk.risk_engine import RiskEngine
sys.path.insert(0, "scripts")
from run_paper_session import resolve_legs, risk_gate, leg_quotes, next_weekly_expiry

Config.assert_no_live_trading()
print(f"SAFETY: LIVE_TRADING_ENABLED={Config.LIVE_TRADING_ENABLED}\n")

client = get_dhan_client()
broker = PaperBroker(session_dir="data/paper_session")
risk = RiskEngine(initial_capital=100000.0, max_simultaneous_positions=8, max_position_pct=0.35)

idx = client.fetch_marketfeed_quote([13, 21], exchange_segment="IDX_I")
spot = float(idx.get("13", {}).get("ltp") or 0)
vix  = float(idx.get("21", {}).get("ltp") or 0)
expiry = next_weekly_expiry("NIFTY", date.today())
print(f"LIVE  NIFTY={spot}  VIX={vix}  expiry={expiry}\n")
assert spot > 0 and vix > 0, "no live index data"

em = BS.expected_move(spot, vix)
so, wo = BS.offset_steps(1.8*em), BS.offset_steps(2.4*em)
s2, w2 = BS.offset_steps(1.3*em), BS.offset_steps(1.9*em)

class D:
    def __init__(self, legs, **kw):
        self.legs = legs
        for k, v in kw.items(): setattr(self, k, v)

CASES = [
    ("BOT1", "Strategy 1: Apex VRP Engine", "4-leg iron condor", D([
        LegSpec("short_call","CE","SELL",strike_offset=so),
        LegSpec("long_call","CE","BUY",strike_offset=wo),
        LegSpec("short_put","PE","SELL",strike_offset=-so),
        LegSpec("long_put","PE","BUY",strike_offset=-wo)])),
    ("BOT2", "Strategy 2: Zen Curvature Overnight", "2-leg bull put spread", D([
        LegSpec("short_put","PE","SELL",strike_offset=-s2),
        LegSpec("long_put","PE","BUY",strike_offset=-w2)])),
    ("BOT6", "Strategy 6: Micro Momentum Sniper", "1-leg long CE", D([
        LegSpec("leg","CE","BUY",strike_offset=0)])),
    ("BOT7", "Strategy 7: Intraday Displacement", "1-leg long PE", D([
        LegSpec("leg","PE","BUY",strike_offset=0)])),
]

results = {}
for key, name, desc, dec in CASES:
    print("="*72); print(f"{key} — {desc}"); print("="*72)
    r = {"structure": desc}
    contracts = resolve_legs(dec, spot, vix, expiry)
    if not contracts:
        r["result"] = "CONTRACT_UNRESOLVED"; results[key]=r; print("  CONTRACT UNRESOLVED\n"); continue
    print("  contracts:")
    for c in contracts:
        ok, why = validate_quote(c["bid"], c["ask"], c["quote_timestamp"], c["side"])
        print(f"    {c['role']:11s} {c['side']:4s} {c['custom_symbol']:<28s} "
              f"sid={c['security_id']:<7s} bid={c['bid']} ask={c['ask']} lot={c['lot_size']} "
              f"{'OK' if ok else 'REJECT:'+why}")
    r["legs_resolved"] = len(contracts)

    bad = [c for c in contracts if not validate_quote(c["bid"],c["ask"],c["quote_timestamp"],c["side"])[0]]
    if bad:
        r["result"]="QUOTE_REJECTED"; results[key]=r
        print("  -> quote gate REFUSED entry (correct fail-closed behaviour)\n"); continue

    ok, why = risk_gate(risk, broker, key, contracts)
    print(f"  risk engine: {'APPROVED' if ok else 'REJECTED — '+why}")
    r["risk"] = "APPROVED" if ok else why
    if not ok:
        r["result"]="RISK_BLOCKED"; results[key]=r; print(); continue

    pos = broker.open_position(bot=key, strategy=name, underlying="NIFTY", spot=spot,
                               contracts=contracts, ledger="SHADOW",
                               meta={"verification": True, "structure": desc})
    if not pos:
        r["result"]="FILL_REFUSED"; results[key]=r; print("  -> broker refused fill\n"); continue
    print(f"  FILLED  id={pos.position_id}  credit={pos.net_credit_points:+.2f} pts  "
          f"entry costs Rs {pos.entry_costs:,.2f}")
    r["position_id"]=pos.position_id; r["entry_costs"]=round(pos.entry_costs,2)

    time.sleep(2)
    q = leg_quotes(client, [l.security_id for l in pos.legs])
    marked = broker.mark_position(pos, q, spot)
    print(f"  MARKED  unrealized Rs {marked:,.2f}   MFE {pos.mfe:,.2f}  MAE {pos.mae:,.2f}"
          if marked is not None else "  MARK FAILED (no usable quote)")
    r["marked_unrealized"]=marked

    closed = broker.close_position(pos, q, "VERIFICATION_EXIT", spot)
    if closed:
        print(f"  CLOSED  realized Rs {pos.realized_pnl:,.2f}  total costs Rs {pos.total_costs:,.2f}  "
              f"held {pos.holding_seconds():.0f}s")
        r["realized_pnl"]=pos.realized_pnl; r["total_costs"]=round(pos.total_costs,2)
        r["result"]="FULL_PATH_OK"
    else:
        print(f"  EXIT UNRESOLVED: {pos.exit_reason} (position left open, null realised P&L)")
        r["result"]=f"EXIT_UNRESOLVED:{pos.exit_reason}"
    results[key]=r; print()

path = broker.persist()
print("="*72)
print("VERIFICATION RESULT")
print("="*72)
for k, v in results.items():
    print(f"  {k}: {v.get('result')}   legs={v.get('legs_resolved')}  "
          f"realized={v.get('realized_pnl')}  costs={v.get('total_costs')}")
print(f"\n  SHADOW summary: {broker.summary('SHADOW')}")
print(f"  PAPER  summary: {broker.summary('PAPER')}   <-- must be all zeros")
print(f"  ledger: {path}")
json.dump(results, open("reports/paper_path_verification.json","w"), indent=2, default=str)
