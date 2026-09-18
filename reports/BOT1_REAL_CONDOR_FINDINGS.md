# Bot 1 — NIFTY Weekly Iron Condor: authentic four-leg research

Branch `rebuild/bots-1-5-6-7`. `main` untouched. `LIVE_TRADING_ENABLED = false`.
No Dhan order, position, or account-mutation endpoint was called at any point.

**Bottom line: with authentic exchange prices over 7.6 years, Bot 1 has no
demonstrable edge after costs. Net expectancy is +2.90 points per weekly cycle at
t = +1.40 — indistinguishable from zero — and turns negative at 1 point per leg of
slippage. It is NOT paper-ready. No parameter was changed to reach this.**

---

## 1. The data blocker was real, but it was the wrong blocker

The previous verdict was "0.0% of 420 sessions feasible — Bot 1 cannot be
backtested." That was a limitation of **one vendor endpoint**, not of the data.

| | DhanHQ `/charts/rollingoption` | NSE F&O bhavcopy |
|---|---|---|
| Strike coverage | ATM±10 (verified stable across 2021 / 2023 / 2026) | **12000–34500 vs a ~23200 spot** |
| Bot 1 needs | ~ATM±13 shorts, ~ATM±17 wings | comfortably inside |
| Volume at those legs | n/a | **360k–650k contracts/day** |
| Access | authenticated | **public, unauthenticated** |
| Reach | 2020-09 → | **2019 →** (UDiFF from 2024-01-02, legacy before) |

Ingested: **1,903 sessions, 4.0M option rows**. NIFTY and India VIX history came
from NSE's public `ind_close_all` archive and were **independently cross-checked**
against the repository's own files — 422 overlapping sessions, max difference
**0.0008 points**, none exceeding 0.1%.

---

## 2. Canonical specification — resolved from existing evidence only

| Item | Resolution | Evidence |
|---|---|---|
| Structure | **four-leg Iron Condor** | class name, hypothesis text ("Call & Put spreads … hedged wings"), the `wing_sd=2.4` parameter, and the four-leg `OptionsStructure.simulate_iron_condor` |
| Shorts | spot ± 1.8 × exp_move | `options_theta.py:126-129` |
| Wings | spot ± 2.4 × exp_move | `options_engine.py:124-125` |
| exp_move | `close × vix/100 × sqrt(5/365)` | `options_theta.py:126`, verbatim |
| Entry | at the daily close | `entry_c = df.iloc[i]["close"]` |
| Timing | **exactly 5 trading sessions before expiry** | `df.iloc[i+1:i+6]` and `sqrt(5/365)` both mean five sessions |
| Exit | held to expiry; no stop, target or roll | no such code exists in either implementation |

The two-strike `simulate_weekly_condors` is a degraded implementation of the
documented condor, not a different strategy. Building four legs implements the
spec; it does not invent one.

### Still unresolved — STRATEGY-OWNER DECISION REQUIRED
- **RSI band inconsistency**: the class declares 40/68, the simulator hardcodes 38/70.
- **Time scaling**: `exp_move` uses `sqrt(5/365)` while the position is held ~7
  calendar days. True holding-period sigma is 1.183× larger, so a strike labelled
  **1.8 SD actually sits at ~1.52 SD**. Reported, deliberately **not corrected** —
  changing the formula would change the strategy.
- **Margin basis**: SPAN is not obtainable read-only. The old `55000.0` per lot is
  fabricated. All headline figures here are per-lot and margin-independent.

---

## 3. What the original research fabricated

| Quantity | Original | Authentic (measured) | Error |
|---|---|---|---|
| Credit per lot | `2500 × (1.5/1.8)` = ₹2,083 | **₹656** (10.09 pts × 65) | **3.2× overstated** |
| Loss on breach | `−1.5 × credit` = ₹3,125 | **₹4,776** (73.48 pts) | 1.5× understated |
| Max loss | not modelled | **₹14,600** (224.69 pts) | absent |
| Margin | `55000.0`/lot | unverifiable | fabricated |
| Costs | `140`/lot flat | **₹121**/lot, side-aware | crudely approximated |

---

## 4. Execution model, and a correction to my own earlier claim

- **Entry**: each leg's own traded close, and only if that contract actually
  traded. An untraded contract's close is a theoretical settlement value — on
  2025-01-02 untraded deep-ITM closes deviated from intrinsic by up to **627.90**
  versus **1.38 mean** for traded ones.
- **Exit**: exact cash settlement against the exchange's official settlement
  price. The legacy archive publishes `SETTLE_PR = 0.0` on 2019–2020 expiry rows,
  so the engine fails closed and falls back to the NSE index close — **verified
  identical on 90/90 sessions where both exist (max diff 0.0)**, so it is a second
  reading of the same number, not a proxy.
- **Costs**: side-aware. The generic roundtrip helper charges a short leg's STT on
  its *exit*, which is zero for an option expiring worthless; the real liability is
  0.1% of the premium received at entry, plus 0.125% exercise STT on ITM longs.

**Correction.** I earlier reported that "every variant flips negative under
adverse fills." That test priced entries at the worst tick of the **whole
session**, which is the wrong bound for a strategy that enters at the close.
Measured on 5-minute bars at Bot 1's own strike offsets, the daily close fell
inside the **closing half-hour range on 223 of 223 observations**, and that window
spans only **17.7%** of the full-day range. The close is achievable. The full-day
figure is retained solely as a floor.

---

## 5. Result

### 5.1 Priced backtest (UDiFF era, where an authentic lot size exists)
74 trades: 94.59% win rate, +₹43,228/lot, breach rate 5.41%.

### 5.2 The decisive study — full history, 158 priced weekly cycles (2019-02 → 2026-09)
Breach outcome and credit both need only points, not lot size, so this spans the
whole sample rather than the UDiFF era.

| | value |
|---|---|
| observed credit | **10.09 pts** (median 9.05, min 0.90, max 55.25) |
| breach rate | **12/164 = 7.32%**, CI95 [3.84%, 12.43%] |
| beyond the wing | 1/164 = 0.61% |
| loss when breached | **73.48 pts** (max 200, wing cap ~183) |
| **gross** | **+4.51 pts/cycle** |
| statutory costs | −1.61 pts/cycle |
| **net, zero slippage** | **+2.90 pts/cycle (₹217/lot), t = +1.40** |
| net @ 0.25 pt/leg | +1.90, t = +0.92 |
| net @ 0.50 pt/leg | +0.90, t = +0.44 |
| net @ 1.00 pt/leg | **−1.10, t = −0.53** |

OOS 70/30: IS +0.81 vs OOS +12.97 pts/cycle — sign agrees, but the in-sample half
is essentially flat. Walk-forward 3/4 folds positive (2021-12 fold: −5.3).

### 5.3 The 2025–26 result was a benign-period artefact

| year | cycles | breached | rate | median VIX |
|---|---|---|---|---|
| 2019 | 20 | 2 | 10.0% | 14.94 |
| 2020 | 7 | 0 | 0.0% | 14.00 |
| 2021 | 19 | 1 | 5.3% | 16.16 |
| 2022 | 21 | 3 | **14.3%** | 17.85 |
| 2023 | 23 | 2 | 8.7% | 11.70 |
| 2024 | 24 | 3 | 12.5% | 13.71 |
| 2025 | 31 | **0** | **0.0%** | 12.49 |
| 2026 | 19 | 1 | 5.3% | 12.60 |

Restricting to 2025–26 gives a 2.27% breach rate and an apparently excellent
strategy. The full history gives 7.32%. **Extending the sample was what changed
the answer** — no parameter moved.

---

## 6. Capital viability

Per lot: max loss **₹14,600**, credit **₹656**, net expectancy **₹217/cycle**.
Sizing on the structural maximum loss (SPAN unverified):

| Capital | Lots at 65% allocation | Weekly expectancy | Worst-case exposure |
|---|---|---|---|
| ₹50,000 | 1 | ₹217 | ₹14,600 |
| ₹1,00,000 | 3 | ₹651 | ₹43,800 |

At ₹1L, one maximum-loss week costs ~67 weeks of expectancy.

---

## 7. Verdict

| | |
|---|---|
| Research | **COMPLETE** — four real legs, real prices, real settlement |
| Data | **RESOLVED** — 1,903 sessions, 4.0M rows, full strike coverage |
| Validation | **RUN IN FULL** — OOS, walk-forward, cost and slippage stress, regime, Monte Carlo, multiple-testing |
| Economics | **AUTHENTIC** — no synthetic credit, delta, IV, margin or substituted strike |
| Live parity | **NOT ESTABLISHED** — the live path has no condor execution model |
| **Paper readiness** | **NOT READY** |

**Exact blocker — no longer "insufficient data":** after costs the edge is
**+2.90 points per cycle at t = +1.40**, which is not statistically distinguishable
from zero, does not survive a multiple-testing adjustment across the variants run,
and turns negative at 1 point per leg of slippage. Roughly 158 cycles of authentic
history were not enough to establish an edge because **the edge itself is too small
relative to its own execution cost**, not because the sample was short.

Secondary blockers, both requiring a strategy-owner decision: the RSI band
inconsistency, and the time-scaling defect that places the "1.8 SD" short at
~1.52 SD.

Nothing here claims Bot 1 is profitable, and nothing here claims it is ready for
money.
