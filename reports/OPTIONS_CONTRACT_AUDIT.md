# Options Contract Reconstruction Audit
**Generated**: 2026-09-16 19:27 IST  
**Standard**: SEBI F&O Regulatory Compliance + NSE UDiFF Validation  

---

## 1. Current Options Data Infrastructure

### 1.1 Available Real Data
| Source | Date Range | Format | Contracts |
|:---|:---|:---|:---:|
| NSE UDiFF Bhavcopy 2026-03-19 | Single day | CSV | 2,116 |
| NSE UDiFF Bhavcopy 2026-06-18 | Single day | CSV | 1,815 |
| NSE UDiFF Bhavcopy 2026-08-27 | Single day | CSV | 1,593 |
| NSE UDiFF Bhavcopy 2026-09-15 | Single day | CSV | 1,651 |

### 1.2 Bhavcopy Fields Utilized
- `TckrSymb` — Underlying symbol (NIFTY, BANKNIFTY)
- `StrkPric` — Strike price
- `OptnTp` — CE/PE
- `XpryDt` — Expiry date
- `SttlmPric` — Settlement price (used as proxy for fair value)
- `OpnIntrst` — Open Interest
- `TtlTradgVol` — Traded Volume
- `PrvsClsgPric` — Previous Close

### 1.3 Validation Against Strategy Assumptions

| Strategy Component | Assumption | Reality (from Bhavcopies) | Gap |
|:---|:---|:---|:---|
| Entry Premium (ATM CE/PE) | Fixed Rs 100 | Varies Rs 40-350 depending on VIX and DTE | **SIGNIFICANT** |
| Delta at entry | Fixed 0.55 | ATM delta ~ 0.48-0.52 (from moneyness) | Moderate |
| Spread width (credit spreads) | 100-point strikes | Available in 50-point increments | OK |
| Liquidity (min OI) | Not checked | ATM OI: 50,000-200,000+ contracts | OK for ATM |
| Bid-Ask spread | Not modeled | Estimated 0.5-2.0 Rs for liquid strikes | **MISSING** |

## 2. Option Pricing Model Audit

### 2.1 Black-Scholes Greeks Engine
The system uses `scipy.stats.norm` for BS pricing with:
- **Risk-free rate**: 6.5% (RBI repo rate proxy)
- **Dividend yield**: 1.2% (NIFTY dividend yield)
- **Implied Volatility**: Derived from INDIA VIX (annualized)

### 2.2 Known Deficiencies
1. **IV Smile/Skew Not Modeled**: Uses flat IV from VIX. OTM puts have higher IV than ATM in reality.
2. **No Term Structure**: Same IV used for weekly and monthly expiries.
3. **No Intraday IV Changes**: Options Greeks are computed at EOD only.
4. **No Pin Risk / Gamma Risk**: Near-expiry gamma explosions not captured.

## 3. Real vs Synthetic Premium Comparison (2026 Snapshot)

Using Bhavcopy from Sep 15, 2026 (NIFTY Spot: ~23,250):

| Strike | Type | Bhavcopy Settlement | BS Model Estimate | Error |
|:---:|:---:|:---:|:---:|:---:|
| 23200 | CE | Rs 157.45 | Rs 148.20 | -5.9% |
| 23300 | CE | Rs 89.30 | Rs 85.10 | -4.7% |
| 23100 | PE | Rs 108.75 | Rs 102.40 | -5.8% |
| 23000 | PE | Rs 72.60 | Rs 68.90 | -5.1% |

**Average Model Error**: -5.4% (model underprices slightly due to missing skew premium).

## 4. Verdict

> [!WARNING]
> **Options strategies using synthetic delta/premium are designated `SIMULATION_ONLY`.**
> The BS model error of ~5% is acceptable for directional P&L estimation but insufficient for:
> - Precise credit spread mark-to-market
> - Gamma scalping strategies
> - Any strategy sensitive to bid/ask spreads
>
> **Remediation**: Integrate daily NSE UDiFF Bhavcopies for the full 2024-2026 period to enable contract-level replay.
