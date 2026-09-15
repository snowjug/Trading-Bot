"""
Monitoring dashboard — FastAPI-based web interface.
Displays strategy performance, regime, risk, experiments.
"""
import json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from src.utils.logging import setup_logging

logger = setup_logging("monitoring.dashboard")

app = FastAPI(title="Indian Quant Research Agent — Dashboard", version="0.1.0")


def get_dashboard_html() -> str:
    """Generate the monitoring dashboard HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quant Research Agent — Dashboard</title>
<style>
  :root {
    --bg: #0a0e17; --surface: #131a2b; --surface2: #1a2338;
    --accent: #00d4ff; --accent2: #7c4dff; --green: #00e676;
    --red: #ff1744; --yellow: #ffd740; --text: #e0e0e0;
    --text-dim: #8892a8; --border: #1e2a40;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, var(--surface), var(--surface2));
    border-bottom: 1px solid var(--border);
    padding: 1rem 2rem;
    display: flex; justify-content: space-between; align-items: center;
  }
  .header h1 {
    font-size: 1.3rem; font-weight: 600;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .header .status {
    display: flex; gap: 1rem; align-items: center; font-size: 0.85rem;
  }
  .badge {
    padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.75rem;
    font-weight: 600; text-transform: uppercase;
  }
  .badge.safe { background: rgba(0,230,118,0.15); color: var(--green); }
  .badge.live { background: rgba(255,23,68,0.15); color: var(--red); }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1rem; padding: 1.5rem 2rem;
  }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.25rem;
    transition: border-color 0.3s;
  }
  .card:hover { border-color: var(--accent); }
  .card h3 {
    font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px;
    color: var(--text-dim); margin-bottom: 0.75rem;
  }
  .metric {
    display: flex; justify-content: space-between;
    padding: 0.4rem 0; border-bottom: 1px solid var(--border);
    font-size: 0.9rem;
  }
  .metric:last-child { border-bottom: none; }
  .metric .value { font-weight: 600; font-variant-numeric: tabular-nums; }
  .metric .value.positive { color: var(--green); }
  .metric .value.negative { color: var(--red); }
  .metric .value.neutral { color: var(--yellow); }
  table {
    width: 100%; border-collapse: collapse; font-size: 0.85rem;
  }
  th { text-align: left; color: var(--text-dim); padding: 0.5rem; border-bottom: 1px solid var(--border); }
  td { padding: 0.5rem; border-bottom: 1px solid var(--border); }
  .footer {
    text-align: center; padding: 1rem; color: var(--text-dim);
    font-size: 0.75rem; border-top: 1px solid var(--border);
  }
  #refresh-time { color: var(--accent); }
</style>
</head>
<body>
<div class="header">
  <h1>🔬 Indian Quant Research Agent</h1>
  <div class="status">
    <span class="badge safe" id="trading-status">PAPER MODE</span>
    <span id="refresh-time"></span>
  </div>
</div>

<div class="grid" id="dashboard-grid">
  <div class="card">
    <h3>📊 Portfolio Overview</h3>
    <div id="portfolio-metrics">Loading...</div>
  </div>
  <div class="card">
    <h3>🎯 Active Strategy</h3>
    <div id="strategy-info">Loading...</div>
  </div>
  <div class="card">
    <h3>🌊 Market Regime</h3>
    <div id="regime-info">Loading...</div>
  </div>
  <div class="card">
    <h3>⚠️ Risk State</h3>
    <div id="risk-info">Loading...</div>
  </div>
  <div class="card" style="grid-column: span 2;">
    <h3>🏆 Strategy Competition</h3>
    <div id="competition-table">Loading...</div>
  </div>
  <div class="card" style="grid-column: span 2;">
    <h3>🧪 Recent Experiments</h3>
    <div id="experiments-table">Loading...</div>
  </div>
</div>

<div class="footer">
  Live Trading: <strong style="color:var(--red)">DISABLED</strong> | 
  System Time: <span id="sys-time"></span>
</div>

<script>
async function refresh() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    document.getElementById('refresh-time').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    document.getElementById('sys-time').textContent = new Date().toLocaleString();
    
    // Portfolio
    const p = data.portfolio || {};
    document.getElementById('portfolio-metrics').innerHTML = 
      metric('Equity', '₹' + fmt(p.equity || 0), pnlClass(p.pnl || 0)) +
      metric('P&L', '₹' + fmt(p.pnl || 0), pnlClass(p.pnl || 0)) +
      metric('P&L %', (p.pnl_pct || 0).toFixed(2) + '%', pnlClass(p.pnl_pct || 0)) +
      metric('Positions', p.positions || 0, 'neutral');

    // Strategy
    const s = data.strategy || {};
    document.getElementById('strategy-info').innerHTML =
      metric('Name', s.name || 'None', 'neutral') +
      metric('Version', s.version || '-', 'neutral') +
      metric('Confidence', (s.confidence || 0).toFixed(2), 'neutral') +
      metric('Trades Today', s.trades_today || 0, 'neutral');

    // Regime
    const r = data.regime || {};
    document.getElementById('regime-info').innerHTML =
      metric('Trend', r.trend || '-', 'neutral') +
      metric('Volatility', r.volatility || '-', 'neutral') +
      metric('Strength', (r.strength || 0).toFixed(2), 'neutral') +
      metric('Confidence', (r.confidence || 0).toFixed(2), 'neutral');

    // Risk
    const rk = data.risk || {};
    document.getElementById('risk-info').innerHTML =
      metric('Drawdown', (rk.drawdown || 0).toFixed(2) + '%', rk.drawdown > 10 ? 'negative' : 'neutral') +
      metric('Daily P&L', '₹' + fmt(rk.daily_pnl || 0), pnlClass(rk.daily_pnl || 0)) +
      metric('Kill Switch', rk.kill_switch ? 'ACTIVE' : 'Off', rk.kill_switch ? 'negative' : 'positive');

    // Competition
    const comp = data.competition || [];
    if (comp.length) {
      let html = '<table><tr><th>#</th><th>Strategy</th><th>Score</th><th>Sharpe</th><th>CAGR%</th><th>MaxDD%</th><th>Status</th></tr>';
      comp.forEach(c => {
        html += '<tr><td>' + c.rank + '</td><td>' + c.name + '</td><td>' + c.score + '</td><td>' + c.sharpe + '</td><td>' + c.cagr + '</td><td>' + c.max_dd + '</td><td>' + c.status + '</td></tr>';
      });
      html += '</table>';
      document.getElementById('competition-table').innerHTML = html;
    }

    // Experiments
    const exps = data.experiments || [];
    if (exps.length) {
      let html = '<table><tr><th>ID</th><th>Strategy</th><th>Sharpe</th><th>CAGR%</th><th>Robust</th><th>Decision</th></tr>';
      exps.slice(-10).forEach(e => {
        html += '<tr><td>' + e.id + '</td><td>' + e.strategy + '</td><td>' + e.sharpe + '</td><td>' + e.cagr + '</td><td>' + e.robust + '</td><td>' + e.decision + '</td></tr>';
      });
      html += '</table>';
      document.getElementById('experiments-table').innerHTML = html;
    }
  } catch(e) {
    console.error('Dashboard refresh error:', e);
  }
}

function metric(label, value, cls) {
  return '<div class="metric"><span>' + label + '</span><span class="value ' + cls + '">' + value + '</span></div>';
}
function pnlClass(v) { return v > 0 ? 'positive' : v < 0 ? 'negative' : 'neutral'; }
function fmt(n) { return Number(n).toLocaleString('en-IN', {maximumFractionDigits: 0}); }

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""


# Dashboard state (populated by the research agent)
dashboard_state = {
    "portfolio": {"equity": 1000000, "pnl": 0, "pnl_pct": 0, "positions": 0},
    "strategy": {"name": "None", "version": "-", "confidence": 0, "trades_today": 0},
    "regime": {"trend": "unknown", "volatility": "unknown", "strength": 0, "confidence": 0},
    "risk": {"drawdown": 0, "daily_pnl": 0, "kill_switch": False},
    "competition": [],
    "experiments": [],
}


@app.get("/", response_class=HTMLResponse)
async def root():
    return get_dashboard_html()


@app.get("/api/status")
async def api_status():
    return dashboard_state


@app.post("/api/update")
async def api_update(data: dict):
    """Update dashboard state from the research agent."""
    dashboard_state.update(data)
    return {"status": "ok"}


def update_dashboard_state(
    portfolio: dict = None,
    strategy: dict = None,
    regime: dict = None,
    risk: dict = None,
    competition: list = None,
    experiments: list = None,
):
    """Helper to update dashboard state from Python code."""
    if portfolio:
        dashboard_state["portfolio"] = portfolio
    if strategy:
        dashboard_state["strategy"] = strategy
    if regime:
        dashboard_state["regime"] = regime
    if risk:
        dashboard_state["risk"] = risk
    if competition is not None:
        dashboard_state["competition"] = competition
    if experiments is not None:
        dashboard_state["experiments"] = experiments
