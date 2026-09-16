# Liquidity & Capital Realism Audit
**Generated**: 2026-09-16 19:27 IST  
**Standard**: Market Microstructure & Position Sizing Constraints  

---

## 1. Market Liquidity Profile (NIFTY F&O, Sep 2026)

### 1.1 NIFTY Index Options (Weekly Expiry)
| Metric | ATM Strike | ATM ± 100 | ATM ± 200 | ATM ± 500 |
|:---|:---:|:---:|:---:|:---:|
| Open Interest | 150,000+ | 80,000-120,000 | 30,000-60,000 | 5,000-15,000 |
| Daily Volume | 200,000+ | 100,000-180,000 | 40,000-80,000 | 10,000-30,000 |
| Bid-Ask Spread (est.) | Rs 0.50-1.00 | Rs 1.00-2.00 | Rs 2.00-5.00 | Rs 5.00-15.00 |
| Market Impact (1 lot) | Negligible | Negligible | Minimal | Minimal |
| Market Impact (50 lots) | Minimal | Low | Moderate | **Significant** |

### 1.2 NIFTY Futures (Monthly)
| Metric | Near Month | Next Month |
|:---|:---:|:---:|
| Open Interest | 10M+ | 3M-5M |
| Daily Volume | 5M+ | 1M-3M |
| Bid-Ask Spread | Rs 0.50-1.50 | Rs 1.00-3.00 |

## 2. Position Sizing Constraints

### 2.1 Current Implementation
| Strategy | Capital Tier | Position Size | Max Lots |
|:---|:---:|:---:|:---:|
| Velocity-5 Scalper | Rs 10,000 | 1 lot ATM options | 1 |
| Zen Curvature Spread | Rs 1,00,000 | 1 lot credit spread | 1 |
| Golden Trend Runner | Rs 10,000 | 1 lot ATM options | 1 |
| Apex VRP Engine | Rs 1,50,000 | 1 lot Iron Condor | 1 |
| Leader Breakout | Rs 10,00,000 | 5 equity positions | Variable |

### 2.2 Liquidity-Capped Scaling Assessment
| Strategy | Max Scalable Lots (< 1% market impact) | Max Capital |
|:---|:---:|:---:|
| Velocity-5 (ATM options) | 50 lots | Rs 5,00,000 |
| Zen Curvature (spreads) | 20 lots | Rs 20,00,000 |
| Golden Trend Runner | 30 lots | Rs 3,00,000 |
| Apex VRP (Iron Condor) | 10 lots | Rs 15,00,000 |

### 2.3 Compounding Cap
- **Pre-audit**: Strategies compounded without limit, reaching Rs 6.15 Cr theoretical allocation.
- **Post-audit**: Fixed 1-lot sizing enforced. Compounding disabled for research reports.
- **Production guideline**: Scale linearly up to liquidity cap, never compound geometrically without human authorization.

## 3. Lot Size & Margin Requirements (NSE, Sep 2026)

| Instrument | Lot Size | SPAN Margin (approx) | Exposure Margin |
|:---|:---:|:---:|:---:|
| NIFTY Options (Buy) | 25 units | Full premium | None |
| NIFTY Options (Sell) | 25 units | Rs 1,00,000-1,50,000 | Rs 10,000-15,000 |
| NIFTY Futures | 25 units | Rs 1,20,000-1,50,000 | Rs 15,000-20,000 |
| BANKNIFTY Options | 15 units | Full premium (buy) | Rs 80,000-1,20,000 (sell) |

## 4. Verdict

> [!NOTE]
> At 1-lot fixed sizing, all strategies operate well within NIFTY/BANKNIFTY's deep liquidity pool. Market impact is negligible. Scaling beyond 50 lots for options strategies or Rs 20L for spread strategies would require market impact modeling.
