# ACTIVE RESEARCH STATE

**Purpose.** Single resume point. A fresh session reads this file first and
continues from `EXACT NEXT ACTION`. Nothing under `ALREADY TESTED` is to be re-run.

**Opened:** 2026-09-18 · **Closed:** 2026-09-19 · **Branch:** `main`
**`LIVE_TRADING_ENABLED`:** `false`
**Status: RUN COMPLETE — OUTCOME B.** Search budget for this run exhausted, no
candidate promoted, every result preserved. Full report:
`reports/FINAL_ONE_YEAR_MONEY_STUDY.md`.

---

## SPLITS USED (fixed before any candidate was written)

| Split | Window | Sessions | Use |
|---|---|---|---|
| DEVELOPMENT | data start → **2024-09-17** | 1,409 daily / 997 grid / 2,396 equity | all screening and structure choice |
| VALIDATION | **2024-09-18 → 2025-09-17** | 247 / 249 | promote or reject, one pass |
| **FINAL HOLDOUT** | **2025-09-18 → 2026-09-18** | 248 | measured once |

**Contamination, disclosed.** (a) The previous 6-month study validated on
2024-09-18 → 2026-03-17, which overlaps the first six months of this holdout; no
candidate from it was promoted, so nothing selected on that overlap is carried
forward. (b) In this run, while tabulating the overnight drift year by year, the
calendar-2025 and calendar-2026 rows were displayed, which lie inside the holdout.
Disclosed in §3.4 of the final report. It could only push toward rejection, and
every candidate had already failed the pre-registered VAL gate.

---

## DATA COVERAGE (authentic, read-only)

| Dataset | Coverage | Path |
|---|---|---|
| NIFTY + India VIX daily OHLC | 1,903–1,905 sessions, 2019-01-01 → 2026-09-18 | `data/raw/nse/index_history/` |
| NIFTY F&O bhavcopy, all strikes/expiries | 1,904 sessions, **4,013,288 rows**, OI at 100% coverage | `data/raw/nse/fo_bhavcopy/` |
| NIFTY options 5-min, ATM±6, CE+PE | **1,501 sessions**, ~2.9M bars, 2020-09-01 → 2026-09-18 | `data/raw/dhan/option_grid_5m/` |
| ~48 NSE equities + BANKNIFTY + NIFTY IT, **daily** | 2015-01 → 2026-09-16 | `data/raw/*_daily.csv` |
| **Chain panel** (built this run) | 1,903 × 79 | `data/derived/chain_panel.parquet` |
| **Equity panel** (built this run) | 124,511 × 75, 48 symbols | `data/derived/equity_panel.parquet` |
| **Grid cache** (built this run) | CE 1,463,973 / PE 1,463,796 bars | `data/derived/grid5m_{ce,pe}.parquet` |

**Hard data limits.** No futures prices of any kind. No intraday data for
BANKNIFTY or equities. Lot size authentic only from 2024. The equity universe is
the *current* NIFTY 50 and is survivorship-contaminated.

**Measured data quirks that changed answers — do not rediscover these:**
1. On an **expiry** session the bhavcopy writes the UNDERLYING's settlement value
   into `SttlmPric` for every contract. Reading it priced the ATM straddle at 2×
   spot. Guarded in `chain_panel._at`.
2. `ClsPric` is NSE's **30-minute weighted average**, not the closing print:
   +0.80 points above the 15:2x print for puts (median, n = 19,828). Only ever
   used for a leg being bought.
3. `OpnPric` matches the grid's 09:15 open (median difference 0.000, corr 0.978,
   n = 19,358) — but exiting *at* the opening print is not tradable: a long ATM+1
   call earns +3.49 pts/night there and **loses 1.31** five minutes later.
4. The 5-minute grid is truncated to **ATM±6**, and the nights it cannot price are
   the big-gap nights (mean index move −185 to −279 points against +19 to +26).
   Pricing exits from the grid alone deletes exactly the losses of a short-vol
   position.
5. `UndrlygPric` and `NewBrdLotQty` are populated on only **27.4%** of bhavcopy rows.

---

## ALREADY TESTED — DO NOT REPEAT

### Earlier studies (~130 implementations)
- **Bot 1** weekly iron condor: 259 cycles 2019-2026, +0.15 pts/cycle, t = 0.06,
  six of eight years lose. Break-even win rate 96.43% vs 8.5% measured breach rate.
- **Bot 5 / Bot 6** intraday momentum: 589 / 187 real-option trades, no edge.
- **Bot 7**: 7 pre-registered candidates including short straddle, iron fly, theta.
  The "+₹456,653" was a silent-skip artefact; corrected to −₹22,094, t = −0.305.
- **31 intraday concepts, ~100 implementations** (`src/research/concepts.py`):
  ORB ×10, prev-day levels, gap go/fade, session anchors, Market Intraday Momentum
  (JFE 2018), Donchian, trend pullback, compression break, range expansion,
  VIX-banded ORB, session-extreme fade, RSI revert, liquidity sweep, structure
  break. 25 of 31 gross-negative on DEV.
- **0-DTE iron condor**: −₹47,803, 50.5% breach when settled honestly at expiry.
- **Intraday premium-selling sweeps**: rejected.

### This run (~90 implementations)
| Family | Implementations | Outcome |
|---|---|---|
| Overnight long call (4 strikes incl. deep ITM) | 6 | rejected — theta beats delta; deep ITM is stale-priced (t = −17.26) |
| Overnight put spreads, 6 offsets × 3 widths | 18 | rejected — best t = 1.24 |
| Overnight put spreads, wide 300–800 | 24 | rejected — non-monotone surface, ex-2020/21 t = 1.27, dies at 2× costs |
| Overnight naked short put | 2 | rejected on capital — ₹169,481 margin |
| Overnight synthetic long future | 1 | rejected — ex-2020/21 exactly 0.00 |
| Overnight bull call spreads | 4 | rejected — −0.79 to −2.78 pts |
| Overnight conditioned on PCR / ΔOI / max pain / VRP / VIX / weekday | 48 cells | rejected at VAL gate (t = 0.68–1.26 vs 2.0); negative on holdout |
| Equity cross-section, 20 features × 4 horizons | 80 tests | rejected — real reversal effect, but alpha < STT (0.1% per side) |
| Long straddle 1–4 day, and filtered on cheap vol | 10 | rejected — −18.05 pts/day t = −9.09; VRP filter makes it *worse* |
| Short straddle 1-day, and filtered on rich vol | 9 | rejected — +13.07 collapses to −0.38 once all 34 unpriced nights are priced |

**Closed spaces:** intraday NIFTY option buying; intraday NIFTY premium selling;
overnight NIFTY options (unconditional and chain-conditioned); weekly iron condor;
0-DTE condor; long and short 1-day volatility; daily equity cross-section.

---

## STANDING QUANTITATIVE FACTS (reuse, do not re-derive)

- NIFTY DEV overnight drift **+0.1350%/night, t = 7.02, 68.6% of nights**; regular
  session **−0.0677%, t = −2.71**.
- Only **+0.0907% (t = 5.06)** of that is available at the 09:15 traded spot —
  29% of the headline sits in the pre-open auction print. ≈ **+15 index points**.
- A near-ATM weekly option pays ≈ **12 points of overnight theta** on ~99 points of
  premium and has delta ≈ 0.5.
- **PCR_OI > 1.1 doubles the drift** to +31.65 points, t = 6.21, n = 195. Smooth
  threshold curve from 0.9 to 1.4. High PCR precedes *continued* upward drift —
  the opposite of the "PCR > 1.3 → reversal" hypothesis.
- Drift by year: 2019 +0.148 / 2020 +0.184 / 2021 +0.194 / 2022 +0.031 /
  2023 +0.127 / 2024 +0.097. All conditioned significance comes from 2021.
- Option round-trip friction ≈ **3.3 points** for a 2-leg structure at lot 65
  (₹20/order brokerage alone is 1.23 points).
- Delivery-equity round trip ≈ **0.23%**, of which 0.20% is STT. Best measured
  cross-sectional alpha 0.085%/day.

---

## CANDIDATE LEDGER

`reports/overnight_dev.csv`, `reports/overnight_dev_width.csv`,
`reports/overnight_dev_conditional.csv`, `reports/overnight_validation.csv`,
`reports/chain_screen_dev.csv`, `reports/chain_hypotheses_dev.csv`,
`reports/equity_screen_dev.csv`, `reports/money_result_1y.json`.

---

## CODE ADDED THIS RUN

| File | Purpose |
|---|---|
| `src/research/chain_panel.py` | daily point-in-time option-chain state: PCR (OI and volume), ΔOI, OI walls, max pain, ATM straddle, VRP, percentile ranks |
| `src/research/overnight.py` | close-to-open engine: two-venue pricing, adverse marking, no silent skips, defined-risk vs SPAN margin |
| `src/research/equity_panel.py` | daily equity cross-section with survivorship handling stated in the module docstring |
| `scripts/research/chain_screen.py` | DEV predictive screen + the brief's named PCR hypotheses |
| `scripts/research/overnight_dev.py` | 31 structures on DEV with full skip accounting |
| `scripts/research/overnight_falsify.py` | concentration / regime / exit-venue / cost / entry-venue / calendar battery |
| `scripts/research/overnight_validate.py` | pre-registered candidates and gate |
| `scripts/research/equity_screen.py` | 80 cross-sectional tests |
| `scripts/research/money_result_1y.py` | one-year holdout money result + rejected-candidate disclosure |
| `tests/test_research_overnight.py` | 25 regression tests: silent skips, exit venue, adverse marking, margin, lookahead, split integrity, mirror-sign check |

---

## EXACT NEXT ACTION

Nothing is in flight. The run is closed at **outcome B**. A future session has
three options, in descending order of expected value, and none of them is a
continuation of the spaces above:

1. **Acquire NIFTY/BANKNIFTY futures history** (daily or intraday). This is the
   single highest-value missing dataset: it is the only instrument that converts
   the measured overnight drift at a credible spread, and it cannot be tested at
   all with what is here. Note it still needs ~₹1.4 lakh of margin per lot, so it
   answers the edge question, not the ₹20K question.
2. **Acquire a survivorship-free equity universe** (delisted and index-removed
   names, 2015-2026) before any cross-sectional claim is made. The reversal effect
   measured here is real but sits under the 0.2% round-trip STT, so this is
   informative rather than promising.
3. **Accept that the measured edges are smaller than retail friction** and stop.
   This is the honest reading of 220 implementations.

Do **not** resume by tuning any family listed under ALREADY TESTED.
