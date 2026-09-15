# 🔬 Autonomous Indian Quant Trading & Research Agent

**A production-grade, self-provisioning, regime-aware, news-aware quantitative research platform for Indian markets.**

> ⚠️ **LIVE_TRADING_ENABLED = false** — Real-money trading is permanently disabled.

## Architecture

```
MARKET DATA (yfinance / broker APIs)
        │
   ┌────┴────┐
   │         │
PRICE     NEWS/EVENTS
FEATURES   (RSS, NSE)
   │         │
   └────┬────┘
        ↓
  REGIME DETECTOR
  (Rule-based / HMM)
        ↓
  STRATEGY ENSEMBLE
  ┌──┬──┬──┬──┐
  Trend Momentum MeanRev Breakout ...
  └──┴──┴──┴──┘
        ↓
  ML CONFIDENCE MODEL
        ↓
  RISK ENGINE
  (ATR sizing, drawdown limits, kill switch)
        ↓
  EXECUTION (Paper only)
        ↓
  MONITORING DASHBOARD
        ↓
  DRIFT DETECTION → RETRAINING
```

## Quick Start

```powershell
# Bootstrap (install deps + verify setup)
.\bootstrap.ps1

# OR manually:
uv pip install --system -r requirements.txt
python research_agent.py --dry-run

# Full autonomous research pipeline
python research_agent.py --autonomous

# Download data only
python research_agent.py --data-only

# Backtest only (assumes data exists)
python research_agent.py --backtest-only

# Start monitoring dashboard
python research_agent.py --dashboard
```

## Baseline Strategies (12)

| # | Strategy | Type | Hypothesis |
|---|----------|------|-----------|
| 1 | SMA Crossover | Trend | Price trends persist due to behavioral momentum |
| 2 | Momentum | Momentum | Winners keep winning due to slow information diffusion |
| 3 | RSI Mean Reversion | Mean Reversion | Extreme moves revert due to behavioral overreaction |
| 4 | Bollinger Mean Reversion | Mean Reversion | Price reverts to mean after statistical extremes |
| 5 | Donchian Breakout | Breakout | Channel breakouts signal new trends |
| 6 | VWAP Trend | Trend | Institutional flow anchors around VWAP |
| 7 | Dual Momentum | Momentum | Absolute + relative momentum filters noise |
| 8 | MACD Crossover | Momentum | EMA convergence/divergence captures momentum shifts |
| 9 | ADX Trend | Trend | ADX identifies genuine trending markets |
| 10 | Gap Mean Reversion | Mean Reversion | Overnight gaps overshoot and revert |
| 11 | Volatility Breakout | Breakout | ATR-based breakouts signal directional moves |
| 12 | Consecutive Days | Mean Reversion | Streaks exhaust themselves and revert |

## Cost Model (Indian Market)

All backtests include: brokerage, STT, exchange charges, GST, SEBI charges, stamp duty, slippage, spread. Tested under 4 scenarios: optimistic → base → pessimistic → stress.

## Validation Framework

- Walk-forward validation (chronological, 5 folds)
- Monte Carlo simulation (1000 trade reshuffles)
- Cost stress testing (4 scenarios)
- Parameter sensitivity (±30% perturbation)
- Robustness scoring (composite 0-1)

## Directory Structure

```
├── src/                    # Core source code
│   ├── data/               # Data pipeline
│   ├── features/           # Feature engineering
│   ├── regime/             # Regime detection
│   ├── strategies/         # Strategy implementations
│   ├── backtesting/        # Backtesting engine + validation
│   ├── risk/               # Risk engine
│   ├── execution/          # Paper trading
│   ├── ml/                 # ML models (future)
│   ├── events/             # News/event pipeline (future)
│   └── monitoring/         # Dashboard
├── data/                   # Market data (Parquet)
├── experiments/            # Experiment logs
├── reports/                # Generated reports
├── models/                 # Model checkpoints
├── research/               # Notebooks & literature
├── logs/                   # Application logs
├── state/                  # Paper broker state
├── research_agent.py       # Main orchestrator
├── bootstrap.ps1           # Setup script
└── .env                    # Configuration (LIVE_TRADING_ENABLED=false)
```

## Safety

- `LIVE_TRADING_ENABLED=false` is enforced at startup
- Kill switch activates on excessive drawdown
- All broker adapters check safety gate before every order
- No authentication bypass
- No CAPTCHA/2FA bypass
- Paper trading only

## License

Internal research use only.
