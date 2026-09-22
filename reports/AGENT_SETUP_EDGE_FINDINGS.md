# WHY THE AGENT LOSES: THE SETUPS, NOT THE EXPRESSION

**Run:** 2026-09-22 · **Window:** 2022-01-01 → 2023-12-31 (DEV) · **NIFTY 5-minute**
**Reproduce:** `python scripts/research/setup_edge_test.py --start 2022-01-01 --end 2023-12-31`
**`LIVE_TRADING_ENABLED`:** `false` · Dhan used read-only for market data only

---

## 1. THE QUESTION

The agent's deterministic decider lost **₹131,883** over 43 trades (t = −5.62), worse
than not trading. Two explanations lead to completely different work:

| | Hypothesis | If true, the fix is |
|---|---|---|
| **A** | the setups are fine, the expression is wrong | better structures, stops, sizing |
| **B** | the setups carry no directional information | nothing in options can help — options only add cost |

This test separates them **on the underlying, with no options involved**: for every bar
where a family fires, the index's forward move over realistic holding horizons, signed
by the direction the setup pointed.

Two controls make the answer mean something:

- **Excess over drift.** A "bullish" family in a rising market looks good for free, so
  every number is net of the unconditional mean forward move on the same bars.
  Measured drift: 15m −0.004, 30m +0.081, 60m −0.033, 120m −0.105 points.
- **Non-overlapping samples.** Consecutive 5-minute bars share most of their forward
  window, so observations are thinned to one per horizon length before the t-stat.

37,186 bars produced **4,749 candidate events on 4,452 distinct bars** (12.0%).

---

## 2. THE RESULT

Signed forward move, excess of drift, in index points. A **negative** excess means the
market moved **against** the direction the setup pointed.

| family | dir | 15m | 30m | 60m | 120m |
|---|---|---|---|---|---|
| BREAKOUT | +1 | +0.50 (t=0.88) | +0.01 (t=0.01) | +1.33 (t=0.83) | −0.51 (t=−0.18) |
| BREAKOUT | −1 | +1.05 (t=1.22) | +2.02 (t=1.46) | +1.67 (t=0.76) | +2.48 (t=0.63) |
| VOLATILITY_EXPANSION | 0 | +0.97 (t=1.20) | +1.87 (t=1.52) | +3.28 (t=1.76) | −0.54 (t=−0.17) |
| **VWAP_REVERSION** | **−1** | **−3.24 (t=−2.96)** | **−4.32 (t=−2.54)** | **−7.25 (t=−2.55)** | **−10.62 (t=−1.95)** |
| **VWAP_REVERSION** | **+1** | **+5.77 (t=+2.44)** | +5.07 (t=1.57) | +3.19 (t=0.74) | +3.94 (t=0.54) |

### 2.1 The two families that generated most of the agent's trades have no signal

**BREAKOUT** — 3,352 of the 4,749 events — reaches a maximum |t| of **1.46** across
all eight cells, in either direction. **VOLATILITY_EXPANSION** peaks at **1.76**.
Neither is distinguishable from noise at any horizon an intraday position would use.

That is hypothesis **B** for the bulk of the agent's activity, and it explains the loss
directly: the agent was paying ~4.4 points of option friction per round trip to
express a view with no measurable forward content.

### 2.2 VWAP_REVERSION's short side is systematically BACKWARDS

This is the strongest result in the table and the most useful one.

When the setup said **short** — price stretched above VWAP in a range regime, with an
RSI extreme or a rejection candle — the market went **up**: −3.24 points of excess at
15 minutes (t = −2.96), worsening monotonically to **−10.62 points at 120 minutes**.
Win rate 41.6% falling to 37.4%.

The signal is real and its sign is inverted. What the detector calls "exhaustion above
VWAP" is, on this window, **continuation**.

The long side behaves correctly (+5.77 points at 15m, t = +2.44, 56.0% win), which
gives the asymmetry a plausible mechanism: fading a move **down** works because the
index drifts up; fading a move **up** fights that drift and loses. The family is not
measuring mean reversion — it is measuring where price sits relative to the day's
drift, and only one side of it pays.

### 2.3 Nothing clears the cost bar honestly

A 2-leg NIFTY option structure costs about **4.4 points** of modelled friction per
round trip (measured in the agent replay, not assumed).

Only one cell exceeds it: `VWAP_REVERSION dir=+1 @ 15m`, at +5.77 points. But **20
correlated cells were tested**, and the expected maximum |t| under the null across ~20
such tests is roughly 2.2–2.5. A single t = 2.44 sits inside that range. On n = 191
non-overlapping observations, it is not evidence of an edge.

The only value clearly beyond chance is **t = −2.96**, and it is a family being wrong.

---

## 3. WHAT THIS MEANS FOR THE BUILD

**The machinery is not the problem.** The state engine is causally correct and
pinned by lookahead tests, the accounting reconciles bar-for-bar, the risk boundary
refuses on twelve independent gates, and the two unit bugs the replay exposed are
fixed. None of that produces money, because the candidate engine feeding it has no
signal to express.

So the honest conclusion is **hypothesis B**, and three things follow:

1. **Building better option expression on these families would be wasted effort.** No
   structure converts a +1.3-point, t = 0.83 forward move into a profit against 4.4
   points of friction.
2. **Wiring a model to these same candidates would also be wasted effort** — and this
   corrects the "next required step" in my previous report. A model choosing among
   setups that carry no forward information cannot beat a no-trade baseline; it would
   only produce a more expensive way to lose. The candidate engine has to change first.
3. **The inverted short side is the one concrete, testable lead.** A family that is
   wrong with t = −2.96 is more informative than one that is merely absent. The
   disciplined next test is whether *inverting* it survives out-of-sample — treating
   "stretched above VWAP in a range" as continuation rather than exhaustion. That is a
   hypothesis for DEV, not a result, and it must not be fitted on this window.

---

## 4. A SEPARATE RESULT: NO OTHER UNDERLYING EARNS A SEARCH BUDGET

Measured with the live token on authentic 5-minute bars, 2026-06-01 → 2026-09-18,
ATM straddle at 09:30 against the median session range:

| underlying | sessions | median range | median ATM straddle | **range / premium** | vs NIFTY |
|---|---|---|---|---|---|
| SENSEX | 78 | 0.568% | 0.885% | **0.641** | +5% |
| **NIFTY** | 77 | 0.555% | 0.912% | **0.608** | reference |
| BANKNIFTY | 77 | 0.736% | 2.364% | **0.311** | **−49%** |
| MIDCPNIFTY | 78 | 0.739% | 2.483% | **0.298** | **−51%** |
| FINNIFTY | 78 | 0.706% | 2.429% | **0.290** | **−52%** |

This is the ratio that decides whether a premium **buyer** can pay for the option. It
is comparable across underlyings, and the ranking is unambiguous: BANKNIFTY, MIDCPNIFTY
and FINNIFTY move about a third more than NIFTY but their straddles cost **2.6× more**,
so a buyer is roughly half as well off as in a space already closed by 31 concepts.
SENSEX is +5% on 78 sessions, which is inside noise.

**No underlying earns a fresh search budget for premium buying.** Recorded as a
measurement so it is not re-litigated.

The inversion is worth noting: a ratio of 0.29 means the *seller* collects about 3.4×
the typical realised range. That is a large variance risk premium — but naked short
volatility has no builder in this system by policy, and the defined-risk versions cap
exactly the collection that makes it attractive. Every prior cycle that chased it
found the tail instead.

---

## 5. LIMITATIONS

1. One window (2022–2023 DEV) and one underlying. The families may behave differently
   in other regimes; nothing here is an out-of-sample claim.
2. `VOLATILITY_EXPANSION` is non-directional, so a signed forward return is the wrong
   test for it. Its |t| ≤ 1.76 rules out a directional edge, not a volatility one — an
   absolute-move test would be the right instrument and was not run.
3. Forward moves are index points on the underlying. They are an upper bound on what
   any option structure could capture, never a lower bound.
4. The reported artifact was transcribed from the completed run's own output after a
   numpy-serialisation error at write time; the serialisation is fixed and a re-run
   writes it directly.
5. Multiple testing is acknowledged rather than corrected: with 20 correlated cells no
   single t near 2.4 should be treated as a discovery, including the one that favours
   the strategy.

---

## 6. BOTTOM LINE

> The agent works. The setups do not. Two of three families carry no directional
> information at any intraday horizon, the third is inverted on its short side with
> the strongest t-stat in the table, and nothing clears 4.4 points of option friction
> once multiple testing is taken seriously.

`LIVE_TRADING_ENABLED` remains **false**. Nothing is promoted to paper trading.
