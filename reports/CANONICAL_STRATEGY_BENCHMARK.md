# CANONICAL STRATEGY BENCHMARK REPORT

**Repository:** https://github.com/snowjug/Trading-Bot

**Split:** DEVELOPMENT (2019-01-01 -> 2024-09-17)  |  **Cost Model:** Statutory Post-Oct 2024 (Side-Aware STT, Stamp Duty, GST, Exchange, SEBI, Spread + Slippage)

**Rule:** Baseline canonical measurement first. Zero parameter optimization. Zero machine learning.

---

## 1. CANONICAL STRATEGY SCOREBOARD

| Strategy | Family | Instrument | Trades | Gross P&L | Costs | Net P&L | Exp/Trd | Win% | PF | Max DD | Cap Req | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **NIFTY_ORB_15_1R** | PRICE_ACTION | NIFTY_FUT | 996 | ₹-50,571 | ₹73,560 | **₹-124,130** | ₹-125 | 48.1% | 0.85 | ₹133,888 | ₹15,000 | **REJECTED** |
| **NIFTY_ORB_15_1.5R** | PRICE_ACTION | NIFTY_FUT | 996 | ₹-51,266 | ₹73,559 | **₹-124,824** | ₹-125 | 41.1% | 0.87 | ₹154,425 | ₹15,000 | **REJECTED** |
| **NIFTY_ORB_15_2R** | PRICE_ACTION | NIFTY_FUT | 996 | ₹-97,415 | ₹73,485 | **₹-170,900** | ₹-172 | 35.8% | 0.83 | ₹174,386 | ₹15,000 | **REJECTED** |
| **NIFTY_ORB_15_EOD** | PRICE_ACTION | NIFTY_FUT | 996 | ₹16,965 | ₹73,667 | **₹-56,702** | ₹-57 | 27.9% | 0.95 | ₹88,567 | ₹15,000 | **REJECTED** |
| **NIFTY_ORB_30_1.5R** | PRICE_ACTION | NIFTY_FUT | 995 | ₹44,699 | ₹73,380 | **₹-28,681** | ₹-29 | 41.5% | 0.97 | ₹69,509 | ₹15,000 | **REJECTED** |
| **NIFTY_VWAP_TREND** | PRICE_ACTION | NIFTY_FUT | 651 | ₹-33,514 | ₹47,412 | **₹-80,926** | ₹-124 | 37.6% | 0.80 | ₹83,424 | ₹15,000 | **REJECTED** |
| **NIFTY_VWAP_MEAN_REVERSION** | PRICE_ACTION | NIFTY_FUT | 409 | ₹-90,756 | ₹30,239 | **₹-120,995** | ₹-296 | 41.8% | 0.67 | ₹124,066 | ₹15,000 | **REJECTED** |
| **NIFTY_GAP_FADE** | PRICE_ACTION | NIFTY_FUT | 317 | ₹22,407 | ₹23,783 | **₹-1,376** | ₹-4 | 44.5% | 1.00 | ₹47,449 | ₹15,000 | **REJECTED** |
| **NIFTY_GAP_CONTINUATION** | PRICE_ACTION | NIFTY_FUT | 419 | ₹66,650 | ₹31,345 | **₹35,305** | ₹84 | 45.3% | 1.11 | ₹27,487 | ₹15,000 | **REJECTED** |
| **FUT_MA_CROSS_20_50** | TREND_FOLLOWING | NIFTY_FUT | 18 | ₹820,449 | ₹19,578 | **₹800,871** | ₹44,493 | 61.1% | 4.59 | ₹134,884 | ₹160,000 | **REJECTED** |
| **FUT_MA_CROSS_50_200** | TREND_FOLLOWING | NIFTY_FUT | 7 | ₹175,379 | ₹7,547 | **₹167,831** | ₹23,976 | 28.6% | 1.28 | ₹243,869 | ₹160,000 | **REJECTED** |
| **FUT_DONCHIAN_20D** | TREND_FOLLOWING | NIFTY_FUT | 40 | ₹177,514 | ₹42,505 | **₹135,008** | ₹3,375 | 35.0% | 1.19 | ₹130,828 | ₹160,000 | **VALIDATED** |
| **FUT_DONCHIAN_55D** | TREND_FOLLOWING | NIFTY_FUT | 20 | ₹374,926 | ₹21,657 | **₹353,269** | ₹17,663 | 35.0% | 2.03 | ₹184,493 | ₹160,000 | **VALIDATED** |
| **FUT_SUPERTREND_10_3** | TREND_FOLLOWING | NIFTY_FUT | 5 | ₹-769,941 | ₹5,458 | **₹-775,399** | ₹-155,080 | 40.0% | 0.06 | ₹777,621 | ₹160,000 | **REJECTED** |
| **MOM_TS_NIFTY_FUT** | MOMENTUM | NIFTY_FUT | 5 | ₹308,015 | ₹5,567 | **₹302,448** | ₹60,490 | 40.0% | 1.68 | ₹133,146 | ₹160,000 | **REJECTED** |
| **MOM_CS_FUTSTK_20D** | MOMENTUM | STOCK_FUT_PANEL | 64 | ₹-5,774,386 | ₹43,456 | **₹-5,817,842** | ₹-90,904 | 56.2% | 0.90 | ₹17,757,432 | ₹500,000 | **REJECTED** |
| **MOM_CS_FUTSTK_60D** | MOMENTUM | STOCK_FUT_PANEL | 62 | ₹-6,273,604 | ₹42,098 | **₹-6,315,702** | ₹-101,866 | 51.6% | 0.89 | ₹29,797,373 | ₹500,000 | **REJECTED** |
| **MOM_CS_FUTSTK_120D** | MOMENTUM | STOCK_FUT_PANEL | 60 | ₹-4,711,867 | ₹40,740 | **₹-4,752,607** | ₹-79,210 | 45.0% | 0.92 | ₹18,687,721 | ₹500,000 | **REJECTED** |
| **FUT_RSI_REVERSION_30_70** | MEAN_REVERSION | NIFTY_FUT | 92 | ₹-145,421 | ₹95,586 | **₹-241,007** | ₹-2,620 | 44.6% | 0.75 | ₹424,364 | ₹160,000 | **REJECTED** |
| **FUT_BOLLINGER_REVERSION_2SD** | MEAN_REVERSION | NIFTY_FUT | 49 | ₹-222,234 | ₹50,694 | **₹-272,928** | ₹-5,570 | 42.9% | 0.57 | ₹439,047 | ₹160,000 | **REJECTED** |
| **FUT_ZSCORE_REVERSION_2SD** | MEAN_REVERSION | NIFTY_FUT | 49 | ₹-222,234 | ₹50,694 | **₹-272,928** | ₹-5,570 | 42.9% | 0.57 | ₹439,047 | ₹160,000 | **REJECTED** |
| **OPT_ATM_STRADDLE_0DTE** | OPTIONS_SPREAD | NIFTY_OPT | 293 | ₹404,438 | ₹48,386 | **₹356,052** | ₹1,215 | 70.6% | 2.13 | ₹39,214 | ₹150,000 | **VALIDATED** |
| **OPT_ATM_STRADDLE_WEEKLY** | OPTIONS_SPREAD | NIFTY_OPT | 281 | ₹149,175 | ₹48,251 | **₹100,924** | ₹359 | 62.3% | 1.10 | ₹234,138 | ₹150,000 | **REJECTED** |
| **OPT_STRANGLE_WEEKLY** | OPTIONS_SPREAD | NIFTY_OPT | 281 | ₹506,586 | ₹47,464 | **₹459,121** | ₹1,634 | 76.2% | 1.77 | ₹148,721 | ₹150,000 | **VALIDATED** |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | OPTIONS_SPREAD | NIFTY_OPT | 281 | ₹159,465 | ₹46,498 | **₹112,967** | ₹402 | 68.0% | 1.25 | ₹53,102 | ₹25,000 | **VALIDATED** |
| **OPT_BEAR_CALL_SPREAD_WEEKLY** | OPTIONS_SPREAD | NIFTY_OPT | 281 | ₹-380,598 | ₹46,704 | **₹-427,302** | ₹-1,521 | 47.0% | 0.46 | ₹439,730 | ₹25,000 | **REJECTED** |
| **OPT_DEBIT_CALL_SPREAD_BREAKOUT** | OPTIONS_SPREAD | NIFTY_OPT | 281 | ₹0 | ₹44,960 | **₹-44,960** | ₹-160 | 0.0% | 0.00 | ₹44,800 | ₹25,000 | **REJECTED** |
| **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** | OPTIONS_SPREAD | NIFTY_OPT | 281 | ₹0 | ₹44,960 | **₹-44,960** | ₹-160 | 0.0% | 0.00 | ₹44,800 | ₹25,000 | **REJECTED** |
| **OPT_IRON_CONDOR_WEEKLY** | OPTIONS_SPREAD | NIFTY_OPT | 281 | ₹-28,865 | ₹46,578 | **₹-75,443** | ₹-268 | 57.7% | 0.87 | ₹176,315 | ₹25,000 | **REJECTED** |
| **OPT_IRON_FLY_0DTE** | OPTIONS_SPREAD | NIFTY_OPT | 293 | ₹502,475 | ₹48,239 | **₹454,236** | ₹1,550 | 70.6% | 3.11 | ₹18,529 | ₹25,000 | **VALIDATED** |
| **VOL_VRP_SHORT** | OPTIONS_VOLATILITY | NIFTY_OPT | 281 | ₹-28,865 | ₹46,578 | **₹-75,443** | ₹-268 | 57.7% | 0.87 | ₹176,315 | ₹25,000 | **REJECTED** |
| **PCR_TREND_CONFIRMATION** | PCR_OI | NIFTY_FUT | 0 | ₹0 | ₹0 | **₹0** | ₹0 | 0.0% | — | ₹0 | ₹160,000 | **REJECTED** |
| **EXPIRY_0DTE_DECAY** | EXPIRY | NIFTY_OPT | 0 | ₹0 | ₹0 | **₹0** | ₹0 | 0.0% | — | ₹0 | ₹25,000 | **REJECTED** |
| **OVERNIGHT_FUT_DRIFT** | OVERNIGHT | NIFTY_FUT | 1352 | ₹589,356 | ₹1,411,301 | **₹-821,944** | ₹-608 | 46.7% | 0.71 | ₹830,511 | ₹160,000 | **REJECTED** |

---

## 2. TOP VALIDATED CANDIDATES

### FUT_DONCHIAN_20D (TREND_FOLLOWING)

- **Net P&L:** ₹135,008.47 over 40 trades (Expectancy: ₹3,375.21/trade)
- **Win Rate:** 35.0% | **Profit Factor:** 1.192 | **Max DD:** ₹130,827.63
- **Capital Required:** ₹160,000 | **Cost Stress Survives 2x:** True
- **Validation Reason:** Net positive on DEV, survives 2x friction, n=40

### FUT_DONCHIAN_55D (TREND_FOLLOWING)

- **Net P&L:** ₹353,269.28 over 20 trades (Expectancy: ₹17,663.46/trade)
- **Win Rate:** 35.0% | **Profit Factor:** 2.033 | **Max DD:** ₹184,493.34
- **Capital Required:** ₹160,000 | **Cost Stress Survives 2x:** True
- **Validation Reason:** Net positive on DEV, survives 2x friction, n=20

### OPT_ATM_STRADDLE_0DTE (OPTIONS_SPREAD)

- **Net P&L:** ₹356,051.52 over 293 trades (Expectancy: ₹1,215.19/trade)
- **Win Rate:** 70.6% | **Profit Factor:** 2.134 | **Max DD:** ₹39,213.65
- **Capital Required:** ₹150,000 | **Cost Stress Survives 2x:** True
- **Validation Reason:** Net positive on DEV, n=293

### OPT_STRANGLE_WEEKLY (OPTIONS_SPREAD)

- **Net P&L:** ₹459,121.43 over 281 trades (Expectancy: ₹1,633.88/trade)
- **Win Rate:** 76.2% | **Profit Factor:** 1.774 | **Max DD:** ₹148,721.18
- **Capital Required:** ₹150,000 | **Cost Stress Survives 2x:** True
- **Validation Reason:** Net positive on DEV, n=281

### OPT_BULL_PUT_SPREAD_WEEKLY (OPTIONS_SPREAD)

- **Net P&L:** ₹112,967.48 over 281 trades (Expectancy: ₹402.02/trade)
- **Win Rate:** 68.0% | **Profit Factor:** 1.252 | **Max DD:** ₹53,101.84
- **Capital Required:** ₹25,000 | **Cost Stress Survives 2x:** True
- **Validation Reason:** Net positive on DEV, n=281

### OPT_IRON_FLY_0DTE (OPTIONS_SPREAD)

- **Net P&L:** ₹454,236.07 over 293 trades (Expectancy: ₹1,550.29/trade)
- **Win Rate:** 70.6% | **Profit Factor:** 3.106 | **Max DD:** ₹18,528.81
- **Capital Required:** ₹25,000 | **Cost Stress Survives 2x:** True
- **Validation Reason:** Net positive on DEV, n=293


---

## 3. REJECTED STRATEGIES

| Strategy | Trades | Net P&L | Reason for Rejection |
|---|---|---|---|
| **NIFTY_ORB_15_1R** | 996 | ₹-124,130 | Net negative after 0.30% spread & statutory fees (Net: Rs -124,130) |
| **NIFTY_ORB_15_1.5R** | 996 | ₹-124,824 | Net negative after 0.30% spread & statutory fees (Net: Rs -124,824) |
| **NIFTY_ORB_15_2R** | 996 | ₹-170,900 | Net negative after 0.30% spread & statutory fees (Net: Rs -170,900) |
| **NIFTY_ORB_15_EOD** | 996 | ₹-56,702 | Net negative after 0.30% spread & statutory fees (Net: Rs -56,702) |
| **NIFTY_ORB_30_1.5R** | 995 | ₹-28,681 | Net negative after 0.30% spread & statutory fees (Net: Rs -28,681) |
| **NIFTY_VWAP_TREND** | 651 | ₹-80,926 | Net negative after 0.30% spread & statutory fees (Net: Rs -80,926) |
| **NIFTY_VWAP_MEAN_REVERSION** | 409 | ₹-120,995 | Net negative after 0.30% spread & statutory fees (Net: Rs -120,995) |
| **NIFTY_GAP_FADE** | 317 | ₹-1,376 | Net negative after 0.30% spread & statutory fees (Net: Rs -1,376) |
| **NIFTY_GAP_CONTINUATION** | 419 | ₹35,305 | Fails 2x cost stress test (Net 2x: Rs -17,997) |
| **FUT_MA_CROSS_20_50** | 18 | ₹800,871 | Insufficient trade sample size (n=18 < 20) |
| **FUT_MA_CROSS_50_200** | 7 | ₹167,831 | Insufficient trade sample size (n=7 < 20) |
| **FUT_SUPERTREND_10_3** | 5 | ₹-775,399 | Net negative after statutory friction (Net P&L: Rs -775,399) |
| **MOM_TS_NIFTY_FUT** | 5 | ₹302,448 | Insufficient trade sample size (n=5 < 20) |
| **MOM_CS_FUTSTK_20D** | 64 | ₹-5,817,842 | Net negative after futures turnover STT (Net P&L: Rs -5,817,842) |
| **MOM_CS_FUTSTK_60D** | 62 | ₹-6,315,702 | Net negative after futures turnover STT (Net P&L: Rs -6,315,702) |
| **MOM_CS_FUTSTK_120D** | 60 | ₹-4,752,607 | Net negative after futures turnover STT (Net P&L: Rs -4,752,607) |
| **FUT_RSI_REVERSION_30_70** | 92 | ₹-241,007 | Net negative after statutory friction (Net P&L: Rs -241,007) |
| **FUT_BOLLINGER_REVERSION_2SD** | 49 | ₹-272,928 | Net negative after statutory friction (Net P&L: Rs -272,928) |
| **FUT_ZSCORE_REVERSION_2SD** | 49 | ₹-272,928 | Net negative after statutory friction (Net P&L: Rs -272,928) |
| **OPT_ATM_STRADDLE_WEEKLY** | 281 | ₹100,924 | Severe tail risk / drawdown exceeds account limit |
| **OPT_BEAR_CALL_SPREAD_WEEKLY** | 281 | ₹-427,302 | Net negative after statutory option friction (Net: Rs -427,302) |
| **OPT_DEBIT_CALL_SPREAD_BREAKOUT** | 281 | ₹-44,960 | Net negative after statutory option friction (Net: Rs -44,960) |
| **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** | 281 | ₹-44,960 | Net negative after statutory option friction (Net: Rs -44,960) |
| **OPT_IRON_CONDOR_WEEKLY** | 281 | ₹-75,443 | Net negative after statutory option friction (Net: Rs -75,443) |
| **VOL_VRP_SHORT** | 281 | ₹-75,443 | Net negative after statutory option friction (Net: Rs -75,443) |
| **PCR_TREND_CONFIRMATION** | 0 | ₹0 | 0 trades fired in DEV split |
| **EXPIRY_0DTE_DECAY** | 0 | ₹0 | Net negative after statutory option friction (Net: Rs 0) |
| **OVERNIGHT_FUT_DRIFT** | 1352 | ₹-821,944 | Net negative after statutory friction (Net P&L: Rs -821,944) |

---

## 4. UNTESTABLE STRATEGIES & DATA LIMITATIONS

All canonical strategies in the catalog had sufficient authentic historical data for evaluation.


---

## 5. CAPITAL RESULTS ACROSS TIERS

Sizing rule: whole lots only, $\le 60\%$ of account at risk in a single position.

### ₹20,000 ACCOUNT

- **NOTHING EXECUTABLE UNDER $\le 60\%$ MARGIN RULE.** All canonical single-lot requirements exceed ₹12,000.

### ₹50,000 ACCOUNT

| Strategy | Lots | Net P&L | Return % | Max DD | Max DD % |
|---|---|---|---|---|---|
| NIFTY_ORB_15_1R | 2 | ₹-248,261 | -496.52% | ₹267,776 | 535.55% |
| NIFTY_ORB_15_1.5R | 2 | ₹-249,648 | -499.30% | ₹308,850 | 617.70% |
| NIFTY_ORB_15_2R | 2 | ₹-341,800 | -683.60% | ₹348,772 | 697.54% |
| NIFTY_ORB_15_EOD | 2 | ₹-113,404 | -226.81% | ₹177,134 | 354.27% |
| NIFTY_ORB_30_1.5R | 2 | ₹-57,362 | -114.72% | ₹139,018 | 278.04% |
| NIFTY_VWAP_TREND | 2 | ₹-161,851 | -323.70% | ₹166,849 | 333.70% |
| NIFTY_VWAP_MEAN_REVERSION | 2 | ₹-241,991 | -483.98% | ₹248,133 | 496.27% |
| NIFTY_GAP_FADE | 2 | ₹-2,753 | -5.51% | ₹94,898 | 189.80% |
| NIFTY_GAP_CONTINUATION | 2 | ₹70,609 | 141.22% | ₹54,973 | 109.95% |
| OPT_BULL_PUT_SPREAD_WEEKLY | 1 | ₹112,967 | 225.93% | ₹53,102 | 106.20% |
| OPT_BEAR_CALL_SPREAD_WEEKLY | 1 | ₹-427,302 | -854.60% | ₹439,730 | 879.46% |
| OPT_DEBIT_CALL_SPREAD_BREAKOUT | 1 | ₹-44,960 | -89.92% | ₹44,800 | 89.60% |
| OPT_DEBIT_PUT_SPREAD_BREAKDOWN | 1 | ₹-44,960 | -89.92% | ₹44,800 | 89.60% |
| OPT_IRON_CONDOR_WEEKLY | 1 | ₹-75,443 | -150.89% | ₹176,315 | 352.63% |
| OPT_IRON_FLY_0DTE | 1 | ₹454,236 | 908.47% | ₹18,529 | 37.06% |
| VOL_VRP_SHORT | 1 | ₹-75,443 | -150.89% | ₹176,315 | 352.63% |
| EXPIRY_0DTE_DECAY | 1 | ₹0 | 0.00% | ₹0 | 0.00% |

### ₹1,00,000 ACCOUNT

| Strategy | Lots | Net P&L | Return % | Max DD | Max DD % |
|---|---|---|---|---|---|
| NIFTY_ORB_15_1R | 4 | ₹-496,521 | -496.52% | ₹535,552 | 535.55% |
| NIFTY_ORB_15_1.5R | 4 | ₹-499,296 | -499.30% | ₹617,700 | 617.70% |
| NIFTY_ORB_15_2R | 4 | ₹-683,599 | -683.60% | ₹697,543 | 697.54% |
| NIFTY_ORB_15_EOD | 4 | ₹-226,808 | -226.81% | ₹354,268 | 354.27% |
| NIFTY_ORB_30_1.5R | 4 | ₹-114,724 | -114.72% | ₹278,037 | 278.04% |
| NIFTY_VWAP_TREND | 4 | ₹-323,703 | -323.70% | ₹333,698 | 333.70% |
| NIFTY_VWAP_MEAN_REVERSION | 4 | ₹-483,982 | -483.98% | ₹496,266 | 496.27% |
| NIFTY_GAP_FADE | 4 | ₹-5,506 | -5.51% | ₹189,797 | 189.80% |
| NIFTY_GAP_CONTINUATION | 4 | ₹141,219 | 141.22% | ₹109,946 | 109.95% |
| OPT_BULL_PUT_SPREAD_WEEKLY | 2 | ₹225,935 | 225.93% | ₹106,204 | 106.20% |
| OPT_BEAR_CALL_SPREAD_WEEKLY | 2 | ₹-854,604 | -854.60% | ₹879,460 | 879.46% |
| OPT_DEBIT_CALL_SPREAD_BREAKOUT | 2 | ₹-89,920 | -89.92% | ₹89,600 | 89.60% |
| OPT_DEBIT_PUT_SPREAD_BREAKDOWN | 2 | ₹-89,920 | -89.92% | ₹89,600 | 89.60% |
| OPT_IRON_CONDOR_WEEKLY | 2 | ₹-150,887 | -150.89% | ₹352,629 | 352.63% |
| OPT_IRON_FLY_0DTE | 2 | ₹908,472 | 908.47% | ₹37,058 | 37.06% |
| VOL_VRP_SHORT | 2 | ₹-150,887 | -150.89% | ₹352,629 | 352.63% |
| EXPIRY_0DTE_DECAY | 2 | ₹0 | 0.00% | ₹0 | 0.00% |


---
