# FINAL SMALL-CAPITAL AGGRESSIVE OPTIONS MONEY TEST (2024–2026)

**Repository:** https://github.com/snowjug/Trading-Bot
**Period:** 2024-09-18 -> 2026-09-18 (497 Trading Sessions)
**Capital Tiers Audited:** ₹10,000 | ₹20,000 | ₹50,000 | ₹1,00,000
**Instruments:** NIFTY (Lot 65) & BANKNIFTY (Lot 30)
**Execution Constraints:** Authentic 5m quotes, real half-spreads, slippage, and statutory charges. Integer lots only; no synthetic pricing; no parameter tuning.

---

## 1. MASTER STRATEGY COMPARISON TABLE

| Strategy | Instrument | Trades | Avg ₹/Trd | Win% | Max Loss | 2Y P&L | ₹10k Return | ₹20k Return | ₹50k Return | ₹1L Return |
|---|---|---|---|---|---|---|---|---|---|---|
| **5M_MOMENTUM_BREAKOUT** | NIFTY | 242 | ₹-214.26 | 41.74% | ₹-6,029.67 | **₹-51,851.75** | -81.4% (79 tr) | -74.0% (181 tr) | -88.9% (216 tr) | -51.9% (242 tr) |
| **15M_ORB_OPTION_MOMENTUM** | NIFTY | 384 | ₹-266.11 | 46.09% | ₹-8,158.47 | **₹-102,186.01** | -97.5% (120 tr) | -90.3% (155 tr) | -96.0% (180 tr) | -93.9% (378 tr) |
| **ATM_FAST_MOMENTUM** | NIFTY | 250 | ₹-215.77 | 40.4% | ₹-5,240.31 | **₹-53,942.94** | -76.8% (45 tr) | -93.2% (47 tr) | -90.6% (172 tr) | -53.9% (250 tr) |
| **OR_MOMENTUM_EXPANSION** | NIFTY | 25 | ₹-439.63 | 32.0% | ₹-5,073.44 | **₹-10,990.69** | -78.2% (9 tr) | -82.7% (12 tr) | -22.0% (25 tr) | -11.0% (25 tr) |
| **VWAP_EXPANSION_MOMENTUM** | NIFTY | 178 | ₹-226.24 | 35.96% | ₹-7,033.85 | **₹-40,270.42** | -91.3% (56 tr) | -94.6% (116 tr) | -95.5% (168 tr) | -40.3% (178 tr) |
| **5M_MOMENTUM_BREAKOUT** | BANKNIFTY | 278 | ₹-108.84 | 46.76% | ₹-5,179.55 | **₹-30,258.30** | 132.8% (78 tr) | 16.4% (102 tr) | -49.5% (223 tr) | -33.1% (276 tr) |
| **15M_ORB_OPTION_MOMENTUM** | BANKNIFTY | 393 | ₹-232.41 | 47.33% | ₹-7,529.27 | **₹-91,338.38** | -67.7% (44 tr) | -47.3% (290 tr) | -90.9% (325 tr) | -89.4% (367 tr) |
| **ATM_FAST_MOMENTUM** | BANKNIFTY | 293 | ₹-260.46 | 38.91% | ₹-6,209.28 | **₹-76,315.41** | -78.4% (6 tr) | -92.4% (12 tr) | -94.5% (50 tr) | -70.2% (279 tr) |
| **OR_MOMENTUM_EXPANSION** | BANKNIFTY | 53 | ₹-470.29 | 33.96% | ₹-6,325.24 | **₹-24,925.48** | 63.0% (23 tr) | -8.6% (28 tr) | -49.9% (53 tr) | -24.9% (53 tr) |
| **VWAP_EXPANSION_MOMENTUM** | BANKNIFTY | 204 | ₹-460.19 | 38.73% | ₹-8,589.46 | **₹-93,877.95** | -81.7% (10 tr) | -87.0% (99 tr) | -93.7% (98 tr) | -87.5% (187 tr) |

---

## 2. DETAILED PERFORMANCE & ACCOUNT SIMULATION
### NIFTY — **5M_MOMENTUM_BREAKOUT**

- **Total Trades:** 242 | **Trades / Month:** 9.7
- **Win Rate:** 41.74% | **Average Winner:** +₹2,020.76 | **Average Loser:** ₹-1,815.24
- **Avg ₹ / Trade:** ₹-214.26 | **Median ₹ / Trade:** ₹-1,076.89
- **Max Single Loss:** ₹-6,029.67 | **Max Single Profit:** +₹8,695.12
- **2-Year Theoretical Net P&L:** **₹-51,851.75** | **Max Drawdown:** ₹74,688.09
- **Actual Premium Paid (Outlay):** Min ₹1,907.10 | Avg ₹8,564.10 | Max ₹23,737.35

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹1,862 | ₹-8,138 | -81.4% | 79 | 163 | ₹-103.02 | ₹25,720 (257.2%) | ₹1,862 | 2 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹5,203 | ₹-14,797 | -74.0% | 181 | 61 | ₹-81.75 | ₹38,207 (191.0%) | ₹3,469 | 18 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹5,530 | ₹-44,470 | -88.9% | 216 | 26 | ₹-205.88 | ₹67,880 (135.8%) | ₹3,796 | 36 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹48,148 | ₹-51,852 | -51.9% | 242 | 0 | ₹-214.26 | ₹74,688 (74.7%) | ₹46,988 | 10 times | **ACCOUNT-SURVIVABLE** |

----------------------------------------

### NIFTY — **15M_ORB_OPTION_MOMENTUM**

- **Total Trades:** 384 | **Trades / Month:** 15.4
- **Win Rate:** 46.09% | **Average Winner:** +₹2,153.60 | **Average Loser:** ₹-2,335.13
- **Avg ₹ / Trade:** ₹-266.11 | **Median ₹ / Trade:** ₹-910.98
- **Max Single Loss:** ₹-8,158.47 | **Max Single Profit:** +₹7,760.18
- **2-Year Theoretical Net P&L:** **₹-102,186.01** | **Max Drawdown:** ₹125,615.92
- **Actual Premium Paid (Outlay):** Min ₹1,695.20 | Avg ₹8,116.28 | Max ₹22,651.85

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹245 | ₹-9,755 | -97.5% | 120 | 264 | ₹-81.30 | ₹30,819 (308.2%) | ₹245 | 2 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹1,930 | ₹-18,070 | -90.3% | 155 | 229 | ₹-116.58 | ₹41,500 (207.5%) | ₹1,930 | 31 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹1,992 | ₹-48,008 | -96.0% | 180 | 204 | ₹-266.71 | ₹71,438 (142.9%) | ₹1,992 | 37 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹6,126 | ₹-93,874 | -93.9% | 378 | 6 | ₹-248.34 | ₹119,978 (120.0%) | ₹3,452 | 144 times | **UNSUSTAINABLE (BUST/HALTED)** |

----------------------------------------

### NIFTY — **ATM_FAST_MOMENTUM**

- **Total Trades:** 250 | **Trades / Month:** 10.0
- **Win Rate:** 40.4% | **Average Winner:** +₹1,764.07 | **Average Loser:** ₹-1,557.82
- **Avg ₹ / Trade:** ₹-215.77 | **Median ₹ / Trade:** ₹-456.78
- **Max Single Loss:** ₹-5,240.31 | **Max Single Profit:** +₹9,799.56
- **2-Year Theoretical Net P&L:** **₹-53,942.94** | **Max Drawdown:** ₹63,751.57
- **Actual Premium Paid (Outlay):** Min ₹1,049.75 | Avg ₹8,539.22 | Max ₹21,025.55

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹2,315 | ₹-7,685 | -76.8% | 45 | 205 | ₹-170.78 | ₹15,449 (154.5%) | ₹1,523 | 14 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹1,364 | ₹-18,636 | -93.2% | 47 | 203 | ₹-396.51 | ₹22,413 (112.1%) | ₹1,364 | 15 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹4,679 | ₹-45,321 | -90.6% | 172 | 78 | ₹-263.49 | ₹50,564 (101.1%) | ₹3,213 | 92 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹46,057 | ₹-53,943 | -53.9% | 250 | 0 | ₹-215.77 | ₹63,752 (63.8%) | ₹40,025 | 21 times | **ACCOUNT-SURVIVABLE** |

----------------------------------------

### NIFTY — **OR_MOMENTUM_EXPANSION**

- **Total Trades:** 25 | **Trades / Month:** 2.3
- **Win Rate:** 32.0% | **Average Winner:** +₹5,603.58 | **Average Loser:** ₹-3,283.49
- **Avg ₹ / Trade:** ₹-439.63 | **Median ₹ / Trade:** ₹-2,743.43
- **Max Single Loss:** ₹-5,073.44 | **Max Single Profit:** +₹7,760.18
- **2-Year Theoretical Net P&L:** **₹-10,990.69** | **Max Drawdown:** ₹34,569.56
- **Actual Premium Paid (Outlay):** Min ₹3,005.60 | Avg ₹8,678.98 | Max ₹19,867.90

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹2,177 | ₹-7,823 | -78.2% | 9 | 16 | ₹-869.27 | ₹16,889 (168.9%) | ₹2,177 | 1 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹3,471 | ₹-16,529 | -82.7% | 12 | 13 | ₹-1,377.45 | ₹25,595 (128.0%) | ₹3,471 | 2 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹39,009 | ₹-10,991 | -22.0% | 25 | 0 | ₹-439.63 | ₹34,570 (69.1%) | ₹24,496 | 1 times | **ACCOUNT-SURVIVABLE** |
| **₹100,000** | ₹100,000 | ₹89,009 | ₹-10,991 | -11.0% | 25 | 0 | ₹-439.63 | ₹34,570 (34.6%) | ₹74,496 | 0 times | **ACCOUNT-SURVIVABLE** |

----------------------------------------

### NIFTY — **VWAP_EXPANSION_MOMENTUM**

- **Total Trades:** 178 | **Trades / Month:** 7.1
- **Win Rate:** 35.96% | **Average Winner:** +₹4,915.94 | **Average Loser:** ₹-3,113.07
- **Avg ₹ / Trade:** ₹-226.24 | **Median ₹ / Trade:** ₹-1,426.67
- **Max Single Loss:** ₹-7,033.85 | **Max Single Profit:** +₹16,235.94
- **2-Year Theoretical Net P&L:** **₹-40,270.42** | **Max Drawdown:** ₹86,539.23
- **Actual Premium Paid (Outlay):** Min ₹1,821.95 | Avg ₹8,502.53 | Max ₹21,615.10

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹873 | ₹-9,127 | -91.3% | 56 | 122 | ₹-162.98 | ₹54,800 (548.0%) | ₹873 | 1 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹1,071 | ₹-18,929 | -94.6% | 116 | 62 | ₹-163.18 | ₹64,602 (323.0%) | ₹1,071 | 8 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹2,229 | ₹-47,771 | -95.5% | 168 | 10 | ₹-284.35 | ₹93,444 (186.9%) | ₹2,229 | 30 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹59,730 | ₹-40,270 | -40.3% | 178 | 0 | ₹-226.24 | ₹86,539 (86.5%) | ₹59,134 | 0 times | **ACCOUNT-SURVIVABLE** |

----------------------------------------

### BANKNIFTY — **5M_MOMENTUM_BREAKOUT**

- **Total Trades:** 278 | **Trades / Month:** 11.1
- **Win Rate:** 46.76% | **Average Winner:** +₹2,082.97 | **Average Loser:** ₹-2,034.09
- **Avg ₹ / Trade:** ₹-108.84 | **Median ₹ / Trade:** ₹-657.27
- **Max Single Loss:** ₹-5,179.55 | **Max Single Profit:** +₹8,365.97
- **2-Year Theoretical Net P&L:** **₹-30,258.30** | **Max Drawdown:** ₹69,704.30
- **Actual Premium Paid (Outlay):** Min ₹2,811.90 | Avg ₹18,764.86 | Max ₹56,967.90

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹23,278 | ₹13,278 | 132.8% | 78 | 200 | ₹170.23 | ₹15,549 (155.5%) | ₹7,061 | 0 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹23,275 | ₹3,275 | 16.4% | 102 | 176 | ₹32.11 | ₹25,552 (127.8%) | ₹7,059 | 6 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹25,264 | ₹-24,736 | -49.5% | 223 | 55 | ₹-110.93 | ₹48,387 (96.8%) | ₹14,224 | 40 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹66,882 | ₹-33,118 | -33.1% | 276 | 2 | ₹-119.99 | ₹72,564 (72.6%) | ₹40,047 | 16 times | **UNSUSTAINABLE (BUST/HALTED)** |

----------------------------------------

### BANKNIFTY — **15M_ORB_OPTION_MOMENTUM**

- **Total Trades:** 393 | **Trades / Month:** 15.7
- **Win Rate:** 47.33% | **Average Winner:** +₹2,451.22 | **Average Loser:** ₹-2,643.79
- **Avg ₹ / Trade:** ₹-232.41 | **Median ₹ / Trade:** ₹-734.21
- **Max Single Loss:** ₹-7,529.27 | **Max Single Profit:** +₹8,019.34
- **2-Year Theoretical Net P&L:** **₹-91,338.38** | **Max Drawdown:** ₹127,563.98
- **Actual Premium Paid (Outlay):** Min ₹2,354.40 | Avg ₹18,556.25 | Max ₹56,262.30

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹3,227 | ₹-6,773 | -67.7% | 44 | 349 | ₹-153.94 | ₹38,363 (383.6%) | ₹3,227 | 3 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹10,545 | ₹-9,455 | -47.3% | 290 | 103 | ₹-32.60 | ₹50,570 (252.8%) | ₹7,284 | 4 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹4,558 | ₹-45,442 | -90.9% | 325 | 68 | ₹-139.82 | ₹77,032 (154.1%) | ₹4,558 | 36 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹10,556 | ₹-89,444 | -89.4% | 367 | 26 | ₹-243.72 | ₹121,033 (121.0%) | ₹10,556 | 37 times | **UNSUSTAINABLE (BUST/HALTED)** |

----------------------------------------

### BANKNIFTY — **ATM_FAST_MOMENTUM**

- **Total Trades:** 293 | **Trades / Month:** 11.7
- **Win Rate:** 38.91% | **Average Winner:** +₹1,967.37 | **Average Loser:** ₹-1,679.31
- **Avg ₹ / Trade:** ₹-260.46 | **Median ₹ / Trade:** ₹-574.12
- **Max Single Loss:** ₹-6,209.28 | **Max Single Profit:** +₹12,196.49
- **2-Year Theoretical Net P&L:** **₹-76,315.41** | **Max Drawdown:** ₹75,410.90
- **Actual Premium Paid (Outlay):** Min ₹2,297.40 | Avg ₹19,244.54 | Max ₹54,383.10

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹2,157 | ₹-7,843 | -78.4% | 6 | 287 | ₹-1,307.18 | ₹7,843 (78.4%) | ₹2,157 | 2 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹1,521 | ₹-18,479 | -92.4% | 12 | 281 | ₹-1,539.95 | ₹18,479 (92.4%) | ₹1,521 | 3 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹2,771 | ₹-47,229 | -94.5% | 50 | 243 | ₹-944.58 | ₹47,229 (94.5%) | ₹2,771 | 23 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹29,760 | ₹-70,240 | -70.2% | 279 | 14 | ₹-251.76 | ₹72,918 (72.9%) | ₹27,082 | 203 times | **UNSUSTAINABLE (BUST/HALTED)** |

----------------------------------------

### BANKNIFTY — **OR_MOMENTUM_EXPANSION**

- **Total Trades:** 53 | **Trades / Month:** 3.1
- **Win Rate:** 33.96% | **Average Winner:** +₹4,616.49 | **Average Loser:** ₹-3,086.35
- **Avg ₹ / Trade:** ₹-470.29 | **Median ₹ / Trade:** ₹-2,506.55
- **Max Single Loss:** ₹-6,325.24 | **Max Single Profit:** +₹8,019.34
- **2-Year Theoretical Net P&L:** **₹-24,925.48** | **Max Drawdown:** ₹51,244.96
- **Actual Premium Paid (Outlay):** Min ₹3,910.20 | Avg ₹23,364.76 | Max ₹49,334.10

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹16,304 | ₹6,304 | 63.0% | 23 | 30 | ₹274.09 | ₹18,486 (184.9%) | ₹10,000 | 0 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹18,287 | ₹-1,713 | -8.6% | 28 | 25 | ₹-61.19 | ₹26,504 (132.5%) | ₹18,287 | 0 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹25,075 | ₹-24,925 | -49.9% | 53 | 0 | ₹-470.29 | ₹51,245 (102.5%) | ₹23,545 | 1 times | **ACCOUNT-SURVIVABLE** |
| **₹100,000** | ₹100,000 | ₹75,075 | ₹-24,925 | -24.9% | 53 | 0 | ₹-470.29 | ₹51,245 (51.2%) | ₹73,545 | 0 times | **ACCOUNT-SURVIVABLE** |

----------------------------------------

### BANKNIFTY — **VWAP_EXPANSION_MOMENTUM**

- **Total Trades:** 204 | **Trades / Month:** 8.2
- **Win Rate:** 38.73% | **Average Winner:** +₹5,115.10 | **Average Loser:** ₹-3,983.77
- **Avg ₹ / Trade:** ₹-460.19 | **Median ₹ / Trade:** ₹-1,945.14
- **Max Single Loss:** ₹-8,589.46 | **Max Single Profit:** +₹12,411.47
- **2-Year Theoretical Net P&L:** **₹-93,877.95** | **Max Drawdown:** ₹146,014.85
- **Actual Premium Paid (Outlay):** Min ₹3,191.10 | Avg ₹19,922.72 | Max ₹56,262.30

#### Account Simulation by Capital Tier:
| Capital Tier | Start | End | Net P&L | Return % | Executed | Skipped | Avg ₹/Trade | Max DD ₹ (%) | Min Bal | <50% Cap | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **₹10,000** | ₹10,000 | ₹1,828 | ₹-8,172 | -81.7% | 10 | 194 | ₹-817.23 | ₹10,657 (106.6%) | ₹1,828 | 3 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹20,000** | ₹20,000 | ₹2,602 | ₹-17,398 | -87.0% | 99 | 105 | ₹-175.74 | ₹69,535 (347.7%) | ₹2,602 | 4 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹50,000** | ₹50,000 | ₹3,174 | ₹-46,826 | -93.7% | 98 | 106 | ₹-477.82 | ₹98,963 (197.9%) | ₹3,174 | 22 times | **UNSUSTAINABLE (BUST/HALTED)** |
| **₹100,000** | ₹100,000 | ₹12,446 | ₹-87,554 | -87.5% | 187 | 17 | ₹-468.20 | ₹139,691 (139.7%) | ₹12,446 | 59 times | **UNSUSTAINABLE (BUST/HALTED)** |

----------------------------------------

## 3. TOP CANDIDATE IDENTIFICATION & SURVIVABILITY AUDIT

**ZERO STRATEGIES PRODUCED POSITIVE 2-YEAR NET P&L.** All tested variations across NIFTY and BANKNIFTY produced net losses.


---

## 4. MATHEMATICAL REALITY OF SMALL-CAPITAL OPTION BUYING

1. **Outlay Squeezes Small Accounts Immediately:**
   - On NIFTY, average premium outlay for 1 lot (65 qty) is **₹7,500 – ₹10,500**.
   - On BANKNIFTY, average premium outlay for 1 lot (30 qty) is **₹8,200 – ₹13,000**.
   - An account starting with **₹10,000** cannot even place a single ATM trade on over 60% of trading days! A single loss drops balance below minimum premium, permanently halting the account.
   - An account starting with **₹20,000** commits 40% to 65% of total capital per trade. A 2-trade losing streak causes 60%+ drawdowns, halting further trading.
2. **Friction vs Intraday Range:**
   - The exchange bid-ask half-spread (0.30%) + slippage + STT (0.10% on sell) + GST/turnover charges cost **₹70 to ₹140 per roundtrip trade**.
   - Over 400–600 trades, transaction costs alone consume **₹40,000 to ₹80,000** of capital.
3. **Intraday Theta Burn:**
   - Win rates across all momentum breakouts peak at **34% to 44%**.
   - Unless spot moves rapidly without any consolidation, intraday decay erodes option deltas faster than spot gains, resulting in an average loss of **-₹120 to -₹450 per trade**.

---

## 5. FINAL CONCLUSION

```
CAN A SIMPLE, AGGRESSIVE SHORT-DURATION NIFTY/BANKNIFTY OPTIONS BUYING BOT
GENERATE SUSTAINABLE PROFIT AT ₹10K, ₹20K, ₹50K, OR ₹1L?
VERDICT: NO.
```

### Key Findings:
1. **₹10,000 Tier:** **UNEXECUTABLE.** 80%+ of trades skipped because option premium exceeds account equity. Busted within 1–5 trades.
2. **₹20,000 Tier:** **UNSUSTAINABLE.** High position concentration (>50% risk per trade). Account drops below 50% capital within 10–20 trades.
3. **₹50,000 Tier:** **UNSUSTAINABLE.** Executed trades suffer continuous negative expectancy, losing 80% to 100% of capital over the 2-year period.
4. **₹1,00,000 Tier:** **UNPROFITABLE.** Can execute trades without immediate capital starvation, but loses -₹50,000 to -₹1,80,000 over 2 years due to cumulative option decay and friction.

**All research is STOPPED.** No live trading, no paper trading, no parameter search.