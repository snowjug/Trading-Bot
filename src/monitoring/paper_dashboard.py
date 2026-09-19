"""
Operational dashboard for the live paper session (Bots 1, 2, 6, 7, 8).

Every value is read from artefacts the running session actually writes — the paper
ledger and the heartbeat log. Nothing is computed optimistically and nothing is
invented: a field the session has not produced renders as N/A or UNAVAILABLE, and
data older than the freshness window renders as STALE rather than as live.

Separate from `dashboard.py`, which is left untouched.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.utils.logging import setup_logging

logger = setup_logging("monitoring.paper_dashboard")

app = FastAPI(title="Paper Session — Operational Dashboard", version="1.0.0")

SESSION_ROOT = Path("data/paper_session")
RESEARCH_STATE = Path("data/research_state/final_one_year_state.json")
# The DISPLAY universe, not the active set. BOT6 and BOT8 are retired in
# scripts/run_paper_session.py and are no longer evaluated, but their stored
# trades must still render in the historical view, so they stay listed here.
BOTS = ["BOT1", "BOT2", "BOT6", "BOT7", "BOT8"]
RETIRED = {"BOT6", "BOT8"}
STALE_AFTER_SEC = 120.0

HEARTBEAT_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] CYCLE (\d+)")
BOT_RE = re.compile(r"^(BOT\d): (\S+)\s*(.*?)\s*\| (.*)$")
DHAN_RE = re.compile(r"^DHAN: (\S+) ?(.*?)\s+NIFTY (\S+)\s+VIX (\S+)"
                     r"(?:\s+sessHi (\S+) sessLo (\S+) twap (\S+))?")


def session_dir(day: Optional[str] = None) -> Path:
    d = day or datetime.now().strftime("%Y-%m-%d")
    return SESSION_ROOT / d


def load_ledger(day: Optional[str] = None) -> Optional[Dict[str, Any]]:
    p = session_dir(day) / "paper_ledger.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"ledger unreadable: {exc}")
        return None


def parse_heartbeat(log: Optional[Path] = None) -> Dict[str, Any]:
    """
    Reads the LAST complete heartbeat block from the runner's log.

    The log is the only place a bot's WAIT reason is recorded, so a dashboard that
    ignored it could show "WAIT" with no explanation — which is exactly the
    ambiguity that makes "no opportunity" indistinguishable from "broken".
    """
    # Resolved at call time, not bound as a default: a default argument captures
    # SESSION_ROOT at import, so any later redirection of the session directory
    # would be silently ignored and this would keep reading the original path.
    log = log or (SESSION_ROOT / "live_run.log")
    out: Dict[str, Any] = {"cycle": None, "time": None, "bots": {},
                           "market": {}, "source": str(log), "available": False}
    if not log.exists():
        return out
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:                                          # noqa: BLE001
        return out
    # Find the last COMPLETE block. The newest heartbeat line is often still being
    # written when the dashboard reads, so its bot lines do not exist yet — taking
    # it would render every bot as UNAVAILABLE while the session is perfectly
    # healthy. A block counts as complete once its PAPER_POSITIONS footer exists.
    start = None
    for i in range(len(lines) - 1, -1, -1):
        if not HEARTBEAT_RE.match(lines[i].strip()):
            continue
        tail = [l.strip() for l in lines[i + 1:i + 12]]
        if any(l.startswith("PAPER_POSITIONS") for l in tail):
            start = i
            break
    if start is None:
        return out
    m = HEARTBEAT_RE.match(lines[start].strip())
    out["time"], out["cycle"] = m.group(1), int(m.group(2))
    out["available"] = True
    for ln in lines[start + 1:start + 12]:
        ln = ln.strip()
        d = DHAN_RE.match(ln)
        if d:
            out["market"] = {
                "status": d.group(1), "stamp": d.group(2).strip() or None,
                "nifty": d.group(3), "vix": d.group(4),
                "session_high": d.group(5), "session_low": d.group(6),
                "twap": d.group(7),
            }
            continue
        b = BOT_RE.match(ln)
        if b:
            out["bots"][b.group(1)] = {"status": b.group(2),
                                       "detail": b.group(3) or None,
                                       "reason": b.group(4)}
    return out


def position_view(p: Dict[str, Any]) -> Dict[str, Any]:
    legs = p.get("legs") or []
    return {
        "position_id": p.get("position_id"), "bot": p.get("bot"),
        "strategy": p.get("strategy"), "status": p.get("status"),
        "entry_time": p.get("entry_time"), "exit_time": p.get("exit_time"),
        "entry_spot": p.get("entry_spot"), "exit_spot": p.get("exit_spot"),
        "realized_pnl": p.get("realized_pnl"), "unrealized_pnl": p.get("unrealized_pnl"),
        "mae": p.get("mae"), "mfe": p.get("mfe"),
        "holding_seconds": p.get("holding_seconds"),
        "entry_costs": p.get("entry_costs"), "exit_costs": p.get("exit_costs"),
        "total_costs": p.get("total_costs"), "exit_reason": p.get("exit_reason"),
        "net_credit_points": p.get("net_credit_points"),
        "stop_target": {"stop_pnl": (p.get("meta") or {}).get("stop_level"),
                        "target_pnl": (p.get("meta") or {}).get("target_level")},
        "meta": p.get("meta") or {},
        "legs": [{
            "role": l.get("role"), "symbol": l.get("custom_symbol"),
            "security_id": l.get("security_id"), "strike": l.get("strike"),
            "expiry": l.get("expiry"), "option_type": l.get("option_type"),
            "side": l.get("side"), "qty": l.get("qty"),
            "entry_bid": l.get("entry_bid"), "entry_ask": l.get("entry_ask"),
            "entry_fill": l.get("entry_fill"), "slippage": l.get("slippage"),
            "current_bid": l.get("current_bid"), "current_ask": l.get("current_ask"),
            "current_mark": l.get("current_mark"),
            "exit_bid": l.get("exit_bid"), "exit_ask": l.get("exit_ask"),
            "exit_fill": l.get("exit_fill"),
            "spread": (round(l["entry_ask"] - l["entry_bid"], 2)
                       if l.get("entry_ask") is not None and l.get("entry_bid") is not None
                       else None),
        } for l in legs],
    }


@app.get("/api/state")
def api_state(day: Optional[str] = None) -> JSONResponse:
    """Live operational state: one entry per bot, plus market and totals."""
    led = load_ledger(day)
    hb = parse_heartbeat()
    now = datetime.now()

    age = None
    if hb.get("time"):
        try:
            t = datetime.strptime(hb["time"], "%H:%M:%S").time()
            age = (now - datetime.combine(now.date(), t)).total_seconds()
        except ValueError:
            age = None
    live = age is not None and 0 <= age <= STALE_AFTER_SEC

    paper = (led or {}).get("PAPER", {})
    openp = paper.get("open", []) or []
    closed = paper.get("closed", []) or []

    bots = {}
    for b in BOTS:
        h = hb["bots"].get(b, {})
        mine_open = [p for p in openp if p.get("bot") == b]
        mine_closed = [p for p in closed if p.get("bot") == b]
        bots[b] = {
            "status": h.get("status", "UNAVAILABLE"),
            "wait_reason": h.get("reason", "UNAVAILABLE"),
            "last_evaluation": hb.get("time") or "N/A",
            "evaluation_age_sec": round(age, 1) if age is not None else None,
            "data_state": "LIVE" if live else ("STALE" if age is not None else "UNAVAILABLE"),
            "open_position": position_view(mine_open[0]) if mine_open else None,
            "trades_today": len(mine_closed),
            "realized_pnl": round(sum(p.get("realized_pnl") or 0 for p in mine_closed), 2),
            "unrealized_pnl": round(sum(p.get("unrealized_pnl") or 0 for p in mine_open), 2),
        }
        if b == "BOT8":
            meta = (mine_open[0].get("meta") if mine_open else {}) or {}
            bots[b]["structure"] = {
                "state": meta.get("state", "N/A"), "setup_type": meta.get("setup_type", "N/A"),
                "trend": meta.get("trend", "N/A"), "daily_bias": meta.get("daily_bias", "N/A"),
                "swing_high": meta.get("swing_high"), "swing_low": meta.get("swing_low"),
                "support": meta.get("support"), "resistance": meta.get("resistance"),
                "breakout_state": meta.get("breakout_state", "N/A"),
                "retest_state": meta.get("retest_state", "N/A"),
                "entry": meta.get("entry_level"), "stop": meta.get("stop_level"),
                "target": meta.get("target_level"), "risk_reward": meta.get("risk_reward"),
            }

    return JSONResponse({
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "session_live": live,
        "cycle": hb.get("cycle"),
        "heartbeat_available": hb.get("available", False),
        "market": hb.get("market") or {"status": "UNAVAILABLE"},
        "bots": bots,
        "totals": paper.get("summary") or {"note": "no ledger written yet"},
        "shadow_totals": (led or {}).get("SHADOW", {}).get("summary") or {},
        "errors": (led or {}).get("errors", [])[-20:],
        "rejections": (led or {}).get("rejections", [])[-20:],
    })


@app.get("/api/research_status")
def api_research_status() -> JSONResponse:
    """
    The standing research verdict, read verbatim from the state file the study
    writes. It exists so the dashboard cannot be mistaken for evidence that these
    bots are worth trading: no strategy in this repository has passed a
    development -> validation -> holdout gate, and the operator should see that on
    the same screen as the live marks. Nothing here is computed or inferred.
    """
    if not RESEARCH_STATE.exists():
        return JSONResponse({"available": False,
                             "reason": f"no state file at {RESEARCH_STATE}"})
    try:
        with RESEARCH_STATE.open(encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError) as exc:
        return JSONResponse({"available": False, "reason": f"unreadable: {exc}"})
    return JSONResponse({
        "available": True,
        "run": st.get("run"), "closed": st.get("closed"),
        "outcome": st.get("outcome"),
        "promoted": st.get("promoted", []),
        "live_trading_enabled": st.get("live_trading_enabled"),
        "holdout": (st.get("splits") or {}).get("holdout"),
        "money_result": st.get("money_result", {}),
        "retired_bots": st.get("retired_bots", {}),
    })


@app.get("/api/historical")
def api_historical(start: Optional[str] = None, end: Optional[str] = None,
                   bot: Optional[str] = None) -> JSONResponse:
    """
    Real stored sessions, filtered. Absent data is reported as absent.
    """
    if not SESSION_ROOT.exists():
        return JSONResponse({"available": False, "reason": "no session directory",
                             "sessions": [], "trades": []})
    days = sorted(d.name for d in SESSION_ROOT.iterdir()
                  if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name))
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]

    trades, sessions = [], []
    for d in days:
        led = load_ledger(d)
        if not led:
            sessions.append({"date": d, "status": "UNREADABLE"})
            continue
        paper = led.get("PAPER", {})
        closed = [p for p in (paper.get("closed") or [])
                  if not bot or p.get("bot") == bot]
        openp = [p for p in (paper.get("open") or []) if not bot or p.get("bot") == bot]
        for p in closed:
            trades.append({"date": d, **position_view(p)})
        pnl = [p.get("realized_pnl") or 0 for p in closed]
        wins = [x for x in pnl if x > 0]
        losses = [x for x in pnl if x <= 0]
        eq, peak, dd = 0.0, 0.0, 0.0
        for x in pnl:
            eq += x
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        sessions.append({
            "date": d, "status": "OK",
            "trades": len(closed), "open_at_end": len(openp),
            "gross_pnl": round(sum(pnl) + sum(p.get("total_costs") or 0 for p in closed), 2),
            "costs": round(sum(p.get("total_costs") or 0 for p in closed), 2),
            "net_pnl": round(sum(pnl), 2),
            "win_rate": round(len(wins) / len(pnl) * 100, 1) if pnl else None,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "max_drawdown": round(abs(dd), 2),
        })

    equity, run, peak, ddmax = [], 0.0, 0.0, 0.0
    for s in sessions:
        if s.get("status") == "OK":
            run += s.get("net_pnl") or 0.0
            peak = max(peak, run)
            ddmax = max(ddmax, peak - run)
            equity.append({"date": s["date"], "equity": round(run, 2)})

    # Analytics over the filtered range. Every figure comes from stored trades;
    # a quantity the ledger does not carry is reported as null, never inferred.
    ok = [s for s in sessions if s.get("status") == "OK"]
    dayp = [s.get("net_pnl") or 0.0 for s in ok]
    allp = [t.get("realized_pnl") or 0.0 for t in trades]
    wins = [x for x in allp if x > 0]
    losses = [x for x in allp if x <= 0]
    deployed = sum(abs(t.get("meta", {}).get("capital_at_risk") or 0.0) for t in trades)
    streak = mx = 0
    for x in dayp:
        if x < 0:
            streak += 1; mx = max(mx, streak)
        elif x > 0:
            streak = 0

    def pct_days(thr: float):
        """Share of traded days at or beyond a threshold, as a % of account.
        Requires PAPER_ACCOUNT_CAPITAL; without it the question is unanswerable."""
        acct = os.environ.get("PAPER_ACCOUNT_CAPITAL")
        if not acct:
            return None
        try:
            a = float(acct)
        except ValueError:
            return None
        if a <= 0 or not dayp:
            return None
        return round(sum(1 for x in dayp if x / a * 100 >= thr) / len(dayp) * 100, 1)

    return JSONResponse({
        "available": bool(days), "filter": {"start": start, "end": end, "bot": bot},
        "sessions": sessions, "equity_curve": equity, "trades": trades,
        "totals": {
            "sessions": len(sessions),
            "trades": sum(s.get("trades") or 0 for s in sessions),
            "net_pnl": round(sum(s.get("net_pnl") or 0 for s in sessions), 2),
            "gross_pnl": round(sum(s.get("gross_pnl") or 0 for s in sessions), 2),
            "costs": round(sum(s.get("costs") or 0 for s in sessions), 2),
            "capital_deployed": round(deployed, 2) if deployed else None,
            "return_on_deployed_pct": (round(sum(allp) / deployed * 100, 2)
                                       if deployed else None),
            "win_rate": round(len(wins) / len(allp) * 100, 1) if allp else None,
            "expectancy": round(sum(allp) / len(allp), 2) if allp else None,
            "profit_factor": (round(sum(wins) / abs(sum(losses)), 3)
                              if losses and sum(losses) != 0 else None),
            "max_drawdown": round(ddmax, 2),
            "profitable_days": sum(1 for x in dayp if x > 0),
            "losing_days": sum(1 for x in dayp if x < 0),
            "max_losing_day_streak": mx,
            "best_day": round(max(dayp), 2) if dayp else None,
            "worst_day": round(min(dayp), 2) if dayp else None,
            "pct_days_ge_1": pct_days(1.0),
            "pct_days_ge_2": pct_days(2.0),
        },
    })


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html><html><head><meta charset="utf-8">
<title>Paper Session</title>
<style>
:root{--bg:#0b0e13;--fg:#e6edf3;--dim:#8b949e;--line:#222b36;--ok:#3fb950;--bad:#f85149;--warn:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;
gap:18px;align-items:baseline;flex-wrap:wrap}
h1{font-size:15px;margin:0;font-weight:600}
.pill{padding:2px 8px;border-radius:10px;font-size:11px;border:1px solid var(--line)}
.live{color:var(--ok);border-color:var(--ok)}.stale{color:var(--bad);border-color:var(--bad)}
main{padding:16px;display:grid;gap:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}
.card{border:1px solid var(--line);border-radius:8px;padding:12px;background:#11151c}
.card h2{font-size:13px;margin:0 0 8px;display:flex;justify-content:space-between}
.k{color:var(--dim)}.row{display:flex;justify-content:space-between;gap:10px;padding:1px 0}
.reason{color:var(--warn);font-size:11px;margin-top:6px;word-break:break-word}
table{width:100%;border-collapse:collapse;font-size:11px}
th,td{text-align:left;padding:4px 6px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:500}
.pos{color:var(--ok)}.neg{color:var(--bad)}
button{background:#1b2430;color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:5px 10px;cursor:pointer;font:inherit}
input{background:#0d1117;color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:4px 6px;font:inherit}
</style></head><body>
<header><h1>PAPER SESSION</h1><span id="hb" class="pill">connecting…</span>
<span id="mkt" class="k"></span>
<button onclick="loadHist()">HISTORICAL</button>
<input id="hstart" placeholder="start YYYY-MM-DD" size="14">
<input id="hend" placeholder="end YYYY-MM-DD" size="14">
<input id="hbot" placeholder="bot e.g. BOT8" size="9"></header>
<main><div class="grid" id="bots"></div>
<div class="card"><h2>TOTALS (PAPER)</h2><div id="tot"></div></div>
<div class="card"><h2>REJECTIONS / ERRORS</h2><div id="err"></div></div>
<div class="card" id="rscard" style="display:none"><h2>RESEARCH VERDICT</h2>
<div id="rs"></div></div>
<div class="card" id="histcard" style="display:none"><h2>HISTORICAL</h2>
<div id="hist"></div></div></main>
<script>
const money=v=>v==null?'N/A':(v<0?'-':'')+'₹'+Math.abs(v).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const cls=v=>v==null?'':(v>0?'pos':(v<0?'neg':''));
const row=(k,v,c)=>`<div class="row"><span class="k">${k}</span><span class="${c||''}">${v}</span></div>`;
async function tick(){
 const r=await fetch('/api/state'); const s=await r.json();
 const hb=document.getElementById('hb');
 hb.textContent=(s.session_live?'LIVE':'STALE')+' · cycle '+(s.cycle??'N/A')+' · '+(s.bots.BOT1?.last_evaluation??'N/A');
 hb.className='pill '+(s.session_live?'live':'stale');
 const m=s.market||{};
 document.getElementById('mkt').textContent='NIFTY '+(m.nifty??'N/A')+'  VIX '+(m.vix??'N/A')
  +'  hi '+(m.session_high??'N/A')+'  lo '+(m.session_low??'N/A')+'  twap '+(m.twap??'N/A');
 document.getElementById('bots').innerHTML=Object.entries(s.bots).map(([k,b])=>{
  const p=b.open_position; let h=`<div class="card"><h2>${k}<span class="${b.data_state==='LIVE'?'pos':'neg'}">${b.status}</span></h2>`;
  h+=row('data',b.data_state+' ('+(b.evaluation_age_sec??'N/A')+'s)');
  h+=row('trades today',b.trades_today);
  h+=row('realized',money(b.realized_pnl),cls(b.realized_pnl));
  h+=row('unrealized',money(b.unrealized_pnl),cls(b.unrealized_pnl));
  if(b.structure){const st=b.structure;
   h+=row('structure',st.state+' / '+st.setup_type);
   h+=row('bias',st.daily_bias+' · '+st.trend);
   h+=row('swing hi/lo',(st.swing_high??'N/A')+' / '+(st.swing_low??'N/A'));
   h+=row('break/retest',st.breakout_state+' / '+st.retest_state);
   h+=row('entry/stop/tgt',(st.entry??'N/A')+' / '+(st.stop??'N/A')+' / '+(st.target??'N/A'));
   h+=row('R:R',st.risk_reward??'N/A');}
  if(p){h+=`<table><tr><th>leg</th><th>side</th><th>fill</th><th>bid</th><th>ask</th><th>mark</th></tr>`
   +p.legs.map(l=>`<tr><td>${l.symbol||l.role}</td><td>${l.side}</td><td>${l.entry_fill}</td>
   <td>${l.current_bid??'N/A'}</td><td>${l.current_ask??'N/A'}</td><td>${l.current_mark??'N/A'}</td></tr>`).join('')+'</table>';
   h+=row('MFE / MAE',money(p.mfe)+' / '+money(p.mae));
   h+=row('costs',money(p.total_costs));
   h+=row('held',(p.holding_seconds??'N/A')+'s');}
  h+=`<div class="reason">${b.wait_reason}</div></div>`; return h;}).join('');
 const t=s.totals||{};
 document.getElementById('tot').innerHTML=Object.entries(t).map(([k,v])=>
   row(k,typeof v==='number'&&/pnl|cost|drawdown/i.test(k)?money(v):v,cls(/pnl/i.test(k)?v:null))).join('');
 const errs=(s.errors||[]).concat(s.rejections||[]);
 document.getElementById('err').innerHTML=errs.length?errs.slice(-12).map(e=>
   `<div class="row"><span class="k">${e.time||''} ${e.bot||''}</span><span>${e.error||e.reason||''}</span></div>`).join('')
   :'<span class="k">none</span>';
}
async function loadHist(){
 const q=new URLSearchParams();
 ['hstart','hend','hbot'].forEach((id,i)=>{const v=document.getElementById(id).value.trim();
  if(v)q.set(['start','end','bot'][i],v);});
 const r=await fetch('/api/historical?'+q); const h=await r.json();
 document.getElementById('histcard').style.display='block';
 if(!h.available){document.getElementById('hist').innerHTML='<span class="k">UNAVAILABLE — no stored sessions</span>';return;}
 document.getElementById('hist').innerHTML=
  `<table><tr><th>date</th><th>trades</th><th>gross</th><th>costs</th><th>net</th>
   <th>win%</th><th>avg win</th><th>avg loss</th><th>maxDD</th></tr>`+
  h.sessions.map(s=>s.status!=='OK'?`<tr><td>${s.date}</td><td colspan="8">${s.status}</td></tr>`:
   `<tr><td>${s.date}</td><td>${s.trades}</td><td>${money(s.gross_pnl)}</td><td>${money(s.costs)}</td>
    <td class="${cls(s.net_pnl)}">${money(s.net_pnl)}</td><td>${s.win_rate??'N/A'}</td>
    <td>${money(s.avg_win)}</td><td>${money(s.avg_loss)}</td><td>${money(s.max_drawdown)}</td></tr>`).join('')
  +`</table><div class="row"><span class="k">totals</span><span>${h.totals.trades} trades · net ${money(h.totals.net_pnl)} · costs ${money(h.totals.costs)}</span></div>`
  +(h.trades.length?`<table style="margin-top:8px"><tr><th>date</th><th>bot</th><th>entry</th><th>exit</th>
    <th>reason</th><th>net</th><th>MFE</th><th>MAE</th></tr>`+h.trades.map(t=>
    `<tr><td>${t.date}</td><td>${t.bot}</td><td>${t.entry_time??''}</td><td>${t.exit_time??''}</td>
     <td>${t.exit_reason??''}</td><td class="${cls(t.realized_pnl)}">${money(t.realized_pnl)}</td>
     <td>${money(t.mfe)}</td><td>${money(t.mae)}</td></tr>`).join('')+'</table>':'');
}
async function research(){
 const r=await fetch('/api/research_status'); const j=await r.json();
 const c=document.getElementById('rscard'), t=document.getElementById('rs');
 c.style.display='block';
 if(!j.available){t.innerHTML='<span class="k">UNAVAILABLE \u2014 '+(j.reason||'')+'</span>';return;}
 const prom=(j.promoted&&j.promoted.length)?j.promoted.join(', '):'NONE';
 const mr=j.money_result||{};
 const row=(k,lbl)=>{const v=mr[k]; if(!v) return '';
   if(v.net===null||v.net===undefined) return `<tr><td>${lbl}</td><td colspan="3">${v.note||'not executable'}</td></tr>`;
   return `<tr><td>${lbl}</td><td class="${cls(v.net)}">${money(v.net)}</td><td>${v.return_pct}%</td><td>${v.profitable_days_pct}% of sessions</td></tr>`;};
 t.innerHTML=`<div class="row"><span class="k">run</span><span>${j.run||'N/A'} (closed ${j.closed||'N/A'})</span></div>`
  +`<div class="row"><span class="k">outcome</span><span>${j.outcome||'N/A'}</span></div>`
  +`<div class="row"><span class="k">strategies promoted</span><span class="${prom==='NONE'?'neg':'pos'}">${prom}</span></div>`
  +`<div class="row"><span class="k">LIVE_TRADING_ENABLED</span><span>${j.live_trading_enabled}</span></div>`
  +`<div class="row"><span class="k">holdout</span><span>${(j.holdout||[]).join(' \u2192 ')}</span></div>`
  +`<table style="margin-top:8px"><tr><th>account</th><th>net</th><th>return</th><th>profitable days</th></tr>`
  +row('20000','\u20b920,000')+row('50000','\u20b950,000')+row('100000','\u20b91,00,000')+`</table>`
  +`<div class="row" style="margin-top:6px"><span class="k">retired</span><span>`
  +Object.keys(j.retired_bots||{}).join(', ')+`</span></div>`;
}
research(); tick(); setInterval(tick,5000);
</script></body></html>"""


@app.get("/api/health")
def health() -> JSONResponse:
    lock = SESSION_ROOT / "session.lock"
    return JSONResponse({
        "ledger_present": (session_dir() / "paper_ledger.json").exists(),
        "heartbeat_present": (SESSION_ROOT / "live_run.log").exists(),
        "session_lock": lock.read_text(encoding="utf-8").strip() if lock.exists() else None,
    })
