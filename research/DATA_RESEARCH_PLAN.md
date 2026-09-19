# DATA RESEARCH PLAN

**Written:** 2026-09-19 · **Governs:** this clean-room research cycle
**Holdout:** 2025-09-18 → 2026-09-18, frozen (see `reports/HOLDOUT_FREEZE.md` when
a candidate set is frozen)

---

## 1. WHY THIS PLAN EXISTS

The binding constraint identified by the previous cycle is not signal discovery. It
is **instrument economics**:

> NIFTY's measured directional edge is worth ≈15 index points a night. A near-ATM
> weekly option — the only instrument a ₹20k–₹1L account could trade at a credible
> spread — has delta ≈0.5 and pays ≈12 points of overnight theta. The structures
> that capture the whole move needed ≈₹1.7 lakh of margin.

That conclusion rested on "no futures data exists". **That was an intake defect, not
a data fact** (see `research/CLEAN_ROOM_AUDIT.md` §1.1). Index futures have been in
this repository's own data source since 2019-01-02. So the first priority is not a
new signal; it is to acquire the instrument that makes the already-measured signals
tradable, and then re-ask the question.

---

## 2. ACQUISITION PRIORITY

| # | Dataset | Why it is first | Status | Blocker |
|---|---|---|---|---|
| 1 | **NSE F&O futures, all symbols, daily, 2019→2026** | the delta-1 instrument the last cycle called missing; no auth needed | **INGESTING** | none |
| 2 | **Index options for BANKNIFTY / FINNIFTY / MIDCPNIFTY / NIFTYNXT50, daily, 2019→2026** | four untested underlyings, same file | **INGESTING** | none |
| 3 | Full scrip master snapshot | authentic security IDs, lot sizes, expiries | **DONE** | none |
| 4 | Intraday bars for non-NIFTY index options and index futures | intraday work is NIFTY-only today | **DEFERRED** | **Dhan token expired 2026-09-19 08:43:45** |
| 5 | BSE bhavcopy (SENSEX, BANKEX) | 3,156 + 1,000 listed contracts, entirely untested | NOT STARTED | budget |
| 6 | Stock options (OPTSTK, 210 underlyings) | ~36,000 rows/session | NOT STARTED | budget |
| 7 | Survivorship-free equity universe | the equity cross-section is contaminated | NOT STARTED | data not held |

Nothing on this list is allowed to be reported as "strategy failed" while its status
is DEFERRED, NOT STARTED or blocked.

---

## 3. WHAT THE NEW DATA MAKES TESTABLE

Each row is a hypothesis that could not be tested before, with the mechanism stated.

| Family | Instrument | Mechanism | Testable now? |
|---|---|---|---|
| Overnight drift, delta-1 | **NIFTY / BANKNIFTY futures** | the measured +15 pt/night drift with no theta and ~2 crossings instead of 4 | **YES** (daily close→close; close→open needs intraday) |
| Futures basis / roll | NIFTY futures vs spot | carry decay is mechanical and measurable from settlement prices | **YES** |
| Calendar spread | near vs next month futures | term-structure mean reversion | **YES** |
| Cross-index relative value | NIFTY vs BANKNIFTY futures | lead-lag and spread mean reversion between two liquid indices | **YES** |
| Index options on 4 new underlyings | BANKNIFTY / FINNIFTY / MIDCPNIFTY / NIFTYNXT50 | BANKNIFTY is more volatile and more institutionally traded than NIFTY; a premium structure that fails on NIFTY may not fail there | **YES, daily** |
| Stock futures cross-section | FUTSTK, 228 underlyings | a multi-day cross-sectional signal in futures avoids the 0.20% delivery STT that killed the equity version | **YES, daily** |
| Overnight drift in options, non-NIFTY | BANKNIFTY options intraday | needs 09:15/15:25 prints | **NO — token** |

The last row matters: the single cleanest test of the overnight family on a new
underlying is blocked on the credential, not on method.

---

## 4. SPLITS — FIXED BEFORE ANY NEW CANDIDATE

| Split | Window | Use |
|---|---|---|
| DEVELOPMENT | data start → **2024-09-17** | screening, structure choice, all parameter looks |
| VALIDATION | **2024-09-18 → 2025-09-17** | promote / reject, one pass |
| **FINAL HOLDOUT** | **2025-09-18 → 2026-09-18** | measured once, after a written freeze |

**Disclosed contamination carried in from the previous cycle:** calendar-2025 and
calendar-2026 index-level overnight drift figures were displayed before that cycle's
holdout run. Any *overnight* candidate in this cycle therefore cannot claim a fully
blind holdout for that one feature, and must say so. Futures, cross-index and the
four new option underlyings are unaffected — none of their data has been looked at.

---

## 5. RESEARCH BUDGET FOR THIS CYCLE

| Bound | Value |
|---|---|
| Strategy families | 10–14 |
| Concepts per family | 5–15 |
| Parameter neighbourhood per concept | ≤5 values per axis, and only to test smoothness |
| Validation passes per candidate | 1 |
| Holdout runs | **1**, after a written freeze |
| Max distinct implementations | ~150 |

Search is by **economic mechanism**, not by parameter grid. A concept without a
one-sentence mechanism is not implemented.

---

## 6. GATE (restating PART 26, fixed here before results exist)

A candidate may become `PAPER_CANDIDATE` only with **all** of:

authentic data · complete session accounting · no silent selection · no lookahead ·
exact contract identity, expiry and DTE · correct per-leg P&L · realistic execution
and costs · positive DEV · positive VALIDATION · sufficient trade count · stable
neighbouring parameters · survives 2× cost · survives parameter perturbation ·
not a single-regime artefact · research/live parity verified.

Otherwise: `REJECTED`, `UNTESTABLE` or `DATA_LIMITED`.

A high win rate, a profit factor above 1, a Sharpe above 1, a t-stat above 2 or a
positive holdout are each **individually insufficient**. BOT1 is the standing
example: 100% win rate on 27 holdout cycles, and ≈zero net expectancy over 140.

---

## 7. IMMEDIATE SEQUENCE

1. Finish the futures + index-option ingest; build a coverage report from the ledger.
2. Derive authentic pre-2024 lot sizes from futures turnover
   (`VAL_INLAKH × 1e5 / (CONTRACTS × price)`) and **verify stability** before using
   it — the old ingester asserted this is unstable; that claim is itself untested.
3. Build a continuous futures series (near-month, rolled on authentic expiry) with a
   documented roll rule.
4. Re-ask the overnight and trend questions in futures, where cost per unit of delta
   is an order of magnitude lower.
5. Screen the four new index-option underlyings on the daily horizon.
6. Stock-futures cross-section.
7. Freeze, then one holdout run.
