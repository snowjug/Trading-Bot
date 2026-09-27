# FORECAST CALIBRATION: DEV vs VALIDATION

**Run:** 2026-09-27 · **NIFTY 5-minute** · 60-minute hold · authentic traded option bars
**DEV** 2022-01-01 → 2023-12-31 — 19,644 forecasts
**VAL** 2024-01-01 → 2025-09-17 — 18,916 forecasts
**HOLDOUT** 2025-09-18 → 2026-09-18 — **NOT TOUCHED**
**Reproduce:** `python scripts/research/run_calibration.py --start <a> --end <b>`
**`LIVE_TRADING_ENABLED`:** `false` · Dhan read-only, market data only

---

## 1. WHY THIS INSTRUMENT

Replay P&L said the agent lost ₹131,883 at t = −5.62. That single number cannot
separate *"it has no view"* from *"it has a view it cannot afford to express"*, because
it is dominated by friction. This grades the **assertion** instead: the agent states a
direction with a confidence, and a move size over a declared horizon. Both are scored
against baselines it must beat to have said anything at all —

- a coin flip at p = 0.50
- **the realised base rate on the same bars**, which already contains the index's drift,
  so drift cannot masquerade as skill
- for magnitude, **the option market's own ATM straddle**, scaled to the same horizon

A family is credited with skill only if it beats *both* directional baselines.

`n` is forecast records; **`n_indep`** is the maximal set whose 60-minute forward
windows do not overlap. On 5-minute bars consecutive records share 11/12 of their
window, so `n` overstates the sample ~12× and every threshold uses `n_indep`. Point
estimates use all records (each is a valid, merely correlated, draw); error bars use
`n_indep`.

`z` below is how many conservative standard errors (`0.5/√n_indep`) the hit rate sits
**below** a coin flip. Positive `z` = wrong more often than right. The inversion bar is
`z > 1.5`.

---

## 2. THE COMPARISON

| scope | DEV hit% | n | z | VAL hit% | n | z | replicates? |
|---|---|---|---|---|---|---|---|
| BREAKOUT | 53.6 | 1040 | −2.32 | 51.2 | 869 | −0.71 | neither |
| BREAKOUT dir=+1 | 56.0 | 597 | **−2.93** | 50.8 | 511 | −0.36 | **no** |
| BREAKOUT dir=−1 | 50.0 | 451 | 0.00 | 51.7 | 369 | −0.65 | neither |
| **VWAP_REVERSION** | **41.9** | 285 | **+2.73** | **39.9** | 200 | **+2.86** | **YES — both** |
| VWAP_REVERSION dir=+1 | 49.8 | 125 | +0.04 | **36.4** | 83 | **+2.48** | **VAL only** |
| VWAP_REVERSION dir=−1 | **37.1** | 160 | **+3.26** | 42.1 | 117 | +1.71 | both, **much weaker** |

---

## 3. WHAT SURVIVED, AND WHAT I GOT WRONG

### 3.1 SURVIVED — VWAP_REVERSION is wrong as a family, in both windows

41.9% then 39.9%, at z = +2.73 and +2.86 on independent samples of 285 and 200. Two
non-overlapping multi-year windows agree. This is the one directional finding in the
repository that has now been measured twice and held.

### 3.2 REFUTED — my explanation for it, and the side I attributed it to

My previous report (`AGENT_SETUP_EDGE_FINDINGS.md` §2.2) said the **short side** was the
inverted one and offered a mechanism:

> fading a move **down** works because the index drifts up; fading a move **up** fights
> that drift and loses

**The validation window refutes that.** The side that is wrong swapped:

- `dir=−1` (fade a move up) weakened from z = +3.26 to **+1.71**
- `dir=+1` (fade a move down) went from z = +0.04 — nothing at all — to **+2.48**

If the drift mechanism were right, `dir=+1` should be the *reliable* side. It is now the
worse one. The mechanism is dead, and the DEV-specific claim that the short side
carries the inversion was **an artefact of that window.**

What is consistent with both windows is simpler and makes no appeal to drift: **after a
VWAP stretch, NIFTY continues rather than reverting, on either side, at a 60-minute
horizon.** That predicts both sides wrong, which is what VAL shows and what DEV shows
partially.

Had a side-specific inversion been promoted off DEV — the obvious move — VAL would have
refuted it. The proposal's own validation list required exactly this check
("*check it is not an artefact of the index's upward drift by comparing long and short
sides separately*"), and the check is what caught it.

### 3.3 REFUTED — BREAKOUT's apparent long-side edge

`BREAKOUT dir=+1` hit **56.0%** in DEV at z = −2.93, i.e. nearly three standard errors
**better** than a coin flip. In VAL it is **50.8%**, z = −0.36. The DEV figure was
window-specific noise, and it is the most seductive number in the whole table because
it points the profitable way. It did not replicate.

Across both windows BREAKOUT beats neither baseline. Two measurements, ~1,900
independent observations, nothing there.

---

## 4. THE TWO FINDINGS THAT REPLICATE ALMOST EXACTLY

These are properties of the code, not of the market, which is why they are stable.

### 4.1 The confidence mapping overstates by ~0.3, in both windows

| scope | DEV asserted → delivered | VAL asserted → delivered |
|---|---|---|
| BREAKOUT dir=+1 | 0.84 → 56.0% (**+0.28**) | 0.84 → 50.8% (**+0.33**) |
| BREAKOUT dir=−1 | 0.83 → 50.0% (**+0.33**) | 0.82 → 51.7% (**+0.30**) |
| VWAP_REVERSION | 0.62 → 41.9% (**+0.21**) | 0.62 → 39.9% (**+0.23**) |

`direction_score` comes from one expression in the decider — `0.45 + 0.15 · score` —
which reaches 0.90–1.00 for an aligned MEDIUM or HIGH setup. It is consumed downstream
as a probability. **Asserting 0.83 on a coin flip is the single most reproducible defect
in this system**, and it is one line of code, not a per-family problem.

### 4.2 Magnitude: the options families overstate the move ~2×, and BREAKOUT understates 3×

| family | DEV bias | VAL bias | reading |
|---|---|---|---|
| OPTIONS_VOL_CHEAP | 2.53× | 2.81× | states a **daily ATR** over a session horizon |
| OPTIONS_VOL_RICH | 2.14× | 1.76× | same cause |
| VWAP_REVERSION | 1.19× | 1.29× | mildly over |
| VOLATILITY_EXPANSION | 0.52× | 0.56× | understates ~2× |
| **BREAKOUT** | **0.322×** | **0.323×** | understates 3×, to the third decimal |

BREAKOUT reproducing 0.322× and 0.323× across two independent windows is not a market
fact — it is a deterministic scaling error. In every one of these families the ATM
straddle's implied move is the **more accurate** estimate of the realised move, so the
`expected_move_points` currently used to justify a debit structure should not be.

This is the same class of error as the stop-units and expected-move-horizon bugs found
earlier, caught this time by an external yardstick rather than by inspection.

---

## 5. WHAT THIS DOES **NOT** ESTABLISH

1. **No P&L claim.** A 39.9% hit rate inverts to ~60% directional accuracy, but hit rate
   is not profit. VWAP_REVERSION's own magnitude estimate is 1.2–1.3× too large and less
   accurate than the straddle's, and a 2-leg structure costs ~4.4 points per round trip.
   **An inverted-rule P&L test has not been run.** Until it is, this is a forecasting
   result, not a strategy.
2. **Not an out-of-sample edge.** DEV and VAL were both used to *measure*. The 2025-09-18
   → 2026-09-18 holdout is untouched and must stay that way until a specific rule is
   frozen.
3. **Multiple testing.** Six scopes × two windows. The family-level replication is
   meaningful precisely because it survived a second window; no single cell should be
   read as a discovery, including `VWAP_REVERSION dir=+1`'s z = +2.48.
4. **The detector, not the agent.** Every bar where a family fires is scored, not only
   bars the agent would have traded. The risk gate and decider filters are not applied.
   These are the *detector's* forecasts.
5. **One underlying, one hold.** NIFTY, 60 minutes. The side attribution proved unstable
   across windows; it may be unstable across horizons too.

---

## 6. BOTTOM LINE

> VWAP_REVERSION is wrong as a family in two independent multi-year windows, at z ≈ 2.8
> both times. But **which side** is wrong is not stable, and the drift mechanism I
> published for it is refuted — so the specific inversion I flagged as "the one concrete
> lead" would have been fitted to its own window. BREAKOUT's 56% long side did not
> replicate either.
>
> The findings that reproduce to two decimal places are both bugs in this codebase: the
> decider asserts ~0.83 confidence on coin flips, and every family's expected-move
> figure is less accurate than the ATM straddle it is competing with.

Nothing has been promoted. `journal/proposals.md` carries the proposals; the target
files are unchanged. `LIVE_TRADING_ENABLED` remains `false`.
