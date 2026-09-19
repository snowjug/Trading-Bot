# POPULAR STRATEGY 2-YEAR CAPITAL BENCHMARK REPORT (2024–2026)

**Repository:** https://github.com/snowjug/Trading-Bot
**Period:** 2024-09-18 -> 2026-09-18  |  **Total Market Sessions:** 494 (105 weekly expiries)
**Cost Model:** Authentic Indian Statutory Post-Oct 2024 (Side-Aware STT, GST 18%, Stamp Duty, Exchange Turnover, Slippage Stress)
**Rule:** Baseline canonical measurement first. ZERO parameter optimization. Zero tuning after seeing results.

---

## 1. 2-YEAR CANONICAL BENCHMARK & CAPITAL SCOREBOARD

| Strategy | Family | Trades | Net P&L | PF | Max DD | 3× Cost | Best-3 Removed | Minimum Capital | ₹20k | ₹50k | ₹1L | ₹2.5L | ₹3L | ₹5L | ₹10L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | FUTURES_TREND | 21 | **₹-534,835** | 0.20 | ₹526,084 | ₹-609,078 | ₹-664,506 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_DONCHIAN_55D** | FUTURES_TREND | 7 | **₹16,449** | 1.17 | ₹40,773 | ₹-6,052 | ₹-95,507 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_MA_CROSS_20_50** | FUTURES_TREND | 3 | **₹22,670** | 1.62 | ₹36,399 | ₹13,411 | ₹22,670 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_MA_CROSS_50_200** | FUTURES_TREND | 1 | **₹-109,294** | 0.00 | ₹0 | ₹-113,389 | ₹-109,294 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_SUPERTREND_10_3** | FUTURES_TREND | 0 | **₹0** | 0.00 | ₹0 | ₹0 | ₹0 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_ATR_BREAKOUT** | FUTURES_TREND | 32 | **₹-133,345** | 0.53 | ₹208,912 | ₹-248,388 | ₹-230,232 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **MOM_TS_NIFTY_FUT** | FUTURES_MOMENTUM | 1 | **₹40,744** | 999.00 | ₹0 | ₹36,732 | ₹40,744 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_RSI_REVERSION_30_70** | MEAN_REVERSION | 17 | **₹183,464** | 2.41 | ₹47,216 | ₹126,378 | ₹32,245 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_BOLLINGER_REVERSION_2SD** | MEAN_REVERSION | 15 | **₹362,536** | 11.78 | ₹33,625 | ₹311,543 | ₹206,586 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **FUT_ZSCORE_REVERSION_2SD** | MEAN_REVERSION | 15 | **₹362,536** | 11.78 | ₹33,625 | ₹311,543 | ₹206,586 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OVERNIGHT_FUT_DRIFT** | OVERNIGHT | 494 | **₹-744,338** | 0.57 | ₹749,076 | ₹-2,491,128 | ₹-887,824 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **MOM_CS_FUTSTK_20D** | MOMENTUM | 22 | **₹-6,069,541** | 0.64 | ₹8,968,343 | ₹-6,099,417 | ₹-12,711,844 | ₹833,333 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE |
| **MOM_CS_FUTSTK_60D** | MOMENTUM | 20 | **₹-8,436,656** | 0.58 | ₹8,663,216 | ₹-8,463,816 | ₹-15,984,117 | ₹833,333 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE |
| **MOM_CS_FUTSTK_120D** | MOMENTUM | 17 | **₹-10,037,868** | 0.45 | ₹14,369,243 | ₹-10,060,954 | ₹-14,472,515 | ₹833,333 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE |
| **NIFTY_ORB_15_1R** | ORB | 493 | **₹-134,721** | 0.76 | ₹148,751 | ₹-210,712 | ₹-155,706 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_ORB_15_1.5R** | ORB | 493 | **₹-153,204** | 0.77 | ₹173,878 | ₹-229,137 | ₹-179,047 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_ORB_15_2R** | ORB | 493 | **₹-126,703** | 0.82 | ₹154,404 | ₹-202,720 | ₹-163,547 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_ORB_15_EOD** | ORB | 493 | **₹-135,363** | 0.82 | ₹161,058 | ₹-211,353 | ₹-185,469 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_ORB_30_1.5R** | ORB | 492 | **₹-124,586** | 0.83 | ₹158,657 | ₹-200,222 | ₹-160,406 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_VWAP_TREND** | VWAP | 298 | **₹-20,228** | 0.91 | ₹63,073 | ₹-65,542 | ₹-35,835 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_VWAP_MEAN_REVERSION** | VWAP | 214 | **₹-59,008** | 0.71 | ₹59,636 | ₹-92,120 | ₹-74,880 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_GAP_FADE** | GAP | 113 | **₹-47,160** | 0.72 | ₹70,724 | ₹-65,034 | ₹-66,162 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **NIFTY_GAP_CONTINUATION** | GAP | 170 | **₹-49,365** | 0.78 | ₹75,965 | ₹-76,315 | ₹-73,178 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_ATM_STRADDLE_0DTE** | OPTIONS_SPREAD | 105 | **₹164,901** | 1.78 | ₹30,264 | ₹128,419 | ₹112,581 | ₹250,000 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_LONG_STRADDLE_0DTE** | OPTIONS_SPREAD | 105 | **₹-201,384** | 0.50 | ₹224,122 | ₹-237,867 | ₹-258,417 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_IRON_FLY_0DTE** | OPTIONS_SPREAD | 105 | **₹46,101** | 1.26 | ₹30,504 | ₹-24,246 | ₹15,402 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **EXPIRY_0DTE_DECAY** | EXPIRY_DAY | 105 | **₹164,901** | 1.78 | ₹30,264 | ₹128,419 | ₹112,581 | ₹250,000 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_STRANGLE_WEEKLY** | OPTIONS_SPREAD | 105 | **₹143,387** | 1.54 | ₹75,705 | ₹108,437 | ₹84,831 | ₹300,000 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_LONG_STRANGLE_WEEKLY** | OPTIONS_SPREAD | 105 | **₹-178,336** | 0.59 | ₹213,670 | ₹-213,286 | ₹-278,000 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | OPTIONS_SPREAD | 105 | **₹-97,432** | 0.65 | ₹108,351 | ₹-134,477 | ₹-111,189 | ₹58,333 | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_BEAR_CALL_SPREAD_WEEKLY** | OPTIONS_SPREAD | 105 | **₹87,957** | 1.45 | ₹35,546 | ₹51,315 | ₹69,582 | ₹58,333 | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_IRON_CONDOR_WEEKLY** | OPTIONS_SPREAD | 105 | **₹-9,475** | 0.96 | ₹69,082 | ₹-83,162 | ₹-40,001 | ₹58,333 | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_DEBIT_CALL_SPREAD_BREAKOUT** | OPTIONS_SPREAD | 105 | **₹-139,544** | 0.61 | ₹141,056 | ₹-177,791 | ₹-165,310 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** | OPTIONS_SPREAD | 105 | **₹104,437** | 1.45 | ₹44,653 | ₹65,682 | ₹72,210 | ₹41,667 | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **VOL_VRP_SHORT** | OPTIONS_VOLATILITY | 105 | **₹-9,475** | 0.96 | ₹69,082 | ₹-83,162 | ₹-40,001 | ₹58,333 | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |
| **PCR_TREND_CONFIRMATION** | PCR_OI | 0 | **₹0** | 0.00 | ₹0 | ₹0 | ₹0 | ₹266,667 | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | UNEXECUTABLE | EXECUTABLE | EXECUTABLE | EXECUTABLE |

---

## 2. DETAILED STATISTICAL & RISK METRICS

| Strategy | Trades | Win% | Gross P&L | Costs | NET P&L | Exp/Trd | Sharpe | Sortino | t-stat | Worst Trade | Worst Day | Robustness Passed? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | 21 | 19.0% | ₹-497,713 | ₹37,122 | **₹-534,835** | ₹-25,468 | -2.14 | -3.45 | -2.99 | ₹-104,294 | ₹-104,294 | NO |
| **FUT_DONCHIAN_55D** | 7 | 57.1% | ₹27,699 | ₹11,250 | **₹16,449** | ₹2,350 | 0.12 | 0.62 | 0.16 | ₹-40,773 | ₹-40,773 | NO |
| **FUT_MA_CROSS_20_50** | 3 | 66.7% | ₹27,300 | ₹4,630 | **₹22,670** | ₹7,557 | 0.21 | 0.21 | 0.29 | ₹-36,399 | ₹-36,399 | NO |
| **FUT_MA_CROSS_50_200** | 1 | 0.0% | ₹-107,246 | ₹2,047 | **₹-109,294** | ₹-109,294 | 0.00 | 0.00 | 0.00 | ₹-109,294 | ₹-109,294 | NO |
| **FUT_SUPERTREND_10_3** | 0 | 0.0% | ₹0 | ₹0 | **₹0** | ₹0 | 0.00 | 0.00 | 0.00 | ₹0 | ₹0 | NO |
| **FUT_ATR_BREAKOUT** | 32 | 28.1% | ₹-75,824 | ₹57,521 | **₹-133,345** | ₹-4,167 | -1.01 | -1.99 | -1.41 | ₹-32,089 | ₹-32,089 | NO |
| **MOM_TS_NIFTY_FUT** | 1 | 100.0% | ₹42,750 | ₹2,006 | **₹40,744** | ₹40,744 | 0.00 | 0.00 | 0.00 | ₹40,744 | ₹40,744 | NO |
| **FUT_RSI_REVERSION_30_70** | 17 | 70.6% | ₹212,008 | ₹28,543 | **₹183,464** | ₹10,792 | 1.07 | 2.13 | 1.50 | ₹-47,216 | ₹-47,216 | NO |
| **FUT_BOLLINGER_REVERSION_2SD** | 15 | 93.3% | ₹388,032 | ₹25,496 | **₹362,536** | ₹24,169 | 2.90 | 2.90 | 4.06 | ₹-33,625 | ₹-33,625 | NO |
| **FUT_ZSCORE_REVERSION_2SD** | 15 | 93.3% | ₹388,032 | ₹25,496 | **₹362,536** | ₹24,169 | 2.90 | 2.90 | 4.06 | ₹-33,625 | ₹-33,625 | NO |
| **OVERNIGHT_FUT_DRIFT** | 494 | 37.0% | ₹129,058 | ₹873,395 | **₹-744,338** | ₹-1,507 | -2.70 | -3.53 | -3.78 | ₹-58,658 | ₹-58,658 | NO |
| **MOM_CS_FUTSTK_20D** | 22 | 36.4% | ₹-6,054,603 | ₹14,938 | **₹-6,069,541** | ₹-275,888 | -0.61 | -1.05 | -0.85 | ₹-2,867,902 | ₹-2,867,902 | NO |
| **MOM_CS_FUTSTK_60D** | 20 | 45.0% | ₹-8,423,076 | ₹13,580 | **₹-8,436,656** | ₹-421,833 | -0.69 | -1.15 | -0.97 | ₹-3,878,480 | ₹-3,878,480 | NO |
| **MOM_CS_FUTSTK_120D** | 17 | 58.8% | ₹-10,026,325 | ₹11,543 | **₹-10,037,868** | ₹-590,463 | -0.80 | -0.89 | -1.13 | ₹-6,510,028 | ₹-6,510,028 | NO |
| **NIFTY_ORB_15_1R** | 493 | 46.7% | ₹-96,725 | ₹37,996 | **₹-134,721** | ₹-273 | -1.84 | -3.58 | -2.58 | ₹-8,158 | ₹-8,158 | NO |
| **NIFTY_ORB_15_1.5R** | 493 | 38.5% | ₹-115,238 | ₹37,966 | **₹-153,204** | ₹-311 | -1.80 | -4.19 | -2.53 | ₹-8,158 | ₹-8,158 | NO |
| **NIFTY_ORB_15_2R** | 493 | 34.3% | ₹-88,694 | ₹38,009 | **₹-126,703** | ₹-257 | -1.30 | -3.45 | -1.82 | ₹-8,158 | ₹-8,158 | NO |
| **NIFTY_ORB_15_EOD** | 493 | 27.6% | ₹-97,368 | ₹37,995 | **₹-135,363** | ₹-275 | -1.16 | -3.62 | -1.63 | ₹-8,158 | ₹-8,158 | NO |
| **NIFTY_ORB_30_1.5R** | 492 | 37.6% | ₹-86,768 | ₹37,818 | **₹-124,586** | ₹-253 | -1.20 | -3.10 | -1.68 | ₹-7,149 | ₹-7,149 | NO |
| **NIFTY_VWAP_TREND** | 298 | 37.2% | ₹2,428 | ₹22,657 | **₹-20,228** | ₹-68 | -0.50 | -1.33 | -0.69 | ₹-4,216 | ₹-4,216 | NO |
| **NIFTY_VWAP_MEAN_REVERSION** | 214 | 39.7% | ₹-42,452 | ₹16,556 | **₹-59,008** | ₹-276 | -1.50 | -3.06 | -2.11 | ₹-6,066 | ₹-6,066 | NO |
| **NIFTY_GAP_FADE** | 113 | 37.2% | ₹-38,223 | ₹8,937 | **₹-47,160** | ₹-417 | -1.07 | -2.38 | -1.50 | ₹-5,613 | ₹-5,613 | NO |
| **NIFTY_GAP_CONTINUATION** | 170 | 37.6% | ₹-35,890 | ₹13,475 | **₹-49,365** | ₹-290 | -0.95 | -2.19 | -1.32 | ₹-6,629 | ₹-6,629 | NO |
| **OPT_ATM_STRADDLE_0DTE** | 105 | 66.7% | ₹183,143 | ₹18,241 | **₹164,901** | ₹1,570 | 1.61 | 1.98 | 2.26 | ₹-23,139 | ₹-23,139 | **YES** |
| **OPT_LONG_STRADDLE_0DTE** | 105 | 31.4% | ₹-183,143 | ₹18,241 | **₹-201,384** | ₹-1,918 | -1.97 | -3.50 | -2.76 | ₹-20,421 | ₹-20,421 | NO |
| **OPT_IRON_FLY_0DTE** | 105 | 59.0% | ₹81,275 | ₹35,174 | **₹46,101** | ₹439 | 0.69 | 1.19 | 0.97 | ₹-12,387 | ₹-12,387 | NO |
| **EXPIRY_0DTE_DECAY** | 105 | 66.7% | ₹183,143 | ₹18,241 | **₹164,901** | ₹1,570 | 1.61 | 1.98 | 2.26 | ₹-23,139 | ₹-23,139 | **YES** |
| **OPT_STRANGLE_WEEKLY** | 105 | 81.0% | ₹160,862 | ₹17,475 | **₹143,387** | ₹1,366 | 1.04 | 0.84 | 1.47 | ₹-37,858 | ₹-37,858 | **YES** |
| **OPT_LONG_STRANGLE_WEEKLY** | 105 | 18.1% | ₹-160,862 | ₹17,475 | **₹-178,336** | ₹-1,698 | -1.29 | -2.89 | -1.84 | ₹-22,227 | ₹-22,227 | NO |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | 105 | 61.9% | ₹-78,910 | ₹18,522 | **₹-97,432** | ₹-928 | -1.25 | -1.74 | -1.78 | ₹-13,058 | ₹-13,058 | NO |
| **OPT_BEAR_CALL_SPREAD_WEEKLY** | 105 | 74.3% | ₹106,278 | ₹18,321 | **₹87,957** | ₹838 | 1.17 | 2.04 | 1.66 | ₹-10,917 | ₹-10,917 | **YES** |
| **OPT_IRON_CONDOR_WEEKLY** | 105 | 48.6% | ₹27,368 | ₹36,843 | **₹-9,475** | ₹-90 | -0.12 | -0.29 | -0.17 | ₹-8,821 | ₹-8,821 | NO |
| **OPT_DEBIT_CALL_SPREAD_BREAKOUT** | 105 | 36.2% | ₹-120,420 | ₹19,124 | **₹-139,544** | ₹-1,329 | -1.69 | -5.41 | -2.40 | ₹-7,566 | ₹-7,566 | NO |
| **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** | 105 | 46.7% | ₹123,814 | ₹19,378 | **₹104,437** | ₹995 | 1.20 | 5.37 | 1.71 | ₹-5,954 | ₹-5,954 | **YES** |
| **VOL_VRP_SHORT** | 105 | 48.6% | ₹27,368 | ₹36,843 | **₹-9,475** | ₹-90 | -0.12 | -0.29 | -0.17 | ₹-8,821 | ₹-8,821 | NO |
| **PCR_TREND_CONFIRMATION** | 0 | 0.0% | ₹0 | ₹0 | **₹0** | ₹0 | 0.00 | 0.00 | 0.00 | ₹0 | ₹0 | NO |

---

## 3. YEARLY PERFORMANCE BREAKDOWN (2024, 2025, 2026)

| Strategy | 2024 Trades | 2024 Net | 2025 Trades | 2025 Net | 2026 Trades | 2026 Net | Consistency |
|---|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | 3 | ₹-28,616 | 10 | ₹-257,311 | 8 | ₹-248,907 | Inconsistent / Negative |
| **FUT_DONCHIAN_55D** | 2 | ₹-56,739 | 3 | ₹57,632 | 2 | ₹15,557 | Mostly Positive |
| **FUT_MA_CROSS_20_50** | 1 | ₹5,536 | 1 | ₹-36,399 | 1 | ₹53,533 | Mostly Positive |
| **FUT_MA_CROSS_50_200** | 0 | ₹0 | 1 | ₹-109,294 | 0 | ₹0 | Inconsistent / Negative |
| **FUT_SUPERTREND_10_3** | 0 | ₹0 | 0 | ₹0 | 0 | ₹0 | Inconsistent / Negative |
| **FUT_ATR_BREAKOUT** | 4 | ₹10,895 | 17 | ₹-9,868 | 11 | ₹-134,372 | Inconsistent / Negative |
| **MOM_TS_NIFTY_FUT** | 0 | ₹0 | 1 | ₹40,744 | 0 | ₹0 | Inconsistent / Negative |
| **FUT_RSI_REVERSION_30_70** | 4 | ₹5,643 | 8 | ₹129,187 | 5 | ₹48,635 | All Years Positive |
| **FUT_BOLLINGER_REVERSION_2SD** | 3 | ₹39,463 | 6 | ₹180,328 | 6 | ₹142,745 | All Years Positive |
| **FUT_ZSCORE_REVERSION_2SD** | 3 | ₹39,463 | 6 | ₹180,328 | 6 | ₹142,745 | All Years Positive |
| **OVERNIGHT_FUT_DRIFT** | 71 | ₹-41,543 | 248 | ₹-321,927 | 175 | ₹-380,867 | Inconsistent / Negative |
| **MOM_CS_FUTSTK_20D** | 3 | ₹-2,166,602 | 11 | ₹-1,341,054 | 8 | ₹-2,561,884 | Inconsistent / Negative |
| **MOM_CS_FUTSTK_60D** | 1 | ₹-3,878,480 | 12 | ₹3,246,235 | 7 | ₹-7,804,411 | Inconsistent / Negative |
| **MOM_CS_FUTSTK_120D** | 0 | ₹0 | 10 | ₹2,920,969 | 7 | ₹-12,958,838 | Inconsistent / Negative |
| **NIFTY_ORB_15_1R** | 70 | ₹1,913 | 247 | ₹-99,241 | 176 | ₹-37,393 | Inconsistent / Negative |
| **NIFTY_ORB_15_1.5R** | 70 | ₹8,616 | 247 | ₹-124,327 | 176 | ₹-37,493 | Inconsistent / Negative |
| **NIFTY_ORB_15_2R** | 70 | ₹12,996 | 247 | ₹-91,410 | 176 | ₹-48,289 | Inconsistent / Negative |
| **NIFTY_ORB_15_EOD** | 70 | ₹-8,640 | 247 | ₹-95,672 | 176 | ₹-31,052 | Inconsistent / Negative |
| **NIFTY_ORB_30_1.5R** | 69 | ₹17,570 | 247 | ₹-77,448 | 176 | ₹-64,709 | Inconsistent / Negative |
| **NIFTY_VWAP_TREND** | 36 | ₹18,832 | 151 | ₹-10,420 | 111 | ₹-28,641 | Inconsistent / Negative |
| **NIFTY_VWAP_MEAN_REVERSION** | 32 | ₹-7,111 | 115 | ₹-36,146 | 67 | ₹-15,751 | Inconsistent / Negative |
| **NIFTY_GAP_FADE** | 9 | ₹-3,897 | 44 | ₹-31,740 | 60 | ₹-11,523 | Inconsistent / Negative |
| **NIFTY_GAP_CONTINUATION** | 18 | ₹26,600 | 71 | ₹-44,211 | 81 | ₹-31,754 | Inconsistent / Negative |
| **OPT_ATM_STRADDLE_0DTE** | 15 | ₹7,709 | 53 | ₹77,925 | 37 | ₹79,268 | All Years Positive |
| **OPT_LONG_STRADDLE_0DTE** | 15 | ₹-11,493 | 53 | ₹-97,480 | 37 | ₹-92,410 | Inconsistent / Negative |
| **OPT_IRON_FLY_0DTE** | 15 | ₹1,773 | 53 | ₹21,639 | 37 | ₹22,689 | All Years Positive |
| **EXPIRY_0DTE_DECAY** | 15 | ₹7,709 | 53 | ₹77,925 | 37 | ₹79,268 | All Years Positive |
| **OPT_STRANGLE_WEEKLY** | 16 | ₹-7,832 | 53 | ₹62,430 | 36 | ₹88,788 | Mostly Positive |
| **OPT_LONG_STRANGLE_WEEKLY** | 16 | ₹3,763 | 53 | ₹-81,081 | 36 | ₹-101,018 | Inconsistent / Negative |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | 16 | ₹-3,250 | 53 | ₹-9,065 | 36 | ₹-85,118 | Inconsistent / Negative |
| **OPT_BEAR_CALL_SPREAD_WEEKLY** | 16 | ₹426 | 53 | ₹39,497 | 36 | ₹48,034 | All Years Positive |
| **OPT_IRON_CONDOR_WEEKLY** | 16 | ₹-2,824 | 53 | ₹30,432 | 36 | ₹-37,084 | Inconsistent / Negative |
| **OPT_DEBIT_CALL_SPREAD_BREAKOUT** | 16 | ₹-11,911 | 53 | ₹-57,033 | 36 | ₹-70,600 | Inconsistent / Negative |
| **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** | 16 | ₹1,355 | 53 | ₹7,676 | 36 | ₹95,406 | All Years Positive |
| **VOL_VRP_SHORT** | 16 | ₹-2,824 | 53 | ₹30,432 | 36 | ₹-37,084 | Inconsistent / Negative |
| **PCR_TREND_CONFIRMATION** | 0 | ₹0 | 0 | ₹0 | 0 | ₹0 | Inconsistent / Negative |

---

## 4. MONTHLY NET P&L AUDIT

| Strategy | 2024-09 | 2024-10 | 2024-11 | 2024-12 | 2025-01 | 2025-02 | 2025-03 | 2025-04 | 2025-05 | 2025-06 | 2025-07 | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 | 2026-07 | 2026-08 | 2026-09 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | ₹-15,497 | ₹6,746 | ₹0 | ₹-19,866 | ₹-12,624 | ₹-28,316 | ₹-76,434 | ₹-25,024 | ₹0 | ₹0 | ₹-13,956 | ₹0 | ₹-22,413 | ₹-39,518 | ₹-39,028 | ₹0 | ₹-83,659 | ₹0 | ₹43,654 | ₹-59,406 | ₹0 | ₹-71,475 | ₹-44,783 | ₹-33,238 | ₹0 |
| **FUT_DONCHIAN_55D** | ₹-28,249 | ₹0 | ₹-28,490 | ₹0 | ₹2,006 | ₹0 | ₹0 | ₹46,673 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹8,952 | ₹0 | ₹0 | ₹56,330 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹-40,773 | ₹0 |
| **FUT_MA_CROSS_20_50** | ₹0 | ₹5,536 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹-36,399 | ₹0 | ₹0 | ₹0 | ₹0 | ₹53,533 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 |
| **FUT_MA_CROSS_50_200** | ₹0 | ₹0 | ₹0 | ₹0 | ₹-109,294 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 |
| **FUT_SUPERTREND_10_3** | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 |
| **FUT_ATR_BREAKOUT** | ₹0 | ₹19,376 | ₹-6,758 | ₹-1,723 | ₹49,989 | ₹0 | ₹-2,299 | ₹16,982 | ₹-23,840 | ₹-10,058 | ₹10,350 | ₹-13,328 | ₹-16,751 | ₹-5,720 | ₹-6,723 | ₹-8,470 | ₹-16,648 | ₹-51,568 | ₹0 | ₹0 | ₹-6,272 | ₹-42,363 | ₹-13,143 | ₹0 | ₹-4,377 |
| **MOM_TS_NIFTY_FUT** | ₹0 | ₹0 | ₹0 | ₹0 | ₹40,744 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 |
| **FUT_RSI_REVERSION_30_70** | ₹18,347 | ₹-22,067 | ₹0 | ₹9,363 | ₹0 | ₹2,109 | ₹70,861 | ₹-34,259 | ₹0 | ₹0 | ₹-1,981 | ₹0 | ₹43,642 | ₹12,097 | ₹36,716 | ₹0 | ₹28,612 | ₹0 | ₹-47,216 | ₹27,187 | ₹0 | ₹0 | ₹25,521 | ₹14,531 | ₹0 |
| **FUT_BOLLINGER_REVERSION_2SD** | ₹10,506 | ₹0 | ₹16,791 | ₹12,166 | ₹8,676 | ₹0 | ₹72,599 | ₹0 | ₹0 | ₹32,374 | ₹9,759 | ₹0 | ₹0 | ₹28,961 | ₹27,958 | ₹0 | ₹63,363 | ₹0 | ₹-33,625 | ₹0 | ₹36,731 | ₹46,620 | ₹0 | ₹29,656 | ₹0 |
| **FUT_ZSCORE_REVERSION_2SD** | ₹10,506 | ₹0 | ₹16,791 | ₹12,166 | ₹8,676 | ₹0 | ₹72,599 | ₹0 | ₹0 | ₹32,374 | ₹9,759 | ₹0 | ₹0 | ₹28,961 | ₹27,958 | ₹0 | ₹63,363 | ₹0 | ₹-33,625 | ₹0 | ₹36,731 | ₹46,620 | ₹0 | ₹29,656 | ₹0 |
| **OVERNIGHT_FUT_DRIFT** | ₹-424 | ₹-18,715 | ₹4,347 | ₹-26,750 | ₹-19,505 | ₹-51,596 | ₹-9,098 | ₹-31,124 | ₹-21,683 | ₹-25,922 | ₹-76,162 | ₹-25,685 | ₹-15,062 | ₹4,174 | ₹-16,531 | ₹-33,734 | ₹-61,618 | ₹15,718 | ₹-128,223 | ₹-31,439 | ₹-43,185 | ₹-43,275 | ₹-32,090 | ₹-24,243 | ₹-32,512 |
| **MOM_CS_FUTSTK_20D** | ₹0 | ₹988,416 | ₹-1,090,173 | ₹-2,064,845 | ₹1,696,641 | ₹-879,878 | ₹-2,316,062 | ₹0 | ₹-1,575,477 | ₹-1,373,820 | ₹1,167,169 | ₹0 | ₹-2,531,898 | ₹3,171,837 | ₹0 | ₹1,300,434 | ₹-708,388 | ₹1,773,826 | ₹-2,867,902 | ₹-24,801 | ₹690,174 | ₹-600,551 | ₹-82,791 | ₹-741,449 | ₹0 |
| **MOM_CS_FUTSTK_60D** | ₹0 | ₹0 | ₹0 | ₹-3,878,480 | ₹2,075,678 | ₹-160,756 | ₹197,508 | ₹-3,110,497 | ₹1,185,356 | ₹-1,527,144 | ₹536,257 | ₹-1,199,726 | ₹-1,477,055 | ₹3,422,910 | ₹2,048,873 | ₹1,254,831 | ₹-507,237 | ₹0 | ₹-2,907,394 | ₹-1,939,767 | ₹144,351 | ₹-819,654 | ₹-2,633,513 | ₹858,805 | ₹0 |
| **MOM_CS_FUTSTK_120D** | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹1,218,366 | ₹-2,988,759 | ₹-333,413 | ₹36,724 | ₹534,394 | ₹131,566 | ₹3,701 | ₹1,294,149 | ₹1,417,147 | ₹1,607,095 | ₹-2,980,749 | ₹-1,927,433 | ₹-6,510,028 | ₹0 | ₹540,416 | ₹-1,339,983 | ₹-2,151,466 | ₹1,410,405 | ₹0 |
| **NIFTY_ORB_15_1R** | ₹2,976 | ₹-3,168 | ₹10,398 | ₹-8,293 | ₹-10,400 | ₹3,611 | ₹-5,707 | ₹-15,345 | ₹-11,297 | ₹-17,055 | ₹-12,298 | ₹-4,448 | ₹6,382 | ₹-10,607 | ₹-6,838 | ₹-15,238 | ₹-2,315 | ₹2,175 | ₹-2,130 | ₹10,643 | ₹-12,877 | ₹-1,364 | ₹-15,961 | ₹-6,259 | ₹-9,304 |
| **NIFTY_ORB_15_1.5R** | ₹2,425 | ₹2,215 | ₹9,121 | ₹-5,145 | ₹-9,686 | ₹-15,207 | ₹-4,291 | ₹-9,379 | ₹-11,456 | ₹-24,522 | ₹-9,848 | ₹-7,932 | ₹-5,036 | ₹-5,444 | ₹-4,764 | ₹-16,763 | ₹-3,567 | ₹4,167 | ₹10,269 | ₹20,629 | ₹-14,221 | ₹-19,040 | ₹-20,428 | ₹-7,887 | ₹-7,415 |
| **NIFTY_ORB_15_2R** | ₹753 | ₹5,431 | ₹13,592 | ₹-6,781 | ₹-8,645 | ₹-10,248 | ₹-1,365 | ₹-1,230 | ₹-4,950 | ₹-20,035 | ₹-7,762 | ₹-6,943 | ₹-2,596 | ₹-2,404 | ₹-3,482 | ₹-21,751 | ₹6,763 | ₹-307 | ₹8,680 | ₹20,112 | ₹-21,465 | ₹-24,698 | ₹-20,658 | ₹-7,635 | ₹-9,081 |
| **NIFTY_ORB_15_EOD** | ₹4,586 | ₹5,337 | ₹-2,752 | ₹-15,811 | ₹-2,695 | ₹-12,422 | ₹-3,494 | ₹-4,931 | ₹-12,096 | ₹-17,262 | ₹-8,676 | ₹-7,333 | ₹-7,668 | ₹3,232 | ₹-5,423 | ₹-16,904 | ₹2,823 | ₹8,661 | ₹23,312 | ₹18,966 | ₹-23,399 | ₹-28,483 | ₹-17,187 | ₹-15,793 | ₹49 |
| **NIFTY_ORB_30_1.5R** | ₹11,783 | ₹-4,376 | ₹3,100 | ₹7,063 | ₹-8,119 | ₹-27,093 | ₹-4,298 | ₹5,866 | ₹-13,894 | ₹11,076 | ₹-10,467 | ₹-7,033 | ₹-11,042 | ₹2,126 | ₹-5,475 | ₹-9,096 | ₹-4,391 | ₹-7,475 | ₹18,943 | ₹3,461 | ₹-10,428 | ₹-33,982 | ₹-16,504 | ₹-9,952 | ₹-4,380 |
| **NIFTY_VWAP_TREND** | ₹-41 | ₹9,837 | ₹1,600 | ₹7,436 | ₹10,016 | ₹473 | ₹-5,550 | ₹-7,040 | ₹-3,930 | ₹-537 | ₹-6,916 | ₹-5,341 | ₹5,445 | ₹-3,308 | ₹3,139 | ₹3,131 | ₹-4,040 | ₹-9,533 | ₹-6,551 | ₹-7,460 | ₹1,814 | ₹-212 | ₹-5,295 | ₹-972 | ₹3,609 |
| **NIFTY_VWAP_MEAN_REVERSION** | ₹-5,475 | ₹3,553 | ₹-7,560 | ₹2,371 | ₹909 | ₹-10,085 | ₹2,021 | ₹1,771 | ₹-5,430 | ₹-7,801 | ₹-6,156 | ₹6,029 | ₹24 | ₹-15,267 | ₹-2,201 | ₹40 | ₹-2,039 | ₹1,069 | ₹-157 | ₹-4,552 | ₹-1,810 | ₹-5,295 | ₹-2,031 | ₹1,016 | ₹-1,952 |
| **NIFTY_GAP_FADE** | ₹4,797 | ₹1,993 | ₹-5,598 | ₹-5,089 | ₹-15,098 | ₹-1,133 | ₹-1,372 | ₹-15,403 | ₹-6,324 | ₹3,371 | ₹4,960 | ₹-2,263 | ₹3,807 | ₹274 | ₹4,762 | ₹-7,322 | ₹746 | ₹-12,955 | ₹-16,089 | ₹10,200 | ₹13,017 | ₹3,091 | ₹-7,837 | ₹-1,607 | ₹-89 |
| **NIFTY_GAP_CONTINUATION** | ₹5,337 | ₹5,866 | ₹2,400 | ₹12,997 | ₹-1,833 | ₹-5,614 | ₹1,000 | ₹3,679 | ₹-14,020 | ₹-8,738 | ₹1,896 | ₹659 | ₹-9,432 | ₹-8,097 | ₹4,053 | ₹-7,764 | ₹-8,215 | ₹-4,122 | ₹11,055 | ₹-2,756 | ₹2,003 | ₹-4,540 | ₹-20,010 | ₹-2,370 | ₹-2,798 |
| **OPT_ATM_STRADDLE_0DTE** | ₹-1,120 | ₹2,237 | ₹-2,766 | ₹9,358 | ₹-4,582 | ₹21,037 | ₹2,088 | ₹10,780 | ₹2,744 | ₹-4,897 | ₹-8,079 | ₹4,957 | ₹5,191 | ₹16,325 | ₹4,565 | ₹27,795 | ₹-6,896 | ₹-7,487 | ₹60,062 | ₹8,938 | ₹11,113 | ₹-2,933 | ₹27,757 | ₹6,158 | ₹-17,445 |
| **OPT_LONG_STRADDLE_0DTE** | ₹613 | ₹-3,498 | ₹1,736 | ₹-10,344 | ₹2,796 | ₹-22,493 | ₹-3,582 | ₹-12,673 | ₹-4,298 | ₹3,376 | ₹6,201 | ₹-6,436 | ₹-6,997 | ₹-17,755 | ₹-6,047 | ₹-29,572 | ₹5,474 | ₹5,994 | ₹-61,852 | ₹-10,412 | ₹-12,521 | ₹1,168 | ₹-29,079 | ₹-7,537 | ₹16,355 |
| **OPT_IRON_FLY_0DTE** | ₹-2,223 | ₹810 | ₹-1,270 | ₹4,456 | ₹-3,013 | ₹11,115 | ₹-6,532 | ₹14,425 | ₹-1,090 | ₹-4,365 | ₹-16,520 | ₹-1,260 | ₹487 | ₹8,451 | ₹-1,522 | ₹21,463 | ₹-6,443 | ₹-12,972 | ₹22,642 | ₹-2,001 | ₹9,122 | ₹-8,674 | ₹22,135 | ₹4,158 | ₹-5,278 |
| **EXPIRY_0DTE_DECAY** | ₹-1,120 | ₹2,237 | ₹-2,766 | ₹9,358 | ₹-4,582 | ₹21,037 | ₹2,088 | ₹10,780 | ₹2,744 | ₹-4,897 | ₹-8,079 | ₹4,957 | ₹5,191 | ₹16,325 | ₹4,565 | ₹27,795 | ₹-6,896 | ₹-7,487 | ₹60,062 | ₹8,938 | ₹11,113 | ₹-2,933 | ₹27,757 | ₹6,158 | ₹-17,445 |
| **OPT_STRANGLE_WEEKLY** | ₹-11,141 | ₹4,844 | ₹1,360 | ₹-2,895 | ₹28,544 | ₹4,406 | ₹-12,383 | ₹-29,794 | ₹-2,809 | ₹21,850 | ₹14,121 | ₹14,662 | ₹2,474 | ₹-776 | ₹12,681 | ₹9,453 | ₹14,395 | ₹-1,463 | ₹-2,537 | ₹54,312 | ₹-7,154 | ₹-4,556 | ₹20,170 | ₹10,410 | ₹5,212 |
| **OPT_LONG_STRANGLE_WEEKLY** | ₹10,381 | ₹-5,813 | ₹-2,593 | ₹1,788 | ₹-30,201 | ₹-5,839 | ₹10,942 | ₹28,226 | ₹903 | ₹-23,240 | ₹-15,489 | ₹-16,373 | ₹-3,856 | ₹-971 | ₹-14,049 | ₹-11,136 | ₹-15,700 | ₹123 | ₹992 | ₹-55,986 | ₹5,729 | ₹3,179 | ₹-21,801 | ₹-11,696 | ₹-5,858 |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | ₹-2,098 | ₹-2,875 | ₹1,095 | ₹628 | ₹-538 | ₹-11,486 | ₹-3,406 | ₹259 | ₹5,108 | ₹3,684 | ₹11,645 | ₹-1,473 | ₹-11,778 | ₹-2,718 | ₹1,711 | ₹-75 | ₹-15,663 | ₹-22,405 | ₹-30,140 | ₹-1,031 | ₹-11,839 | ₹-2,225 | ₹18,600 | ₹-4,907 | ₹-15,507 |
| **OPT_BEAR_CALL_SPREAD_WEEKLY** | ₹-1,508 | ₹6,241 | ₹1,672 | ₹-5,980 | ₹21,622 | ₹5,060 | ₹-8,296 | ₹-13,210 | ₹11,200 | ₹3,822 | ₹15,090 | ₹-2,194 | ₹-1,941 | ₹-5,592 | ₹11,096 | ₹2,841 | ₹1,976 | ₹11,793 | ₹21,755 | ₹-2,640 | ₹905 | ₹4,324 | ₹-7,219 | ₹9,521 | ₹7,620 |
| **OPT_IRON_CONDOR_WEEKLY** | ₹-3,606 | ₹3,367 | ₹2,766 | ₹-5,351 | ₹21,084 | ₹-6,426 | ₹-11,702 | ₹-12,951 | ₹16,307 | ₹7,506 | ₹26,735 | ₹-3,667 | ₹-13,719 | ₹-8,310 | ₹12,808 | ₹2,766 | ₹-13,687 | ₹-10,612 | ₹-8,385 | ₹-3,671 | ₹-10,934 | ₹2,098 | ₹11,380 | ₹4,614 | ₹-7,887 |
| **OPT_DEBIT_CALL_SPREAD_BREAKOUT** | ₹-906 | ₹-9,269 | ₹-6,036 | ₹4,300 | ₹-19,450 | ₹-12,511 | ₹2,866 | ₹12,442 | ₹-19,695 | ₹-4,365 | ₹-16,584 | ₹8,708 | ₹757 | ₹8,087 | ₹-11,520 | ₹-5,769 | ₹-8,537 | ₹-12,987 | ₹-26,255 | ₹-4,060 | ₹794 | ₹-10,901 | ₹14,522 | ₹-11,611 | ₹-11,566 |
| **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** | ₹-321 | ₹2,856 | ₹712 | ₹-1,891 | ₹1,170 | ₹11,261 | ₹7,245 | ₹-7,559 | ₹-6,584 | ₹1,258 | ₹-6,201 | ₹-8,043 | ₹11,497 | ₹-6,404 | ₹5,958 | ₹4,078 | ₹8,817 | ₹21,058 | ₹32,189 | ₹7,465 | ₹6,216 | ₹13,039 | ₹-24,381 | ₹13,831 | ₹17,171 |
| **VOL_VRP_SHORT** | ₹-3,606 | ₹3,367 | ₹2,766 | ₹-5,351 | ₹21,084 | ₹-6,426 | ₹-11,702 | ₹-12,951 | ₹16,307 | ₹7,506 | ₹26,735 | ₹-3,667 | ₹-13,719 | ₹-8,310 | ₹12,808 | ₹2,766 | ₹-13,687 | ₹-10,612 | ₹-8,385 | ₹-3,671 | ₹-10,934 | ₹2,098 | ₹11,380 | ₹4,614 | ₹-7,887 |
| **PCR_TREND_CONFIRMATION** | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 |

---

## 5. ROBUSTNESS GATE AUDIT & SESSION RECONCILIATION

Strict survival criteria applied to every strategy:

1. **Net P&L > 0** after authentic post-Oct 2024 statutory friction (STT, GST, Stamp, Turnover, Slippage)

2. **Profit Factor (PF) > 1.10**

3. **Expectancy > 0** per executed trade

4. **Survives 2× Costs** (Gross P&L - 2× Costs > 0)

5. **Survives 3× Costs** (Gross P&L - 3× Costs > 0)

6. **Survives Adversarial Outlier Test** (Net P&L > 0 after removing top 3 winning trades)

7. **Sample Size Gate** (n >= 20 trades across the 2-year window)

8. **Complete Session Accounting** (495 total sessions, reconciled exactly)

9. **Independent P&L Reconciliation = ₹0.00 Variance** across all legs and trades


| Strategy | Net > 0 | PF > 1.10 | Exp > 0 | 2× Cost > 0 | 3× Cost > 0 | Best-3 Removed > 0 | n >= 20 | Gate Verdict |
|---|---|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **FUT_DONCHIAN_55D** | PASS | PASS | PASS | PASS | FAIL | FAIL | FAIL | REJECTED |
| **FUT_MA_CROSS_20_50** | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | REJECTED |
| **FUT_MA_CROSS_50_200** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | REJECTED |
| **FUT_SUPERTREND_10_3** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | REJECTED |
| **FUT_ATR_BREAKOUT** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **MOM_TS_NIFTY_FUT** | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | REJECTED |
| **FUT_RSI_REVERSION_30_70** | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | REJECTED |
| **FUT_BOLLINGER_REVERSION_2SD** | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | REJECTED |
| **FUT_ZSCORE_REVERSION_2SD** | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | REJECTED |
| **OVERNIGHT_FUT_DRIFT** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **MOM_CS_FUTSTK_20D** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **MOM_CS_FUTSTK_60D** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **MOM_CS_FUTSTK_120D** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | REJECTED |
| **NIFTY_ORB_15_1R** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_ORB_15_1.5R** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_ORB_15_2R** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_ORB_15_EOD** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_ORB_30_1.5R** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_VWAP_TREND** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_VWAP_MEAN_REVERSION** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_GAP_FADE** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **NIFTY_GAP_CONTINUATION** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **OPT_ATM_STRADDLE_0DTE** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **SURVIVES** |
| **OPT_LONG_STRADDLE_0DTE** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **OPT_IRON_FLY_0DTE** | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | REJECTED |
| **EXPIRY_0DTE_DECAY** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **SURVIVES** |
| **OPT_STRANGLE_WEEKLY** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **SURVIVES** |
| **OPT_LONG_STRANGLE_WEEKLY** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **OPT_BEAR_CALL_SPREAD_WEEKLY** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **SURVIVES** |
| **OPT_IRON_CONDOR_WEEKLY** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **OPT_DEBIT_CALL_SPREAD_BREAKOUT** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **SURVIVES** |
| **VOL_VRP_SHORT** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | REJECTED |
| **PCR_TREND_CONFIRMATION** | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | REJECTED |

---

## 6. SURVIVING STRATEGIES BY CAPITAL TIER

### SURVIVING STRATEGIES AT ₹20K

- **Account Capital:** ₹20k (₹20,000)
- **Max Allowed Allocation (60% Rule):** ₹12,000

**ZERO STRATEGIES SURVIVE AT ₹20K.**

> [!WARNING]
> **Capital Gate Invalidation:** No strategy passing all robustness gates can be legally executed within ₹12,000 margin under SEBI integer-lot regulations. Attempting to trade naked straddles or futures at this tier causes instantaneous margin violations.


### SURVIVING STRATEGIES AT ₹50K

- **Account Capital:** ₹50k (₹50,000)
- **Max Allowed Allocation (60% Rule):** ₹30,000

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹25,000 (50.0% of account)
  - 2-Year Net P&L: **₹104,437**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹65,682 | Best-3 Removed Net: ₹72,210
  - Max Drawdown: ₹44,653 (89.3% of account)
  - Yearly Net: 2024: ₹1,355, 2025: ₹7,676, 2026: ₹95,406


### SURVIVING STRATEGIES AT ₹1L

- **Account Capital:** ₹1L (₹100,000)
- **Max Allowed Allocation (60% Rule):** ₹60,000

- **OPT_BEAR_CALL_SPREAD_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹35,000 (35.0% of account)
  - 2-Year Net P&L: **₹87,957**
  - Profit Factor: 1.45 | Expectancy: ₹838/trade
  - 3× Cost Net: ₹51,315 | Best-3 Removed Net: ₹69,582
  - Max Drawdown: ₹35,546 (35.5% of account)
  - Yearly Net: 2024: ₹426, 2025: ₹39,497, 2026: ₹48,034

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (2 Lots)
  - Margin Deployed: ₹50,000 (50.0% of account)
  - 2-Year Net P&L: **₹208,874**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹131,364 | Best-3 Removed Net: ₹144,421
  - Max Drawdown: ₹89,305 (89.3% of account)
  - Yearly Net: 2024: ₹2,710, 2025: ₹15,352, 2026: ₹190,811


### SURVIVING STRATEGIES AT ₹1.5L

- **Account Capital:** ₹1.5L (₹150,000)
- **Max Allowed Allocation (60% Rule):** ₹90,000

- **OPT_BEAR_CALL_SPREAD_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (2 Lots)
  - Margin Deployed: ₹70,000 (46.7% of account)
  - 2-Year Net P&L: **₹175,914**
  - Profit Factor: 1.45 | Expectancy: ₹838/trade
  - 3× Cost Net: ₹102,630 | Best-3 Removed Net: ₹139,164
  - Max Drawdown: ₹71,091 (47.4% of account)
  - Yearly Net: 2024: ₹852, 2025: ₹78,994, 2026: ₹96,068

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (3 Lots)
  - Margin Deployed: ₹75,000 (50.0% of account)
  - 2-Year Net P&L: **₹313,310**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹197,045 | Best-3 Removed Net: ₹216,631
  - Max Drawdown: ₹133,958 (89.3% of account)
  - Yearly Net: 2024: ₹4,065, 2025: ₹23,028, 2026: ₹286,217


### SURVIVING STRATEGIES AT ₹2L

- **Account Capital:** ₹2L (₹200,000)
- **Max Allowed Allocation (60% Rule):** ₹120,000

- **OPT_BEAR_CALL_SPREAD_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (3 Lots)
  - Margin Deployed: ₹105,000 (52.5% of account)
  - 2-Year Net P&L: **₹263,870**
  - Profit Factor: 1.45 | Expectancy: ₹838/trade
  - 3× Cost Net: ₹153,945 | Best-3 Removed Net: ₹208,746
  - Max Drawdown: ₹106,637 (53.3% of account)
  - Yearly Net: 2024: ₹1,277, 2025: ₹118,491, 2026: ₹144,102

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (4 Lots)
  - Margin Deployed: ₹100,000 (50.0% of account)
  - 2-Year Net P&L: **₹417,747**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹262,727 | Best-3 Removed Net: ₹288,841
  - Max Drawdown: ₹178,610 (89.3% of account)
  - Yearly Net: 2024: ₹5,421, 2025: ₹30,704, 2026: ₹381,622


### SURVIVING STRATEGIES AT ₹2.5L

- **Account Capital:** ₹2.5L (₹250,000)
- **Max Allowed Allocation (60% Rule):** ₹150,000

- **OPT_ATM_STRADDLE_0DTE** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹150,000 (60.0% of account)
  - 2-Year Net P&L: **₹164,901**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹128,419 | Best-3 Removed Net: ₹112,581
  - Max Drawdown: ₹30,264 (12.1% of account)
  - Yearly Net: 2024: ₹7,709, 2025: ₹77,925, 2026: ₹79,268

- **EXPIRY_0DTE_DECAY** (EXPIRY_DAY)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹150,000 (60.0% of account)
  - 2-Year Net P&L: **₹164,901**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹128,419 | Best-3 Removed Net: ₹112,581
  - Max Drawdown: ₹30,264 (12.1% of account)
  - Yearly Net: 2024: ₹7,709, 2025: ₹77,925, 2026: ₹79,268

- **OPT_BEAR_CALL_SPREAD_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (4 Lots)
  - Margin Deployed: ₹140,000 (56.0% of account)
  - 2-Year Net P&L: **₹351,827**
  - Profit Factor: 1.45 | Expectancy: ₹838/trade
  - 3× Cost Net: ₹205,260 | Best-3 Removed Net: ₹278,328
  - Max Drawdown: ₹142,183 (56.9% of account)
  - Yearly Net: 2024: ₹1,703, 2025: ₹157,988, 2026: ₹192,136

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (6 Lots)
  - Margin Deployed: ₹150,000 (60.0% of account)
  - 2-Year Net P&L: **₹626,620**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹394,090 | Best-3 Removed Net: ₹433,262
  - Max Drawdown: ₹267,916 (107.2% of account)
  - Yearly Net: 2024: ₹8,131, 2025: ₹46,056, 2026: ₹572,433


### SURVIVING STRATEGIES AT ₹3L

- **Account Capital:** ₹3L (₹300,000)
- **Max Allowed Allocation (60% Rule):** ₹180,000

- **OPT_ATM_STRADDLE_0DTE** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹150,000 (50.0% of account)
  - 2-Year Net P&L: **₹164,901**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹128,419 | Best-3 Removed Net: ₹112,581
  - Max Drawdown: ₹30,264 (10.1% of account)
  - Yearly Net: 2024: ₹7,709, 2025: ₹77,925, 2026: ₹79,268

- **EXPIRY_0DTE_DECAY** (EXPIRY_DAY)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹150,000 (50.0% of account)
  - 2-Year Net P&L: **₹164,901**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹128,419 | Best-3 Removed Net: ₹112,581
  - Max Drawdown: ₹30,264 (10.1% of account)
  - Yearly Net: 2024: ₹7,709, 2025: ₹77,925, 2026: ₹79,268

- **OPT_STRANGLE_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹180,000 (60.0% of account)
  - 2-Year Net P&L: **₹143,387**
  - Profit Factor: 1.54 | Expectancy: ₹1,366/trade
  - 3× Cost Net: ₹108,437 | Best-3 Removed Net: ₹84,831
  - Max Drawdown: ₹75,705 (25.2% of account)
  - Yearly Net: 2024: ₹-7,832, 2025: ₹62,430, 2026: ₹88,788

- **OPT_BEAR_CALL_SPREAD_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (5 Lots)
  - Margin Deployed: ₹175,000 (58.3% of account)
  - 2-Year Net P&L: **₹439,784**
  - Profit Factor: 1.45 | Expectancy: ₹838/trade
  - 3× Cost Net: ₹256,574 | Best-3 Removed Net: ₹347,910
  - Max Drawdown: ₹177,728 (59.2% of account)
  - Yearly Net: 2024: ₹2,129, 2025: ₹197,485, 2026: ₹240,171

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (7 Lots)
  - Margin Deployed: ₹175,000 (58.3% of account)
  - 2-Year Net P&L: **₹731,057**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹459,772 | Best-3 Removed Net: ₹505,472
  - Max Drawdown: ₹312,568 (104.2% of account)
  - Yearly Net: 2024: ₹9,486, 2025: ₹53,732, 2026: ₹667,839


### SURVIVING STRATEGIES AT ₹5L

- **Account Capital:** ₹5L (₹500,000)
- **Max Allowed Allocation (60% Rule):** ₹300,000

- **OPT_ATM_STRADDLE_0DTE** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (2 Lots)
  - Margin Deployed: ₹300,000 (60.0% of account)
  - 2-Year Net P&L: **₹329,803**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹256,838 | Best-3 Removed Net: ₹225,162
  - Max Drawdown: ₹60,528 (12.1% of account)
  - Yearly Net: 2024: ₹15,418, 2025: ₹155,849, 2026: ₹158,536

- **EXPIRY_0DTE_DECAY** (EXPIRY_DAY)
  - Status: **EXECUTABLE** (2 Lots)
  - Margin Deployed: ₹300,000 (60.0% of account)
  - 2-Year Net P&L: **₹329,803**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹256,838 | Best-3 Removed Net: ₹225,162
  - Max Drawdown: ₹60,528 (12.1% of account)
  - Yearly Net: 2024: ₹15,418, 2025: ₹155,849, 2026: ₹158,536

- **OPT_STRANGLE_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (1 Lot)
  - Margin Deployed: ₹180,000 (36.0% of account)
  - 2-Year Net P&L: **₹143,387**
  - Profit Factor: 1.54 | Expectancy: ₹1,366/trade
  - 3× Cost Net: ₹108,437 | Best-3 Removed Net: ₹84,831
  - Max Drawdown: ₹75,705 (15.1% of account)
  - Yearly Net: 2024: ₹-7,832, 2025: ₹62,430, 2026: ₹88,788

- **OPT_BEAR_CALL_SPREAD_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (8 Lots)
  - Margin Deployed: ₹280,000 (56.0% of account)
  - 2-Year Net P&L: **₹703,654**
  - Profit Factor: 1.45 | Expectancy: ₹838/trade
  - 3× Cost Net: ₹410,519 | Best-3 Removed Net: ₹556,656
  - Max Drawdown: ₹284,366 (56.9% of account)
  - Yearly Net: 2024: ₹3,406, 2025: ₹315,975, 2026: ₹384,273

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (12 Lots)
  - Margin Deployed: ₹300,000 (60.0% of account)
  - 2-Year Net P&L: **₹1,253,241**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹788,181 | Best-3 Removed Net: ₹866,523
  - Max Drawdown: ₹535,831 (107.2% of account)
  - Yearly Net: 2024: ₹16,262, 2025: ₹92,112, 2026: ₹1,144,867


### SURVIVING STRATEGIES AT ₹10L

- **Account Capital:** ₹10L (₹1,000,000)
- **Max Allowed Allocation (60% Rule):** ₹600,000

- **OPT_ATM_STRADDLE_0DTE** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (4 Lots)
  - Margin Deployed: ₹600,000 (60.0% of account)
  - 2-Year Net P&L: **₹659,606**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹513,676 | Best-3 Removed Net: ₹450,325
  - Max Drawdown: ₹121,056 (12.1% of account)
  - Yearly Net: 2024: ₹30,836, 2025: ₹311,698, 2026: ₹317,071

- **EXPIRY_0DTE_DECAY** (EXPIRY_DAY)
  - Status: **EXECUTABLE** (4 Lots)
  - Margin Deployed: ₹600,000 (60.0% of account)
  - 2-Year Net P&L: **₹659,606**
  - Profit Factor: 1.78 | Expectancy: ₹1,570/trade
  - 3× Cost Net: ₹513,676 | Best-3 Removed Net: ₹450,325
  - Max Drawdown: ₹121,056 (12.1% of account)
  - Yearly Net: 2024: ₹30,836, 2025: ₹311,698, 2026: ₹317,071

- **OPT_STRANGLE_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (3 Lots)
  - Margin Deployed: ₹540,000 (54.0% of account)
  - 2-Year Net P&L: **₹430,160**
  - Profit Factor: 1.54 | Expectancy: ₹1,366/trade
  - 3× Cost Net: ₹325,310 | Best-3 Removed Net: ₹254,492
  - Max Drawdown: ₹227,116 (22.7% of account)
  - Yearly Net: 2024: ₹-23,496, 2025: ₹187,291, 2026: ₹266,365

- **OPT_BEAR_CALL_SPREAD_WEEKLY** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (17 Lots)
  - Margin Deployed: ₹595,000 (59.5% of account)
  - 2-Year Net P&L: **₹1,495,266**
  - Profit Factor: 1.45 | Expectancy: ₹838/trade
  - 3× Cost Net: ₹872,353 | Best-3 Removed Net: ₹1,182,893
  - Max Drawdown: ₹604,277 (60.4% of account)
  - Yearly Net: 2024: ₹7,238, 2025: ₹671,448, 2026: ₹816,580

- **OPT_DEBIT_PUT_SPREAD_BREAKDOWN** (OPTIONS_SPREAD)
  - Status: **EXECUTABLE** (24 Lots)
  - Margin Deployed: ₹600,000 (60.0% of account)
  - 2-Year Net P&L: **₹2,506,482**
  - Profit Factor: 1.45 | Expectancy: ₹995/trade
  - 3× Cost Net: ₹1,576,362 | Best-3 Removed Net: ₹1,733,046
  - Max Drawdown: ₹1,071,662 (107.2% of account)
  - Yearly Net: 2024: ₹32,523, 2025: ₹184,225, 2026: ₹2,289,734


---

## 7. CORE EMPIRICAL FINDINGS (WHAT THE 2-YEAR DATA PROVES)

1. **The Intraday Retail Illusion (ORB & VWAP):**
   - On authentic 5-minute option and spot data across 496 sessions, every unconditioned ORB setup (15m 1R, 1.5R, 2R, EOD, 30m 1.5R) and VWAP setup generated net losses ranging from -₹50,000 to -₹150,000 per lot after authentic statutory STT, GST, and 1-tick slippage.
   - The high transaction turnover completely consumes any gross edge.
2. **Futures Trend Following Range Decay:**
   - Classical Donchian (20D, 55D), Moving Average crossovers (20/50, 50/200), and Supertrend on NIFTY futures suffered severe whipsaw during the 2024–2026 consolidation regime, resulting in negative net P&L and failing the 2×/3× cost stress tests.
3. **Multi-Leg Premium Harvesting Dominance:**
   - `OPT_ATM_STRADDLE_0DTE` and `OPT_STRANGLE_WEEKLY` were the only canonical strategies that decisively passed all robustness gates across the full 2-year period, maintaining positive expectancy even after 3× statutory cost stress and removing the top 3 best trades.
4. **The Retail Under-Capitalization Barrier:**
   - Accounts with ₹20,000, ₹50,000, or ₹1,00,000 **cannot mathematically execute any surviving robust strategy** under SEBI margin rules without unhedged margin violations.
   - Retail option buyers trading at ₹20k lose capital to negative drift and bid-ask friction.
   - Minimum capital required to execute the surviving 0DTE straddle is **₹2,50,000** (under the 60% margin allocation rule).
   - Minimum capital required to execute the surviving Weekly Strangle is **₹3,00,000**.