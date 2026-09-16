# SEBI Regulatory Compliance & Tax Audit
**Generated**: 2026-09-16 19:27 IST  
**Jurisdiction**: Securities and Exchange Board of India (SEBI)  
**Tax Authority**: Income Tax Department, Government of India  

---

## 1. SEBI Circular Compliance

### 1.1 Algorithmic Trading Regulations (SEBI/HO/MRD/DP/CIR/P/2016/30)
| Requirement | Status | Implementation |
|:---|:---:|:---|
| Algo orders must be tagged | **COMPLIANT** | All orders tagged with strategy name + signal ID |
| Risk checks before order submission | **COMPLIANT** | 7-gate pre-trade check system |
| Kill switch capability | **COMPLIANT** | `Config.LIVE_TRADING_ENABLED` flag |
| Audit trail of all orders | **COMPLIANT** | Full order log with timestamps in `logs/` |

### 1.2 F&O Position Limits
| Instrument | SEBI Limit | System Limit | Status |
|:---|:---:|:---:|:---:|
| NIFTY Options (client) | 15,000 lots | 1 lot (research default) | **COMPLIANT** |
| BANKNIFTY Options | 2,500 lots | 1 lot | **COMPLIANT** |
| Total F&O exposure | < 5% of MWPL | Well within | **COMPLIANT** |

## 2. Tax Computation Engine

### 2.1 Securities Transaction Tax (STT) — Post Oct 2024
| Trade Type | STT Rate | When Applied |
|:---|:---:|:---|
| Options Sell (premium) | 0.100% | On sell-side premium turnover |
| Futures Sell | 0.020% | On sell-side notional turnover |
| Equity Delivery Buy | 0.100% | On buy-side transaction value |
| Equity Delivery Sell | 0.100% | On sell-side transaction value |
| Equity Intraday Sell | 0.025% | On sell-side transaction value |

### 2.2 Income Tax Treatment
| Income Type | Classification | Tax Rate |
|:---|:---|:---:|
| F&O Trading Income | Speculative Business Income (Sec 43(5)) | Slab rate |
| Short-Term Capital Gains (Equity < 1 year) | STCG u/s 111A | 15% + cess |
| Long-Term Capital Gains (Equity > 1 year) | LTCG u/s 112A | 10% above Rs 1L |
| Intraday Trading | Speculative Income | Slab rate |

### 2.3 GST on Brokerage
- **Rate**: 18% on (Brokerage + Exchange Turnover Charges)
- **Implementation**: Correctly computed in `src/backtesting/cost_model.py`

## 3. Record-Keeping Compliance

| Requirement | Status | Location |
|:---|:---:|:---|
| Complete trade history | Yes | `logs/trades/` |
| P&L statements | Yes | `reports/` |
| Tax computation records | Yes | Cost model breakdown per trade |
| Audit trail | Yes | Data lineage + SHA-256 hashes |

## 4. Risk Disclosures

> [!CAUTION]
> **Mandatory Risk Disclosure (SEBI format)**:
> 1. Trading in F&O involves substantial risk of loss and is not suitable for all investors.
> 2. Past performance is not indicative of future results.
> 3. The system uses EOD data and synthetic option pricing — actual execution prices may differ materially.
> 4. All backtest results include known limitations documented in `reports/DATA_INTEGRITY_AUDIT.md`.
> 5. Live trading requires explicit human authorization and is disabled by default.

## 5. Verdict

> [!NOTE]
> The system is **COMPLIANT** with applicable SEBI algorithmic trading regulations and Indian tax computation requirements. Position limits are set conservatively at 1 lot (well below SEBI client limits). The versioned cost model correctly implements Pre/Post Oct 2024 STT schedules.
