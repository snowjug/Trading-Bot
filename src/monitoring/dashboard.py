"""
Monitoring dashboard — FastAPI-based real-time quantitative web interface.
Displays live multi-bot execution, real-time PnL, active/closed trades, and historical charts.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from src.utils.logging import setup_logging

logger = setup_logging("monitoring.dashboard")

app = FastAPI(title="Apex Quant — Live Performance Dashboard", version="1.0.0")

# Mount charts directory if it exists
charts_dir = Path("reports/charts")
if charts_dir.exists():
    app.mount("/charts", StaticFiles(directory=str(charts_dir)), name="charts")


def get_dashboard_html() -> str:
    """Generate the high-contrast institutional trading dashboard HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ Apex Quant — Live Performance & Telemetry</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #07090e;
    --surface: #0e131f;
    --surface2: #161e31;
    --border: #1e2942;
    --accent: #38bdf8;
    --accent-glow: rgba(56, 189, 248, 0.15);
    --purple: #a855f7;
    --green: #22c55e;
    --green-bg: rgba(34, 197, 94, 0.12);
    --red: #ef4444;
    --red-bg: rgba(239, 68, 68, 0.12);
    --yellow: #eab308;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100vh; display: flex; flex-direction: column;
  }
  .header {
    background: linear-gradient(180deg, #111726 0%, #0c101a 100%);
    border-bottom: 1px solid var(--border);
    padding: 1.1rem 2.5rem;
    display: flex; justify-content: space-between; align-items: center;
  }
  .brand { display: flex; align-items: center; gap: 0.8rem; }
  .brand h1 {
    font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em;
    background: linear-gradient(90deg, #38bdf8, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .tagline { font-size: 0.8rem; color: var(--text-muted); }
  .header-actions { display: flex; gap: 1rem; align-items: center; }
  .badge {
    padding: 0.35rem 0.85rem; border-radius: 9999px; font-size: 0.75rem;
    font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
  }
  .badge.paper { background: var(--green-bg); color: var(--green); border: 1px solid rgba(34,197,94,0.3); }
  .badge.live { background: var(--red-bg); color: var(--red); border: 1px solid rgba(239,68,68,0.3); }
  .pulse-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: var(--green); margin-right: 6px;
    box-shadow: 0 0 10px var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }

  .container { padding: 2rem 2.5rem; flex: 1; max-width: 1600px; margin: 0 auto; width: 100%; }

  /* Top Stat Banners */
  .stats-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1.25rem; margin-bottom: 2rem;
  }
  .stat-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1.25rem 1.5rem;
    position: relative; overflow: hidden;
  }
  .stat-card::after {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--accent), var(--purple));
    opacity: 0.7;
  }
  .stat-title { font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); margin-bottom: 0.4rem; }
  .stat-value { font-family: 'JetBrains Mono', monospace; font-size: 1.65rem; font-weight: 700; }
  .stat-sub { font-size: 0.8rem; margin-top: 0.35rem; color: var(--text-muted); }
  .green { color: var(--green); }
  .red { color: var(--red); }
  .accent { color: var(--accent); }

  /* Strategy Cards Grid */
  .section-title { font-size: 1.05rem; font-weight: 700; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
  .bots-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
    gap: 1.25rem; margin-bottom: 2rem;
  }
  .bot-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1.25rem; transition: transform 0.2s, border-color 0.2s;
  }
  .bot-card:hover { border-color: var(--accent); transform: translateY(-2px); }
  .bot-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.8rem; }
  .bot-name { font-size: 0.95rem; font-weight: 700; color: #fff; }
  .bot-status {
    font-size: 0.68rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 6px;
    background: var(--surface2); color: var(--accent); letter-spacing: 0.04em;
  }
  .bot-status.active { background: var(--green-bg); color: var(--green); }
  .bot-status.stopped { background: rgba(148, 163, 184, 0.15); color: var(--text-muted); }
  .bot-meta { font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.8rem; }
  .bot-pnl-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.6rem 0; border-top: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;
  }

  /* Tables */
  .table-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1.25rem; margin-bottom: 2rem; overflow-x: auto;
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.86rem; text-align: left; }
  th { padding: 0.75rem 1rem; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
  td { padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.04); }
  tr:last-child td { border-bottom: none; }
  .mono { font-family: 'JetBrains Mono', monospace; }

  /* Quick Navigation to Charts */
  .charts-bar {
    display: flex; gap: 0.8rem; flex-wrap: wrap; margin-bottom: 2rem;
  }
  .chart-btn {
    padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.82rem; font-weight: 600;
    text-decoration: none; color: var(--text); background: var(--surface2);
    border: 1px solid var(--border); transition: all 0.2s; display: inline-flex; align-items: center; gap: 0.4rem;
  }
  .chart-btn:hover { background: var(--accent); color: #000; border-color: var(--accent); }

  .footer {
    border-top: 1px solid var(--border); padding: 1.2rem 2.5rem;
    font-size: 0.78rem; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center;
  }
</style>
</head>
<body>

<div class="header">
  <div class="brand">
    <h1>⚡ APEX QUANT</h1>
    <span class="tagline">Indian Autonomous F&O Algorithmic Telemetry</span>
  </div>
  <div class="header-actions">
    <span class="badge paper"><span class="pulse-dot"></span><span id="sys-mode">PAPER MODE ACTIVE</span></span>
    <span style="font-size:0.8rem; color:var(--text-muted); font-family:'JetBrains Mono';" id="clock">--:--:--</span>
  </div>
</div>

<div class="container">
  <!-- Top Stat Cards -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-title">Total Portfolio Equity</div>
      <div class="stat-value mono" id="equity-val">₹5,00,000</div>
      <div class="stat-sub" id="strat-count-sub">Allocated Across Active Strategies</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Net Realized P&L</div>
      <div class="stat-value mono green" id="net-pnl-val">+₹0.00</div>
      <div class="stat-sub" id="net-pnl-sub">All Statutory Charges Deducted</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Gross Realized Profit</div>
      <div class="stat-value mono" id="gross-pnl-val">₹0.00</div>
      <div class="stat-sub">Before Taxes & Exchange Levies</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Statutory Taxes & Brokerage</div>
      <div class="stat-value mono red" id="charges-val">-₹0.00</div>
      <div class="stat-sub">STT + GST + ₹20/order Fee Cap</div>
    </div>
  </div>

  <!-- Interactive Charts Bar -->
  <div class="section-title">📊 Interactive Quant Visualizations</div>
  <div class="charts-bar">
    <a href="/charts/equity_curves.html" target="_blank" class="chart-btn">📈 Equity Curves & Drawdown</a>
    <a href="/charts/drawdowns.html" target="_blank" class="chart-btn">🌊 Historical Drawdown Profiles</a>
    <a href="/charts/correlation_matrix.html" target="_blank" class="chart-btn">🔥 Return Correlation Matrix</a>
    <a href="/charts/portfolio_allocation.html" target="_blank" class="chart-btn">🥧 Capital Allocation</a>
    <a href="/charts/return_distribution.html" target="_blank" class="chart-btn">📊 Return Distribution & Skew</a>
  </div>

  <!-- Active Bots Grid -->
  <div class="section-title" id="bots-section-title">🤖 Production Algorithmic Strategies</div>
  <div class="bots-grid" id="bots-container">
    <!-- Populated dynamically via Javascript -->
  </div>

  <!-- Open Positions Table -->
  <div class="section-title">⚡ Active Open Positions (Real-time Mark-to-Market)</div>
  <div class="table-card" style="margin-bottom: 2rem;">
    <table>
      <thead>
        <tr>
          <th>Strategy</th>
          <th>Contract</th>
          <th>Security ID</th>
          <th>Side</th>
          <th>Qty</th>
          <th>Entry Fill</th>
          <th>Current Bid</th>
          <th>Current Ask</th>
          <th>Unrealized P&L</th>
          <th>Target</th>
          <th>Stop</th>
          <th>Valuation</th>
        </tr>
      </thead>
      <tbody id="open-positions-tbody">
        <tr><td colspan="12" style="text-align:center; color:var(--text-muted);">No active open positions. Standing by for signals.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Closed Trades Table -->
  <div class="section-title">📜 Today's Execution Ledger & Settled Positions</div>
  <div class="table-card">
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Strategy</th>
          <th>Contract / Structure</th>
          <th>Exit Reason</th>
          <th>Gross PnL</th>
          <th>Charges (STT/GST)</th>
          <th>Net PnL</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="trades-tbody">
        <tr><td colspan="8" style="text-align:center; color:var(--text-muted);">Loading live trading events...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="footer">
  <div>Safety Gate: <span style="color:var(--green); font-weight:600;">LIVE_TRADING_ENABLED=False</span> (Protected Synthetic Broker)</div>
  <div>Broker Connectivity: <span class="mono" id="dhan-status">DhanHQ Official Data API Active</span></div>
</div>

<script>
function fmt(num) {
  if (num === undefined || num === null || isNaN(num)) return "0.00";
  return Number(num).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function updateDashboard() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    document.getElementById('clock').innerText = new Date().toLocaleTimeString('en-GB');

    // Portfolio Equity & Totals
    const totalCap = data.total_capital_deployed || 500000;
    const settlement = data.final_settlement || {};
    const netPnl = settlement.total_net_realized_pnl || 0;
    const grossPnl = settlement.total_realized_gross || 0;
    const friction = settlement.total_statutory_friction || 0;

    document.getElementById('equity-val').innerText = '₹' + fmt(totalCap + netPnl);
    
    const netEl = document.getElementById('net-pnl-val');
    netEl.innerText = (netPnl >= 0 ? '+' : '') + '₹' + fmt(netPnl);
    netEl.className = 'stat-value mono ' + (netPnl >= 0 ? 'green' : 'red');

    document.getElementById('gross-pnl-val').innerText = '₹' + fmt(grossPnl);
    document.getElementById('charges-val').innerText = '-₹' + fmt(friction);

    // Dynamic Strategy Count
    const botStates = data.bot_states || {};
    const botCount = Object.keys(botStates).length || 6;
    const stratSub = document.getElementById('strat-count-sub');
    if (stratSub) stratSub.innerText = `Allocated Across ${botCount} Strategies`;
    const botsSecTitle = document.getElementById('bots-section-title');
    if (botsSecTitle) botsSecTitle.innerText = `🤖 Production Algorithmic Strategies (${botCount} Bots)`;

    // Render Bots
    const botsContainer = document.getElementById('bots-container');
    let botsHtml = '';
    const allTrades = [];
    const openPositions = [];

    for (const [name, b] of Object.entries(botStates)) {
      const active = b.active_trade;
      const closed = b.closed_trades || [];
      const isActUnavailable = (active && (active.valuation_status === 'DATA_UNAVAILABLE' || active.unrealized_pnl === null));
      const botNetPnl = b.net_pnl || 0;
      const isProfitable = botNetPnl >= 0;

      let statusBadgeClass = 'bot-status';
      if (b.status && b.status.includes('IN_POSITION')) statusBadgeClass += ' active';
      else if (b.status && b.status.includes('SQUARED_OFF')) statusBadgeClass += ' stopped';

      let pnlSnippet = '';
      if (isActUnavailable && closed.length === 0) {
        pnlSnippet = '<span style="color:#f59e0b; font-weight:700; font-size:0.85rem;">DATA_UNAVAILABLE</span>';
      } else if (isActUnavailable && closed.length > 0) {
        pnlSnippet = `<span class="${isProfitable ? 'green' : 'red'}" style="font-weight:700;">${isProfitable ? '+' : ''}₹${fmt(botNetPnl)}</span> <span style="font-size:0.7rem; color:#f59e0b;">(Settled)</span>`;
      } else {
        pnlSnippet = `<span class="${isProfitable ? 'green' : 'red'}" style="font-weight:700;">${isProfitable ? '+' : ''}₹${fmt(botNetPnl)}</span>`;
      }

      botsHtml += `
        <div class="bot-card">
          <div class="bot-header">
            <div class="bot-name">${name}</div>
            <span class="${statusBadgeClass}">${b.status || 'STANDBY'}</span>
          </div>
          <div class="bot-meta">
            Allocated: ₹${fmt(b.allocated_capital)}<br>
            Current Capital: ₹${fmt(b.current_capital || b.allocated_capital)}
          </div>
          <div class="bot-pnl-row">
            <span style="color:var(--text-muted); font-size:0.8rem;">Session P&L</span>
            ${pnlSnippet}
          </div>
        </div>
      `;

      if (active) {
        openPositions.push({ bot: name, ...active });
      }

      if (closed.length > 0) {
        closed.forEach(t => {
          allTrades.push({ bot: name, ...t });
        });
      }
    }
    botsContainer.innerHTML = botsHtml;

    // Render Open Positions Table
    const openTbody = document.getElementById('open-positions-tbody');
    if (openPositions.length === 0) {
      openTbody.innerHTML = '<tr><td colspan="12" style="text-align:center; color:var(--text-muted);">No active open positions. Monitoring market opportunities...</td></tr>';
    } else {
      let openHtml = '';
      openPositions.forEach(p => {
        const isUnavailable = (p.valuation_status === 'DATA_UNAVAILABLE' || p.unrealized_pnl === null || p.unrealized_pnl === undefined);
        const pnlDisplay = isUnavailable ? '<span style="color:#f59e0b; font-weight:700;">DATA_UNAVAILABLE</span>' : `<span class="mono ${p.unrealized_pnl >= 0 ? 'green' : 'red'}" style="font-weight:700;">${p.unrealized_pnl >= 0 ? '+' : ''}₹${fmt(p.unrealized_pnl)}</span>`;
        const badgeBg = isUnavailable ? 'rgba(245,158,11,0.15)' : 'rgba(0,210,106,0.15)';
        const badgeColor = isUnavailable ? '#f59e0b' : 'var(--green)';
        const curBid = (p.current_bid !== undefined && p.current_bid !== null) ? '₹' + fmt(p.current_bid) : '--';
        const curAsk = (p.current_ask !== undefined && p.current_ask !== null) ? '₹' + fmt(p.current_ask) : '--';
        openHtml += `
          <tr>
            <td style="font-weight:600;">${p.bot}</td>
            <td class="mono" style="color:var(--accent);">${p.contract || '--'}</td>
            <td class="mono">${p.security_id || '--'}</td>
            <td style="font-weight:600;">${p.side || 'BUY'}</td>
            <td class="mono">${p.qty || p.lots || '--'}</td>
            <td class="mono">₹${fmt(p.entry_fill || p.entry_premium)}</td>
            <td class="mono green">${curBid}</td>
            <td class="mono red">${curAsk}</td>
            <td>${pnlDisplay}</td>
            <td class="mono">${p.target_premium ? '₹' + fmt(p.target_premium) : '--'}</td>
            <td class="mono">${p.stop_premium ? '₹' + fmt(p.stop_premium) : '--'}</td>
            <td><span style="font-size:0.75rem; background:${badgeBg}; color:${badgeColor}; padding:0.2rem 0.5rem; border-radius:4px; font-weight:600;">${p.valuation_status || 'LIVE_QUOTE'}</span></td>
          </tr>
        `;
      });
      openTbody.innerHTML = openHtml;
    }

    // Render Trades Table
    const tbody = document.getElementById('trades-tbody');
    if (allTrades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No closed trades yet in this session.</td></tr>';
    } else {
      let tableHtml = '';
      allTrades.forEach(t => {
        const net = t.net_pnl || 0;
        const gross = t.gross_pnl || 0;
        const fric = t.statutory_friction || 0;
        tableHtml += `
          <tr>
            <td class="mono">${t.exit_time || t.entry_time || '--'}</td>
            <td style="font-weight:600;">${t.bot}</td>
            <td class="mono" style="color:var(--accent);">${t.contract || '--'}</td>
            <td><span style="font-size:0.75rem; background:rgba(255,255,255,0.06); padding:0.2rem 0.5rem; border-radius:4px;">${t.exit_reason || 'CLOSED'}</span></td>
            <td class="mono ${gross >= 0 ? 'green' : 'red'}">+₹${fmt(gross)}</td>
            <td class="mono red">-₹${fmt(fric)}</td>
            <td class="mono ${net >= 0 ? 'green' : 'red'}" style="font-weight:700;">${net >= 0 ? '+' : ''}₹${fmt(net)}</td>
            <td><span style="color:var(--green); font-weight:600; font-size:0.75rem;">✔ SETTLED</span></td>
          </tr>
        `;
      });
      tbody.innerHTML = tableHtml;
    }

  } catch(e) {
    console.error("Dashboard poll error:", e);
  }
}

updateDashboard();
setInterval(updateDashboard, 2000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return get_dashboard_html()


@app.get("/api/status")
async def api_status():
    """Returns the live multi-bot state dynamically from state/live_paper_session.json."""
    session_file = Path("state/live_paper_session.json")
    if session_file.exists():
        try:
            with open(session_file, "r") as f:
                data = json.load(f)

            # Authoritative State/API Payload Invariant:
            # If valuation_status == DATA_UNAVAILABLE: unrealized_pnl, gross_pnl, net_pnl MUST be None (null)
            for b in data.get("bot_states", {}).values():
                act = b.get("active_trade")
                if act and act.get("valuation_status") == "DATA_UNAVAILABLE":
                    act["unrealized_pnl"] = None
                    act["gross_pnl"] = None
                    act["net_pnl"] = None
                closed_pnl = sum(c.get("net_pnl", 0.0) for c in b.get("closed_trades", []))
                live_unrealized = act.get("unrealized_pnl") if (act and act.get("valuation_status") != "DATA_UNAVAILABLE") else None
                b["net_pnl"] = round(closed_pnl + (live_unrealized or 0.0), 2)

            return data
        except Exception as e:
            logger.warning(f"Error reading session file: {e}")

    # Fallback default state
    return {
        "last_updated": datetime.now().isoformat(),
        "total_capital_deployed": 500000.0,
        "bot_states": {},
        "session_log": [],
        "final_settlement": {
            "total_realized_gross": 0.0,
            "total_statutory_friction": 0.0,
            "total_net_realized_pnl": 0.0,
        },
    }
