# EXTERNAL SOURCE LEDGER

External material generates HYPOTHESES. It never establishes profitability. No
performance claim from any source below is reproduced as fact.

**Source hierarchy applied:** exchange/regulator data > authenticated broker data >
reputable public data > academic research > established quant research >
open-source implementations > community content > social media.

---

## ACCESSED 2026-09-19

### 1. Overnight-return / intraday-reversal literature
- **Reference:** Cliff, Cooper & Gulen, "Return Differences between Trading and
  Non-Trading Hours" (2008); Lou, Polk & Skouras, "A Tug of War: Overnight Versus
  Intraday Expected Returns" (JFE 2019).
- **Original market/horizon:** US equities, daily, close-to-open vs open-to-close.
- **Rules taken:** the segment split only — hold exposure close→open rather than
  open→close.
- **Reported claim:** overnight returns account for most or all of the equity premium.
- **Indian adaptation:** measured on NIFTY directly rather than assumed to transfer.
- **Reproduction:** **effect is real in NIFTY.** DEV 2019-01→2024-09, n=1,409:
  close→open **+0.1350%/session, t=7.02, 68.6% positive**, positive in each of six
  years; open→close **−0.0677%, t=−2.71**. Only **+0.0907% (t=5.06)** survives at
  the 09:15 traded spot — 29% of the headline sits in the pre-open auction print.
- **Status:** OBSERVED SIGNAL, NOT MONETISED. A near-ATM weekly option has delta
  ≈0.5 and pays ≈12 points of overnight theta against ≈15 points of drift.
- **Known bias:** the US literature is cash-equity; Indian retail cannot hold a
  multi-day cash short, and the delta-1 instruments need ≈₹1.7 lakh of margin.

### 2. Durgia, "Weekly Behavior of the Nifty Index"
- **Reference:** SSRN 5353404 (2015–2025 sample).
- **Access note:** the SSRN page returns **HTTP 403** to automated fetches. Only the
  rules implied by its own title and abstract were reproduced; no number from the
  paper is quoted.
- **Rules taken:** the expiry-cycle anchor — session after one weekly expiry to the
  next expiry — as the basis for systematic option selling. "Friday to Thursday"
  generalised to the full expiry cycle because NIFTY's weekly expiry weekday changed
  mid-sample.
- **Reproduction:** `scripts/research/weekly_cycle_study.py`, settled exactly at
  expiry so no exit price is involved. ±2% strangle: **+8.76 pts/cycle, t=0.87**,
  82.6% win, 23.7% breach, worst cycle **−1,039 pts**. **One cycle of 241 carries
  49% of all profit.** By year: −13.32 / +5.51 / +19.68 / +1.56 / +36.63.
- **Status:** REJECTED. The calendar claim also does not support selling: the ATM
  straddle costs **1.66% of spot** at entry while only **41.7%** of cycles finish
  inside ±1%.

### 3. Retail PCR framing
- **Reference:** widely repeated on Indian retail sites, e.g.
  `niftytrader.in/nifty-put-call-ratio`, `icfmindia.com` intraday strategy posts.
- **Rules taken:** PCR by open interest, thresholds 1.3 and 0.7, as hypotheses.
- **Reported claim:** "PCR > 1.3 signals a reversal down; PCR < 0.7 signals a
  reversal up."
- **Reproduction:** DEV only, conditional overnight index move against an
  unconditional +15.97 pts: **PCR_OI > 1.1 → +31.65 pts, t=6.21, n=195**;
  PCR_OI > 1.3 → +26.16, t=2.96; PCR_OI < 0.7 → +10.15, t=1.23.
- **Status:** **DIRECTION REFUTED, INFORMATION CONFIRMED.** A high put-call ratio
  precedes *continued upward* overnight drift, the opposite of the claim. Threshold
  curve from 0.9 to 1.4 is smooth, so the 1.1 cut is not fitted. Did not survive
  validation: PCR>1.1 fires on ~20% of sessions post-2021, leaving n=28 on VAL and
  t=0.68–1.26 against a pre-registered t≥2.0 gate.

### 4. Variance-risk-premium framing
- **Reference:** general volatility literature plus its retail restatement,
  "buy volatility when implied is below realised".
- **Rules taken:** VIX-vs-realised filters applied to a long ATM straddle.
- **Reproduction:** long straddle 1-day hold, DEV: **−18.05 pts/day, t=−9.09**,
  29.1% win. Filtered on VRP < 0 it gets **worse: −32.30 pts, t=−7.04**.
- **Status:** REJECTED, and the conditioning is **backwards** — VIX below realised
  usually means realised just spiked and is about to mean-revert down.

### 5. Expiry-day effect literature (Indian evidence)
- **References:** "Futures and options expiration-day effects: The Indian evidence"
  (ResearchGate 264369138); "An Empirical Study on the Impact of Weekly Options
  Expiry on Market Volatility: NIFTY and Bank NIFTY" (Zenodo 19220278);
  "F&O Expiry vs. First-Day SIPs: A 22-Year Analysis" (arXiv 2507.04859).
- **Rules taken:** expiry-session return/volume/volatility conditioning; the SIP
  timing claim was read but is not a tradable strategy for this account.
- **Reported claim:** returns, volume and volatility are elevated on expiry day;
  expiry-timed SIPs outperform first-of-month by 0.5–2.5%/yr.
- **Reproduction:** expiry-day overnight drift +0.0927%, **t=2.09**; day before
  expiry +0.1115%, t=2.69. Days-to-expiry gating improved no candidate.
- **Status:** WEAK. Not pursued further.

### 6. Market Intraday Momentum
- **Reference:** Gao, Han, Li & Zhou, JFE 2018 (SSRN 2440866). *Tested in an earlier
  session; recorded here so it is not re-researched.*
- **Rules taken:** first half-hour return predicts last half-hour return, with the
  paper's volatility/volume conditioning and timed exit.
- **Reproduction:** **−₹123,679, t=−4.59, gross-negative** on NIFTY options.
- **Status:** REJECTED — does not transfer.

### 7. Public NIFTY ORB and VWAP-pullback write-ups
- **Reference:** public Indian trading write-ups. *Earlier session.*
- **Reproduction:** ORB conditioning effect real on development, **failed
  validation**; VWAP pullback −₹78,458, t=−2.45.
- **Status:** REJECTED.

### 8. Retail backtesting tools and blog strategy lists
- **References:** `quantzee.com` 2026 NIFTY intraday blueprint;
  `niftytrader.in/live-nifty-open-interest`; `icfmindia.com` "5 smart setups";
  `stockmojo.in/simulator`; `optionbacktesting.in`; `stocksrin.com`.
- **Assessment:** these describe near-ATM directional setups and OI
  support/resistance reads already covered by the 31 concepts closed in the previous
  study. None states rules deterministic enough to reproduce without invention, and
  none addresses the binding constraint identified here, which is instrument
  economics rather than signal choice.
- **Status:** READ, NOT PURSUED — reason recorded rather than left implicit.
- **One methodological point adopted:** "backtest the same strategy in trending-up,
  trending-down and sideways regimes; a strategy that wins in only one is a bet on
  that regime." This is already the regime-split discipline applied throughout.

---

## RULES FOR THIS LEDGER

1. A US or global result is never transplanted by substituting NIFTY for SPY.
   Market hours, expiry structure, settlement, lot size, taxes, spread and gap
   behaviour are compared first, and the Indian hypothesis is stated separately.
2. A source is recorded here the first time it is read, so it is not researched twice.
3. "Reported claim" and "Reproduction" are kept in separate columns permanently.
