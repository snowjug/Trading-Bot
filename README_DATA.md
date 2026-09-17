# DHAN MARKET DATA LAKE & QUANT RESEARCH INFRASTRUCTURE

Production-grade Indian Market Data Lake, Deterministic Replay Engine, and Research Pipeline powered by official DhanHQ Data API access.

---

## Architecture Overview

```
DhanHQ Official Data API (api.dhan.co/v2)
   │
   ▼
[src/data/collector.py] ── Live HTTP/Feed Ingestion (Fail-Closed)
   │
   ▼
data/raw/dhan/ ───────── Immutable Raw Payloads (Option Chains, Quotes, Feed)
   │
   ▼
data/normalized/ ─────── Partitioned Parquet (Options, Indices, Microstructure)
   │
   ▼
data/metadata/ ───────── Instrument Manifests & Session Snapshots (SHA-256)
   │
   ▼
data/derived/features/ ── Point-In-Time Features (available_at <= decision_time)
   │
   ▼
src/replay/ ──────────── Unified Market Event Bus & Deterministic Replay Engine
   │
   ▼
src/strategies/ ──────── 6 Production Strategies (Same Decision Logic)
   │
   ▼
src/execution/ ───────── Realistic Microstructure Simulator (Ask for Buy, Bid for Sell)
   │
   ▼
src/backtesting/ ─────── Independent P&L Auditor & 3-Way Reconciliation
```

---

## Safety Guarantees

1. **`Config.LIVE_TRADING_ENABLED = False`**: Hard-coded safety invariant.
2. **Order Route Hard-Block**: Any internal call targeting Dhan `/orders` or trade routing triggers an immediate `RuntimeError("FAIL CLOSED SAFETY VIOLATION")`.
3. **No Synthetic Pricing**: If Dhan data is absent or stale, returns `DATA_UNAVAILABLE` and halts execution (`NO_EXECUTION`). Zero fallback to LTP or artificial Black-Scholes estimates.

---

## Directory Layout

```
data/
  raw/
    dhan/
      optionchain/date=YYYY-MM-DD/
      quotes/date=YYYY-MM-DD/
      historical/
  normalized/
    options/date=YYYY-MM-DD/underlying=NIFTY/
    indices/
  derived/
    features/
    training/
  metadata/
    instruments/date=YYYY-MM-DD/
      instrument_manifest.parquet
      manifest_meta.json
    sessions/
    manifests/
  session/
    YYYY-MM-DD/
      signal_journal.csv
      trade_journal.csv
      rejected_signals.csv
      live_paper_session.json
```

---

## Command Reference

### 1. Data Lake Inventory & Statistics
```bash
# Print complete dataset inventory, row counts, sizes, and date ranges
python scripts/data_inventory.py

# Calculate compression ratios, daily velocity, and monthly/yearly storage projections
python scripts/data_stats.py

# Audit all Parquet files for corruption, truncation, or schema drift
python scripts/data_validate.py
```

### 2. Historical & Live Market Data Ingestion
```bash
# Download historical daily index candles and rolling options from Dhan
python scripts/download_dhan_history.py \
    --symbol NIFTY \
    --start 2026-09-01 \
    --end 2026-09-16 \
    --include-rolling-options

# Fetch and store normalized live option chains (all strikes, Greeks, Bid/Ask)
python scripts/build_option_chain_dataset.py \
    --underlying NIFTY
```

### 3. Point-in-Time Feature Engineering
```bash
# Generate leak-free point-in-time features with strict available_at timestamps
python scripts/build_features.py \
    --source data/normalized/indices/NIFTY_daily.parquet \
    --output data/derived/features
```

### 4. Machine Learning Training Dataset Pipeline
```bash
# Construct leak-free chronological splits (Train, Validation, Untouched Test)
python scripts/build_training_dataset.py \
    --source data/normalized/indices/NIFTY_daily.parquet \
    --version 2026.1.0
```

### 5. Market Replay Engine
```bash
# Execute deterministic historical replay through the strategy event bus (speed=0)
python scripts/replay_session.py \
    --date 2026-09-17 \
    --symbol NIFTY \
    --speed 0 \
    --strategy all
```

### 6. Dataset Export (Parquet & CSV)
```bash
# Export option datasets for external research or quantitative analysis
python scripts/export_dataset.py \
    --dataset options \
    --start 2026-09-01 \
    --end 2026-09-17 \
    --output exports/nifty_options_2026.parquet

# Export features to CSV for quick inspection
python scripts/export_dataset.py \
    --dataset features \
    --format csv \
    --output exports/nifty_features.csv
```

### 7. End-of-Day Daily Reporting & Audit Packager
```bash
# Generate daily session audit report with all 14 institutional artifacts
python scripts/generate_daily_report.py \
    --date 2026-09-17
```

---

## Testing & Quality Assurance

Run the comprehensive institutional test suite verifying data lake integrity, realistic execution fills, replay determinism, independent P&L calculation, and safety gates:

```bash
python -m pytest tests/test_dhan_data_lake_and_replay.py -v
```
