# Survivorship Bias Audit & Historical Universe Report

**Audit Target**: Equity Universe Construction & Cross-Sectional Ranking  
**Module**: `src/data/universe.py` (`HistoricalUniverseManager`)  
**Data File**: `data/universe_history/nifty50_membership_history.csv`  
**Test Suite**: `tests/test_universe.py`  
**Date**: September 16, 2026  

---

## 1. Executive Summary

A backtest that evaluates equity strategies on today's index constituents (the "survivors") suffers from severe positive survivorship bias. By selecting stocks that are successful in 2026, the backtest retroactively ignores companies that were dominant members of the NIFTY 50 in 2015–2020 but suffered catastrophic declines or insolvency (e.g. Yes Bank, Zee Entertainment, DHFL, Reliance Communications).

---

## 2. Key Historical Constituent Changes (2015–2026)

| Date | Added Symbol | Excluded Symbol | Catalyzing Event |
|---|---|---|---|
| **2016-03-31** | `BHARTIINFRATEL` | `PNB` | NPA crisis in Public Sector Banks |
| **2017-03-31** | `IBULHSGFIN` | `IDEA` | Telecom sector margin collapse |
| **2017-09-29** | `BAJFINANCE` | `ACC` | Cement consolidation vs NBFC growth |
| **2019-09-27** | `NESTLEIND` | `IBULHSGFIN` | NBFC liquidity crisis (IL&FS contagion) |
| **2020-03-27** | `SHREECEM` | `YESBANK` | RBI moratorium, capital collapse (>90% loss) |
| **2020-09-25** | `HDFCLIFE`, `SBILIFE` | `BHARTIINFRATEL`, `ZEEL` | Governance & debt overhang in media/infra |
| **2022-09-30** | `ADANIENT` | `SHREECEM` | Adani Group conglomerate expansion |
| **2024-03-28** | `SHRIRAMFIN` | `UPL` | Agrochemical inventory de-stocking cycle |

---

## 3. Implementation of Point-in-Time Filtering

The newly introduced `HistoricalUniverseManager` in [`src/data/universe.py`](file:///c:/Users/HP/Desktop/Trading%20Bot/src/data/universe.py):
1. **Reconstructs Point-in-Time Membership**: For any query date $t \in [2015, 2026]$, it dynamically computes the exact 50 stocks eligible on that date.
2. **Rejection of Future Entrants**: Prevents historical backtests from selecting stocks like `ADANIENT` prior to September 2022 or `SHRIRAMFIN` prior to March 2024.
3. **Inclusion of Delisted/Exited Equities**: Mandates that any cross-sectional equity model evaluate fallen angels like `YESBANK` during their tenure in the index.

---

## 4. Impact on Existing Strategies
- **Index Options & Futures (Strategies 1, 2, 3, 4, 5)**: Because these strategies trade the **NIFTY 50 and BANK NIFTY index contracts directly**, they are structurally free from single-stock survivorship bias (the index calculation by NSE automatically reflects rebalancings in the index level).
- **Single-Stock Momentum & Leader Breakouts (`leader_breakout.py`, `cross_sectional.py`)**: Must use `HistoricalUniverseManager.is_eligible(symbol, date)` to validate that a stock was actually eligible before generating buy signals.
