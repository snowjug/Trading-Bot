# FINAL 6-MONTH MONEY STUDY

**Holdout:** 2026-03-18 → 2026-09-18 — 125 index sessions, 27 expiry sessions, 17 weekly cycles.
**Splits:** DEV 2020-09-01 → 2024-09-17 (1,001 sessions) · VAL 2024-09-18 → 2026-03-17 (371) · HOLDOUT frozen.
**Search:** 31 distinct concepts, ~100 implementations, 5 rounds. Every rule was fixed before the holdout opened.
**Execution:** each side pays `max(1 tick, 0.30% of premium)` half-spread + 2 ticks slippage, plus statutory
charges (IndianCostModel, side-aware STT, 0.125% exercise STT on ITM longs). Harsher than the 0.22% spread
observed live on 2026-09-18. Cost sensitivity run at 1.0× / 1.5× / 2.0×.
**LIVE_TRADING_ENABLED = false. Paper only. Dhan read-only.**

---

# MONEY RESULT

The frozen five-bot system, equal sleeves across the bots that can execute, whole lots only, ≤60% of the
account at risk in one position.

## ₹20,000

| | |
|---|---|
| NET P&L | **NOTHING EXECUTABLE** |
| RETURN % | — |
| MAX DD | — |
| PROFITABLE DAYS | — |
| % DAYS ≥ +1% | — |
| % DAYS ≥ +2% | — |

No bot fits a ₹5,000 sleeve. One lot needs ₹11,491 (BOT 6), ₹12,706 (BOT 1), ₹15,735 (BOT 7), ₹38,415 (BOT 2).
Committing the **entire** ₹20,000 to a single bot, only BOT 6 fits — 1 lot, **−₹14,587, −72.93%, max DD 106.82%**.

**₹20,000 cannot run this system.**

## ₹50,000

| | |
|---|---|
| NET P&L | **−₹14,587** |
| RETURN % | **−29.17%** |
| MAX DD | ₹21,365 (42.73%) |
| PROFITABLE DAYS | 9 of 125 = 7.2% (of 19 traded days: 47.4%) |
| % DAYS ≥ +1% | 5.6% |
| % DAYS ≥ +2% | 4.0% |

Only BOT 6 clears a ₹12,500 sleeve, and BOT 6 is the system's worst bot. Avg daily −0.2334%, median 0.0000%,
worst day −₹5,512, longest losing-day streak 5.

## ₹1,00,000

| | |
|---|---|
| NET P&L | **−₹17,956** |
| RETURN % | **−17.96%** |
| MAX DD | ₹40,808 (40.81%) |
| PROFITABLE DAYS | 24 of 125 = 19.2% (of 36 traded days: 66.7%) |
| % DAYS ≥ +1% | 7.2% |
| % DAYS ≥ +2% | 4.8% |

Allocation BOT 6 ×2, BOT 7 ×1, BOT 1 ×1. Avg daily −0.1436%, median 0.0000%, best day +₹7,272,
worst day −₹11,080, longest losing-day streak 3.

### Single bot taking the whole account

| Account | BOT 6 | BOT 7 | BOT 1 | BOT 2 |
|---|---|---|---|---|
| ₹20,000 | 1 lot, −72.93% | not executable | not executable | not executable |
| ₹50,000 | 2 lots, −58.35% | 1 lot, +1.31% | 2 lots, **+42.26%** | not executable |
| ₹1,00,000 | 5 lots, −72.93% | 3 lots, +1.96% | 4 lots, **+42.26%** | 1 lot, +20.47% |

**BOT 1's +42.26% is not an edge.** See *Why BOT 1 and BOT 2 are not promoted* below.

---

# BEST STRATEGY

**NONE. No candidate passed the gate.**

The gate was: net positive on development **and** validation, at least 20 validation trades, still positive at
2× cost. Nothing cleared it. The search budget — 31 concepts, ~100 implementations — is exhausted.

| Field | Value |
|---|---|
| BEST STRATEGY | none promoted |
| BEST BOT | none |
| STRATEGY FAMILY | — |
| PAPER STATUS | no new strategy wired; BOT 6 and BOT 8 retired; BOT 1, 2, 7 remain active and unvalidated |

The closest thing to a winner, and why each failed, is below.

---

# PER-BOT HOLDOUT RESULT (per lot)

| Bot | Family | n | Win% | Gross | Costs | **Net** | PF | Max DD | t | One lot needs | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **BOT 1** | weekly condor | 17 | 100% | +12,671 | 2,106 | **+₹10,565** | — | ₹0 | 7.67 | ₹12,706 | **REJECTED** — regime artifact |
| **BOT 2** | weekly vertical | 17 | 100% | +21,543 | 1,077 | **+₹20,466** | — | ₹0 | 8.27 | ₹38,415 | **REJECTED** — regime artifact, not executable ≤₹50k |
| **BOT 6** | micro momentum | 19 | 47.4% | −13,202 | 1,385 | **−₹14,587** | 0.446 | ₹21,365 | −1.34 | ₹11,491 | **RETIRED — loss in both holdouts** |
| **BOT 7** | displacement | 7 | 57.1% | +1,182 | 530 | **+₹653** | 1.141 | ₹3,403 | 0.11 | ₹15,735 | **NOT ESTABLISHED** — 7 trades, t=0.11 |
| **BOT 8** | price action | 0 | — | 0 | 0 | **₹0** | — | ₹0 | — | — | **RETIRED — 0 trades in 125 sessions** |

BOT 6 is the only bot small enough to run at ₹50,000 and it lost 29% of the account. BOT 7 made ₹653 on seven
trades, which is indistinguishable from zero. BOT 8 did not trade at all, for the second consecutive study.

---

# WHY BOT 1 AND BOT 2 ARE NOT PROMOTED

Both show **100% win rates and zero drawdown** over 17 cycles. BOT 1 breached 0 of 17, BOT 2 breached 2 of 17.
A window with no breaches cannot test a breach-risk strategy — it measures the regime, not the strategy.

The previous study settled this for BOT 1 by re-measuring the identical geometry in points over **259 cycles
(2019–2026)**, which needs no lot size and so is not truncated by the post-2024 data gate:

| Window | n | Gross pts/cycle | t | Breach |
|---|---|---|---|---|
| **ALL 2019–2026** | **259** | **+0.15** | **0.06** | 8.5% |
| Pre-2024 | 159 | −4.42 | −1.27 | 10.7% |
| 2024+ | 100 | +7.41 | 3.19 | 5.0% |

Six of eight years lose money. The only two profitable years, 2025 and 2026, are the only two with a **0.0%
breach rate** — and this holdout sits inside them. Net of measured costs the full-sample expectancy is
**−₹113 per cycle**. The max-loss tail fired 6 times in 259 cycles (2.3%), each shedding ~95% of wing width
(≈−₹12,350/lot), four of them at VIX between 12.7 and 20.6.

BOT 2 carries the same regime dependence, a worst cycle of −₹13,434, and needs ₹38,415 for one lot — so it is
**not executable at ₹20,000 or ₹50,000** regardless.

Reporting +42.26% from BOT 1 as an achievable return would be reporting the regime.

---

# THE CENTRAL MEASUREMENT: INTRADAY VOLATILITY HAS COMPRESSED

This explains nearly every negative result in the study.

| Year | % sessions with 09:15–09:29 range ≥ 0.35% | Median day range |
|---|---|---|
| 2020 | 7.1% | 0.928% |
| 2021 | 8.9% | 0.876% |
| **2022** | **10.1%** | **0.965%** |
| 2023 | 2.4% | 0.625% |
| 2024 | 4.5% | 0.728% |
| 2025 | 2.0% | 0.656% |
| 2026 | 2.3% | 0.712% |

By split: DEV 6.8% → VAL 2.4% → **HOLDOUT 1.6%** of sessions qualify at 0.35%.

A bought option must outrun two sides of spread plus theta. Measured here, one round trip costs about **₹74 on
~₹7,000 of premium — 1.05%**. When the index stops moving, that toll stops being payable. It also means any
strategy conditioned on high intraday volatility simply stops trading: in the 125-session holdout only **2
sessions** qualify at the 0.35% threshold.

---

# THE CANDIDATE SEARCH

## Round 1 — 31 distinct concepts, DEV

**25 of 31 were negative before statutory costs**, meaning the signal was absent rather than merely expensive.
Only 3 were net positive, all weak.

| Family | Best result | Verdict |
|---|---|---|
| Opening range breakout (10 variants) | C07 wide-OR +₹47,588 | only the volatility-conditioned one worked |
| Market Intraday Momentum (5 variants) | −₹123,679, t=−4.59 | **academic effect does not transfer** |
| Mean reversion (5 variants) | −₹164,778, t=−9.51 | decisively negative |
| Session anchor / VWAP (3) | −₹78,458, t=−2.45 | negative |
| Previous-day levels (2) | −₹161,408, t=−2.86 | negative |
| Gap (2) | +₹37,776, t=0.87 | weak |
| Trend / channel (2) | +₹35,472, t=0.43 | noise |
| Volatility (3) | −₹35,323 | negative |
| Structure / liquidity sweep (2) | −₹83,203, t=−1.15 | negative |

**Market Intraday Momentum** (Gao, Han, Li & Zhou, *Journal of Financial Economics* 2018 — first half-hour
return predicts last half-hour return, scaled slope 6.94, significant at 1%, on SPY 1993–2013) was the
highest-quality external source in the study. Implemented faithfully — sign of the 09:15–09:45 return sets the
side of a 15:00→15:20 trade, with the paper's volatility and volume conditioning — it returned **−₹123,679 at
t=−4.59, and was gross-negative**, so the sign rule itself fails on NIFTY options. Reported as measured.

## Rounds 2–3 — conditioning, DEV

Restricting ORB to already-wide opening ranges turned a large loser into a winner, and the effect was
neighbourhood-wide (25 of 29 variants positive) with two monotone axes:

```
OR threshold  0.20 → +40,496 | 0.25 → +80,243 | 0.30 → +63,169 | 0.35 → +47,588 | 0.45 → +22,099
reward/risk   1.0  → +22,635 | 1.5  → +47,588 | 2.0  → +58,678 | 2.5  → +81,409 | 3.0  → +78,310
```

Morning and afternoon both worked; strike barely mattered; extra attempts per day diluted the edge.

## Validation — the ORB family failed

| Candidate | DEV net | **VAL net** | VAL n |
|---|---|---|---|
| V1_or0.25_rr1.5 | +₹80,243 | **−₹10,101** | 39 |
| V3_or0.30_rr2.5 | +₹78,701 | **−₹10,361** | 21 |
| V4_or0.25_rr2.5 | +₹80,150 | **−₹5,279** | 39 |
| V5_or0.30_rr1.5 | +₹63,169 | **−₹8,228** | 21 |
| V2_or0.35_rr2.5 | +₹81,409 | +₹25,938 | **9** |
| V6_donch_or0.35 | +₹38,103 | +₹13,930 | **9** |

**PROMOTED: NONE.** Every variant with a usable sample went negative. The two that stayed positive fired 9
times in 371 sessions — because the volatility they depend on had disappeared. On the holdout these produced
**2 trades each** (+₹21,042 and +₹8,219), which at ₹20,000 annualises to a meaningless 105% and is exactly the
"result that depends on one or two trades" that must be discarded.

## The short-premium rebuild, and the artifact I had to catch

Since realised volatility had compressed, the structurally correct response was to be **short** premium, not
long. A defined-risk intraday condor was built and swept across days-to-expiry (derived from the NSE bhavcopy
expiry calendar, not guessed). The result was strikingly clean and monotone:

| DTE | n | Win% | Net | t |
|---|---|---|---|---|
| **0** | 142 | 85.2% | **+₹141,174** | **8.07** |
| 1 | 158 | 57.0% | +₹705 | 0.07 |
| 2 | 153 | 47.7% | −₹9,772 | −1.62 |
| 3 | 137 | 20.4% | −₹31,882 | −8.34 |
| 6 | 128 | 14.1% | −₹35,096 | −12.35 |

The mechanism is right: on expiry day one four-leg round trip buys the entire remaining extrinsic decay; on
any other day it buys one day of theta and the spread costs more.

**It was an artifact.** Closing at 15:10 requires a live quote on all four legs, and on expiry day the wings
are worthless and genuinely stop trading. 68 of 211 development expiry sessions were refused for stale marks —
and the refused sessions had **prior-day range 1.525% against 0.843% for the taken ones**. The filter was
deleting the volatile expiry days, which are the ones that breach.

Removing the need for those quotes — holding to expiry and settling every leg at intrinsic against the
exchange settlement price — gives the honest number:

| | biased | **corrected** |
|---|---|---|
| trades | 142 | **210 of 211 sessions** |
| win rate | 85.2% | **61.9%** |
| breach | 28.9% | **50.5%** |
| net | +₹141,174 | **−₹47,803** |
| t | 8.07 | **−1.18** |

Gross was +₹19/trade against ₹247/trade of costs. Max-loss events: 9. On the holdout the corrected version
returned **−₹4,835 over 23 trades at a 43.5% breach rate**, with 3 max-loss events.

A related artifact was caught in the same family: a 4-step wing appeared far better than a 3-step wing
(+₹179,017 vs −₹46,213) with *identical short strikes*, which is impossible — the wider wing was unavailable
exactly on high-ATR sessions, so its exit bar was being chosen by data availability. Disqualified.

---

# COST SENSITIVITY

Run on validation, not after the holdout, so nothing survives that only clears at base cost.

| Candidate | 1.0× | 1.5× | 2.0× | Survives 2×? |
|---|---|---|---|---|
| V1_or0.25_rr1.5 | −10,101 | −12,840 | −15,578 | no |
| V3_or0.30_rr2.5 | −10,361 | −11,880 | −13,400 | no |
| V4_or0.25_rr2.5 | −5,279 | −8,031 | −10,779 | no |
| V5_or0.30_rr1.5 | −8,228 | −9,753 | −11,279 | no |
| V2_or0.35_rr2.5 | 25,938 | 25,156 | 24,374 | YES — but n=9 |
| V6_donch_or0.35 | 13,930 | 13,201 | 12,476 | YES — but n=9 |

---

# TARGETS ASKED FOR, MEASURED

| Target | Measured | |
|---|---|---|
| ~+1% net on good days | best portfolio: 7.2% of days ≥ +1% at ₹1L, on a **negative** total | not met |
| ~+2% on exceptional days | 4.8% of days at ₹1L, on a negative total | not met |
| 1:2 to 1:3 reward/risk | tested 1:1 → 1:3; DEV favoured 1:2.5, none validated | tested, failed validation |
| ≥68% profitable **days** | 19.2% of all sessions at ₹1L; 66.7% **of traded days** | not met on all sessions |
| ≥60–70% winning trades | BOT 6 47.4%, BOT 7 57.1%; the 100% rates are a zero-breach regime | not met honestly |
| 0.5–2 opportunities/session | best candidates fired 0.07–0.14/session | **not met — by an order of magnitude** |

The ≥68% profitable-days target is unreachable by construction for any of these strategies: they trade on
15–29% of sessions, so most days are flat.

---

# SOURCES USED

| Source | Type | Original market / timeframe | What was testable | Adapted | Result |
|---|---|---|---|---|---|
| Gao, Han, Li & Zhou, "Market intraday momentum", *JFE* 2018 (SSRN 2440866) | peer-reviewed | SPY, 1993–2013, 30-min | sign rule, volatility/volume conditioning, timed exit | first half-hour = 09:15–09:45 vs prior close; last-half-hour trade 15:00→15:20 (data ends 15:25, close auction not modelled) | **−₹123,679, t=−4.59, gross-negative** |
| Public NIFTY/BankNifty ORB write-ups (Zerodha TradingQnA, financewithsai, intradaylab, Medium) | practitioner | NIFTY/BankNifty, 15-min | OR window, stop at opposite side, fixed-R target, square-off, "large-range sessions do better" | 5-min bars, ATM option execution, ATR-scaled sizing | conditioning effect **real on DEV, failed VAL** |
| Published VWAP-pullback continuation framing (TradingView scripts, practitioner guides) | practitioner | ES/NQ futures, 5-min | anchor side, pullback entry, stop through anchor, 1.5–2R | no index volume in dataset → session TWAP and CE+PE option-volume-weighted anchor, both named as such | −₹78,458, t=−2.45 |
| Opening-range / Donchian / gap / liquidity-sweep families | public domain | various | explicit level rules | NIFTY 5-min | see Round 1 table |

Headline performance claims from practitioner sources were **not** carried over — only their rules. No claim
in this report comes from a source; every number is measured on this repository's data.

---

# DATA AND METHOD

| Dataset | Coverage |
|---|---|
| NIFTY 5-min option grid, ATM±6, CE+PE | 1,497 sessions, 2020-09-01 → 2026-09-18, 2.93M bars, 324 strikes, with high/low/IV/OI/volume |
| NIFTY + India VIX daily OHLC | 2019-01 → 2026-09 |
| NSE F&O bhavcopy (all strikes, settlement, expiry calendar) | 2019 → 2026, 4.0M rows |
| Derived session→days-to-expiry map | all 1,497 sessions, from the bhavcopy expiry calendar |

- **No lookahead.** A signal at bar *i* sees session bars 0..*i* and daily rows strictly before the session.
  Exits resolve at bar close — the dataset carries one spot per timestamp, so there is no intrabar path to peek
  at and no ambiguity about whether stop or target was touched first. A level crossed mid-bar fills at that
  bar's close, adverse gap included.
- **No fabricated prices.** Every leg must be quoted with positive volume or the trade is refused.
- **Contract identity preserved.** Strike, CE/PE, lot size and settlement come from authentic sources; the
  grid's uncontrolled days-to-expiry was identified and then controlled from the bhavcopy calendar.
- **SPAN/exposure margin: UNKNOWN.** Not obtainable read-only, not estimated. Capital at risk is premium
  outlaid (long) or (width − credit) × lot (spread).
- **No fractional lots.** Lot size 65.

---

# PAPER STATUS

`LIVE_TRADING_ENABLED = false`, verified in `.env` and asserted by a test. Dhan read-only. PaperBroker is the
only execution path.

**No new strategy was wired**, because none passed the gate. There is nothing to forward-test that was not
already running.

**Two bots are retired**, on measurement rather than opinion (`scripts/run_paper_session.py`):

| Bot | Reason |
|---|---|
| **BOT 6** | −₹2,431 over the 3-month holdout and −₹14,587 over the 6-month holdout (19 trades, 47.4% win, t = −1.34) — the worst bot in the system |
| **BOT 8** | 0 trades in 65 sessions, then 0 trades in 125 sessions — the rules have never produced a measurable entry |

Their code is retained unchanged so the measurements stay reproducible; they are simply no longer evaluated.
`PAPER_BOTS=BOT6,BOT8` re-enables them deliberately for a measurement run.

**Active bots: BOT 1, BOT 2, BOT 7.** All three are disclosed above as unvalidated — BOT 1 and BOT 2 are
profitable only in zero-breach regimes, and BOT 7 rests on 7 trades at t = 0.11. They remain active because
retiring everything would end the paper record, not because they have an edge.

The runner is not currently up: the last completed session is 2026-09-17, and the market is closed.

---

# DASHBOARD STATUS

`python run_paper_dashboard.py` → `http://127.0.0.1:8000`.

`/api/historical` was extended for this study with capital deployed, return on deployed, win rate, expectancy,
profit factor, max drawdown, profitable/losing days, longest losing-day streak, best/worst day, and
% days ≥ +1% / ≥ +2%.

The day-threshold percentages require `PAPER_ACCOUNT_CAPITAL`; without it the endpoint returns `null` rather
than assuming an account size. Every figure is computed from stored trades — a quantity the ledger does not
carry is returned as `null`, never inferred. The stored ledger currently holds one session (2026-09-17) with
no closed trades, so these fields are correctly null today.

---

# HONESTY LEDGER

- No dates cherry-picked, no losers removed, no sessions skipped, nothing tuned on the holdout.
- **Two artifacts of my own making were found and reported rather than shipped**: the 4-step-wing exit selected
  by data availability, and the stale-mark filter deleting volatile expiry sessions. Both produced large fake
  profits (+₹179,017 and +₹141,174). Both are disqualified above.
- The best-looking holdout numbers in the study (+₹21,042 and +₹8,219 from 2 trades each) are **rejected** for
  depending on one or two trades.
- BOT 1 and BOT 2's 100% win rates are disclosed as a zero-breach regime, not an edge.
- Cost sensitivity was run before the holdout, not after.
- Paper and shadow trades are not reported anywhere as historical evidence.
- No bot is declared ready for real money.

---

# REPRODUCTION

| Script | Produces |
|---|---|
| `src/research/lab2.py` | level-based intraday engine (R:R is a property of the setup) |
| `src/research/concepts.py` | the 31 concepts |
| `scripts/research/dev_sweep.py` | round 1 — 31 concepts on DEV |
| `scripts/research/dev_sweep2.py` / `dev_sweep3.py` | rounds 2–3 — conditioning and R:R axes |
| `scripts/research/validate2.py` | the promotion gate + cost sensitivity |
| `src/research/intraday_premium.py` / `scripts/research/dev_premium.py` | intraday short premium |
| `src/research/dte0_condor.py` / `scripts/research/dte0_study.py` | zero-DTE condor, biased and corrected |
| `scripts/research/holdout_6m.py` | the single frozen holdout measurement |
| `scripts/research/money_result_6m.py` | capital scenarios and the daily distribution |
| `scripts/research/condor_regime_check.py` | the 259-cycle regime test that rejects BOT 1 |
