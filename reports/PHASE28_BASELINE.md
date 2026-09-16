# Phase 28 — Immutable Baseline Freeze

**Audit Authority**: Antigravity Quantitative Research Team  
**Git HEAD SHA**: `2d6ed5e6d6dbeeabfa295377ac01c17f75000f80`  
**Baseline Tag**: `phase28-baseline-v1.0`  
**Timestamp**: `2026-09-16T19:43:15+05:30`  
**Branch**: `main`  
**Safety Gate**: `Config.LIVE_TRADING_ENABLED = False` (Hard Enforced)  

---

## 1. Executive Summary & Purpose

This document freezes the exact mathematical and computational state of the repository following the completion of Phases 0–27 (Institutional Quantitative Hardening). 

Under the Phase 28 mandate:
> *"Record current HEAD SHA, all current strategy results, all current reports, dataset hashes, configuration hashes. Create an immutable baseline. Do not allow future research changes to silently alter the baseline."*

Any divergence in future research runs against this baseline must be audited, reconciled, and mathematically accounted for.

---

## 2. Frozen Strategy Performance Baseline

The table below records the exact performance and risk metrics established at the conclusion of Phase 27 across the 2026 real-data evaluation and walk-forward testing:

| Strategy Name | Pre-Audit Claim | Hardened Conservative Win Rate | 2026 Real PnL | OOS Sharpe | PBO | DSR p-Value | Baseline Tier |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Velocity-5 Scalper** (`active_momentum_scalper`) | 56.4% WR, +52.4% CAGR | 47.2% | +Rs 1,58,667 | 1.14 | 0.31 | 0.065 | `PAPER_CANDIDATE` |
| **Zen Curvature Spread** (`curvature_credit_spread`) | 79.8% WR, +92.1% CAGR | 68.4% | +Rs 1,24,412 | 1.08 | 0.28 | 0.034 | `PAPER_CANDIDATE` |
| **Golden Trend Runner** (`golden_trend_buyer`) | 94.9% WR, +28.1% CAGR | 57.7% | +Rs 4,934 | 0.78 | 0.38 | 0.021 | `PAPER_CANDIDATE` |
| **Apex VRP Engine** (`options_theta`) | 86.0% WR, +46.1% CAGR | 62.1% | +Rs 38,255 | 0.72 | 0.36 | 0.041 | `PAPER_CANDIDATE` |
| **Confluence Scalper** (`confluence_scalper`) | 66.7% WR, +23.1% CAGR | 40.9% | -Rs 1,911 | 0.22 | 0.62 | 0.089 | `REJECTED` (Falsified) |
| **Leader Breakout** (`leader_breakout`) | High Momentum Claim | 38.2% | -Rs 63,558 | 0.15 | 0.67 | 0.210 | `REJECTED` (Survivorship) |
| **MACD Crossover** | +15% Claimed | 31.0% | Negative | -0.21 | 0.82 | 0.850 | `REJECTED` (Negative Edge) |

---

## 3. Cryptographic Hashes of Strategy Implementations

All strategy logic files located in [`src/strategies/`](file:///c:/Users/HP/Desktop/Trading%20Bot/src/strategies/) are hashed using SHA-256:

| File Basename | SHA-256 Hash | File Size (Bytes) |
| :--- | :--- | :---: |
| `active_momentum_scalper.py` | `0a8360622dcaf04a8c641588cdbe87ec73f330b6c7aa04aebae7f6f5bb1cca27` | 11,563 |
| `adaptive_fusion.py` | `596217a7cf720587bc7a164915352c8888bcd47676015cf4b3a6362adc237461` | 5,905 |
| `base.py` | `1fdb3e60dae120bf29f131a8b324e26d9906fa85e5b8723769ef97ac131eacf2` | 24,389 |
| `competition.py` | `c4cc00bfac6c70e2d7234d1ee38748b5fb4eb4364ec409edbeb34038a3c1fd36` | 5,558 |
| `confluence_scalper.py` | `a10e44ea59a66728a6f1560d8293219b8de261172fc5b178632c82310ff1bebc` | 12,967 |
| `cross_sectional.py` | `c1068a15fd24e28fae5816a304befdc8f4dbe73f1aaa7fb3ede34c324da55daa` | 18,815 |
| `curvature_credit_spread.py` | `84921d38781df7019f4bb9d53684bdac7eb793df5066bda706c91dbb15635bda` | 10,187 |
| `futures_momentum.py` | `9af8bbb257cab2f56a804d9a21db5dbe73cad4c09839c85cc2ac0da84ef985e2` | 3,854 |
| `gold_trend_rider.py` | `14d3d749473719fd87678abd769bc95652f08fd63c6e7b97469fb492a25d0b88` | 9,093 |
| `golden_trend_buyer.py` | `37e2cf5824162e9497f16c8426b5a0665861cbf9fcdd62324e52e9a95ba5a047` | 12,384 |
| `index_reversion.py` | `e2b60ef789206969dbac32953eebd4776450b4c5a4bc684577fda404339e2070` | 3,667 |
| `leader_breakout.py` | `3ba21349f613b2b83d29cf1cd759e2c5878162e06e7848f2e57000df7a91bd9c` | 14,951 |
| `master_derivatives_portfolio.py` | `8f2121183a5b8a2c606d17fc0b11ca68e5d1542192dbcae274cf73e9499696ae` | 9,782 |
| `options_theta.py` | `e93373b52876c045d9845a78939d2713f204565938856f3da238862bfc05db1b` | 7,517 |

---

## 4. Cryptographic Hashes of Existing Audit Reports

The 22 foundational audit reports in [`reports/`](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/) represent the historical evidentiary chain:

| Report File | SHA-256 Hash | Size (Bytes) |
| :--- | :--- | :---: |
| `BROKER_SAFETY_AUDIT.md` | `38cb7000328fff0bf801a67c56f9d95e1c857048bdced7360b147af9ab5b0088` | 3,497 |
| `CODE_AUDIT.md` | `d276bca5baa3e0ebde71834195f09a1e778c5697f282ba43ef43060e5e1edcab` | 11,154 |
| `COST_AUDIT.md` | `81dadc44d3fb46998d8f055e65a37b63e73b0f9b6380282a95a73c31abc746f7` | 2,573 |
| `CPCV_REPORT.md` | `01c89a88ca150bf241472a623a362e1c5da710511fa395ce48b05f4fade84cc0` | 2,691 |
| `DATA_INTEGRITY_AUDIT.md` | `6c8125e83b9171544f35e39d619614452910c8d9f67965f1e0f53f9caef546ce` | 3,978 |
| `EXECUTION_REALISM_AUDIT.md` | `da0d15a65ca7fdde8ab76c68c32958b24784fb244cfcf53a650dd28aca4fc14f` | 3,365 |
| `FALSIFICATION_REPORT.md` | `ff5849b76eccd32c28cf44893dace9c757f5574dd20a4cd721b5b3e264d330fe` | 2,985 |
| `FINAL_REPORT.md` | `255f76d55004fa23d9b03d29da2db07a852c97cf90be1d69e435d8f53a69b171` | 10,670 |
| `FINAL_RESEARCH_REPORT.md` | `7f8694aebb2d6d6af41983416b396713f27a4ed827da0a9877e329a5bfe3dab8` | 10,012 |
| `LIQUIDITY_AUDIT.md` | `34b5154952d2263f94922d0e6c55ce256fc545557dd06a412a9b1e5f58bb7efd` | 2,824 |
| `LOOKAHEAD_AUDIT.md` | `4864b0c1d2e8a71c2a0733de5c5fc343fb120f5125c5da56b4d83717fd33608c` | 2,863 |
| `ML_AUDIT.md` | `8acf2a28557f620b79ea1d631f0e9b4bc294e100827950f95b3379b75053358f` | 2,972 |
| `OPTIONS_CONTRACT_AUDIT.md` | `ac045dca856459dded0c02a1d805c60b18e685d699063dee054f474e5ab574bd` | 3,127 |
| `OPTION_AUDIT.md` | `2a8dadfb80d9d2ca85c0025351d16e21247cfd81fc414c19d6b14a7ef7f3a785` | 3,939 |
| `OVERFITTING_AUDIT.md` | `b0cffc0be40fb38a71a85e7b33fe5f1fbb60e690b26411e513064ed894701017` | 3,082 |
| `PAPER_VS_BACKTEST_RECONCILIATION.md` | `2a343a52aea77240fd3949ecc61e8a5ed47b638e75f08fd86a2706fff89a541e` | 2,724 |
| `REAL_2026_PERFORMANCE_AUDIT.md` | `a833469bd782b143da87e0d0a8a29a9c03659aa434d2a4579d17aeb034987f72` | 11,486 |
| `REGIME_ROBUSTNESS_REPORT.md` | `6d10d5aec6b072f9730cd3b382462b630af4ffe9de48bc54b007d3fe90c76507` | 3,398 |
| `REGULATORY_COMPLIANCE_AUDIT.md` | `bc88bb0257f0fe95741770bf6314ad518f3bcd10f3e02a9bfa426c412e409c22` | 3,275 |
| `SURVIVORSHIP_AUDIT.md` | `31110bb92d6c454ab9537750a2c1791c71649db89f3189cebe75cfe1b9e0cead` | 2,922 |
| `SYSTEM_ARCHITECTURE_AUDIT.md` | `39aa99e903a6dbac3ad198e810e114061750694d9f70647723c31587d6f299a4` | 9,584 |
| `WALK_FORWARD_REPORT.md` | `731412f6635d2d502dc09c85e3462037ec44bcc3edd2a8323f7b4874ba41773c` | 3,884 |

---

## 5. System Configuration & Data Manifest Hashes

- **Primary Configuration** (`src/config.py`):  
  `0fef154f7947baae0ccc0673851c4559abb7b475c905b3f6034008e30c5c0472` (3,935 bytes)
- **Data Manifest Registry** (`data/DATA_MANIFEST.json`):  
  `97909968100d0e909e792dc0ba3139bbede55993d9ba024a44bfe704b751d817` (44,770 bytes, 58 datasets registered)

---

## 6. Baseline Invariance Declaration

By order of the Phase 28 mandate, this snapshot is **immutable**. Subsequent Phase 28 procedures will evaluate real contract availability, capital realism, independent statistical testing, and trade-by-trade reconstruction without retroactively modifying the baselines recorded here.
