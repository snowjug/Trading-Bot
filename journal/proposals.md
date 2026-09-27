# PROPOSALS JOURNAL

Candidate changes produced by `src/research/retrospective.py` from
calibration evidence. **Nothing here has been applied.** Each entry is a
hypothesis with the validation it must pass first; a human promotes it by
editing the target file and recording the outcome below the entry.

The risk boundary, execution path, cost model, decision schema, structure
catalogue and every risk limit are PROTECTED and can never appear as a
target here — `retrospective.PROTECTED` refuses them and a test enforces it.

---

## Batch 2026-09-27T09:30:10

```json
{
  "window": {
    "start": "2022-01-01",
    "end": "2023-12-31"
  },
  "hold_minutes": 60,
  "records": 19644
}
```

### P-20260927-dda48578 — INVERT_FAMILY

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** VWAP_REVERSION|dir=-1 forecasts are systematically WRONG - hit rate 37.1% (brier_delta vs coin flip -0.0532; n_independent=160)

**Why.** The market moved AGAINST the stated direction more often than not, so the family carries information with the sign reversed. That is a stronger finding than absence of signal, and the easiest of all to over-fit: the same data that produced the inversion cannot also validate it.

**Must pass before promotion:**
1. re-score the inverted rule on a DEV window that excludes the one that produced this finding
2. confirm the sign holds in at least two separate years
3. confirm the excess move clears the measured option friction (~4.4 points per 2-leg round trip)
4. check it is not an artefact of the index's upward drift by comparing long and short sides separately

**Risk of acting on this.** Inverting a rule doubles the multiple-testing surface: the same data now supports two hypotheses. Treat as a NEW hypothesis needing its own out-of-sample window.

<details><summary>evidence</summary>

```json
{
  "scope": "VWAP_REVERSION|dir=-1",
  "n_directional": 383,
  "n_independent": 160,
  "hit_rate": 37.1,
  "brier_agent": 0.30324,
  "brier_coinflip": 0.25,
  "brier_delta_vs_coinflip": -0.05324,
  "brier_delta_vs_base_rate": -0.06994
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-45edd4ac — INVERT_FAMILY

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** VWAP_REVERSION forecasts are systematically WRONG - hit rate 41.9% (brier_delta vs coin flip -0.0421; n_independent=285)

**Why.** The market moved AGAINST the stated direction more often than not, so the family carries information with the sign reversed. That is a stronger finding than absence of signal, and the easiest of all to over-fit: the same data that produced the inversion cannot also validate it.

**Must pass before promotion:**
1. re-score the inverted rule on a DEV window that excludes the one that produced this finding
2. confirm the sign holds in at least two separate years
3. confirm the excess move clears the measured option friction (~4.4 points per 2-leg round trip)
4. check it is not an artefact of the index's upward drift by comparing long and short sides separately

**Risk of acting on this.** Inverting a rule doubles the multiple-testing surface: the same data now supports two hypotheses. Treat as a NEW hypothesis needing its own out-of-sample window.

<details><summary>evidence</summary>

```json
{
  "scope": "VWAP_REVERSION",
  "n_directional": 618,
  "n_independent": 285,
  "hit_rate": 41.9,
  "brier_agent": 0.29212,
  "brier_coinflip": 0.25,
  "brier_delta_vs_coinflip": -0.04212,
  "brier_delta_vs_base_rate": -0.04867
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-6985894d — DISABLE_FAMILY

- **target** `configs/market.yaml` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** BREAKOUT shows no directional skill (brier_delta vs coin -0.0999, vs base rate -0.1012, n_independent=1040)

**Why.** Beating neither a coin flip nor the realised base rate means the family pays friction for nothing. The proposal is to stop emitting it, not to retune it — retuning a family with no measured signal is how thresholds get fitted to noise.

**Must pass before promotion:**
1. confirm on a second window
2. confirm the family's trades are not carrying the portfolio in some regime the aggregate hides

**Risk of acting on this.** Disabling a family reduces trade count, which widens the confidence interval on everything that remains.

<details><summary>evidence</summary>

```json
{
  "scope": "BREAKOUT",
  "n_directional": 2763,
  "n_independent": 1040,
  "hit_rate": 53.6,
  "brier_delta_vs_coinflip": -0.09986,
  "brier_delta_vs_base_rate": -0.10116
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-7b49cb7a — DISABLE_FAMILY

- **target** `configs/market.yaml` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** BREAKOUT|dir=+1 shows no directional skill (brier_delta vs coin -0.0916, vs base rate -0.0952, n_independent=597)

**Why.** Beating neither a coin flip nor the realised base rate means the family pays friction for nothing. The proposal is to stop emitting it, not to retune it — retuning a family with no measured signal is how thresholds get fitted to noise.

**Must pass before promotion:**
1. confirm on a second window
2. confirm the family's trades are not carrying the portfolio in some regime the aggregate hides

**Risk of acting on this.** Disabling a family reduces trade count, which widens the confidence interval on everything that remains.

<details><summary>evidence</summary>

```json
{
  "scope": "BREAKOUT|dir=+1",
  "n_directional": 1658,
  "n_independent": 597,
  "hit_rate": 56.0,
  "brier_delta_vs_coinflip": -0.09157,
  "brier_delta_vs_base_rate": -0.09521
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-e73f6576 — DISABLE_FAMILY

- **target** `configs/market.yaml` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** BREAKOUT|dir=-1 shows no directional skill (brier_delta vs coin -0.1123, vs base rate -0.1123, n_independent=451)

**Why.** Beating neither a coin flip nor the realised base rate means the family pays friction for nothing. The proposal is to stop emitting it, not to retune it — retuning a family with no measured signal is how thresholds get fitted to noise.

**Must pass before promotion:**
1. confirm on a second window
2. confirm the family's trades are not carrying the portfolio in some regime the aggregate hides

**Risk of acting on this.** Disabling a family reduces trade count, which widens the confidence interval on everything that remains.

<details><summary>evidence</summary>

```json
{
  "scope": "BREAKOUT|dir=-1",
  "n_directional": 1105,
  "n_independent": 451,
  "hit_rate": 50.0,
  "brier_delta_vs_coinflip": -0.1123,
  "brier_delta_vs_base_rate": -0.1123
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-4f112129 — DISABLE_FAMILY

- **target** `configs/market.yaml` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** VWAP_REVERSION|dir=+1 shows no directional skill (brier_delta vs coin -0.0240, vs base rate -0.0240, n_independent=125)

**Why.** Beating neither a coin flip nor the realised base rate means the family pays friction for nothing. The proposal is to stop emitting it, not to retune it — retuning a family with no measured signal is how thresholds get fitted to noise.

**Must pass before promotion:**
1. confirm on a second window
2. confirm the family's trades are not carrying the portfolio in some regime the aggregate hides

**Risk of acting on this.** Disabling a family reduces trade count, which widens the confidence interval on everything that remains.

<details><summary>evidence</summary>

```json
{
  "scope": "VWAP_REVERSION|dir=+1",
  "n_directional": 235,
  "n_independent": 125,
  "hit_rate": 49.8,
  "brier_delta_vs_coinflip": -0.02399,
  "brier_delta_vs_base_rate": -0.02399
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-b0e08286 — RECALIBRATE_CONFIDENCE

- **target** `src/agent/deciders.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** the confidence mapping overstates 3 scope(s); worst BREAKOUT|dir=-1 asserts 0.83 and delivers 50.0% (gap +0.33, n_independent=451)

**Why.** ONE proposal rather than one per family, because the number comes from a single expression in the decider - `0.45 + 0.15 * score` - which reaches 0.90-1.00 for an aligned MEDIUM or HIGH setup. The direction is not reversed in any of these scopes (every hit rate is at or above a coin flip), so this is a calibration fault, not a signal fault, and inverting them would make things worse. It matters because `direction_score` is consumed downstream as a probability: asserting 0.90 on a setup that resolves near 0.50 misstates the evidence to every consumer.

**Must pass before promotion:**
1. confirm the gap on a second window before changing the mapping
2. re-fit the quality->score mapping on DEV only, then report the Brier on a window not used for the fit
3. check the gap per quality_hint bucket separately: a single shrink factor is only correct if the miscalibration is uniform across LOW/MEDIUM/HIGH
4. confirm shrinking the score does not simply route every decision to NO_TRADE through the risk gate's confidence floor, which would make the change look harmless while silently disabling the agent

**Risk of acting on this.** A confidence number is an input to the risk boundary, so lowering it is the safe direction (fewer, smaller trades). The danger is the opposite of usual: the mapping must not be re-fitted on the window that measured the gap, or the new numbers are fitted noise wearing a calibration label.

<details><summary>evidence</summary>

```json
{
  "scope": "BREAKOUT|dir=-1",
  "worst_gap": 0.327,
  "n_independent": 451,
  "scopes": [
    {
      "scope": "BREAKOUT|dir=-1",
      "gap": 0.327,
      "mean_score": 0.827,
      "hit_rate": 50.0,
      "n_independent": 451
    },
    {
      "scope": "BREAKOUT",
      "gap": 0.298,
      "mean_score": 0.834,
      "hit_rate": 53.6,
      "n_independent": 1040
    },
    {
      "scope": "BREAKOUT|dir=+1",
      "gap": 0.279,
      "mean_score": 0.839,
      "hit_rate": 56.0,
      "n_independent": 597
    }
  ]
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-87c5916d — RETUNE

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** BREAKOUT magnitude estimate is worse than the option market's implied move (MAE 23.6 vs 21.82 pts, bias 0.322x)

**Why.** The expected-move figure is what the risk gate uses to justify a debit structure. If it is less accurate than the straddle the market is quoting, the agent has no volatility skill and that figure should not be the basis of a debit trade.

**Must pass before promotion:**
1. re-measure with the market implied move on the same horizon
2. check whether using the straddle-implied move directly, instead of an ATR multiple, changes the gate's decisions

**Risk of acting on this.** Adopting the market's implied move makes the gate stricter, which is the safe direction, but it will cut trade count.

<details><summary>evidence</summary>

```json
{
  "scope": "BREAKOUT",
  "n_magnitude": 2763,
  "mae_agent_pts": 23.6,
  "mae_market_pts": 21.82,
  "magnitude_bias_ratio": 0.322,
  "mean_expected_pts": 9.96,
  "mean_realised_abs_pts": 30.92
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-e9b84405 — RETUNE

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** BREAKOUT|dir=+1 magnitude estimate is worse than the option market's implied move (MAE 21.59 vs 21.18 pts, bias 0.329x)

**Why.** The expected-move figure is what the risk gate uses to justify a debit structure. If it is less accurate than the straddle the market is quoting, the agent has no volatility skill and that figure should not be the basis of a debit trade.

**Must pass before promotion:**
1. re-measure with the market implied move on the same horizon
2. check whether using the straddle-implied move directly, instead of an ATR multiple, changes the gate's decisions

**Risk of acting on this.** Adopting the market's implied move makes the gate stricter, which is the safe direction, but it will cut trade count.

<details><summary>evidence</summary>

```json
{
  "scope": "BREAKOUT|dir=+1",
  "n_magnitude": 1658,
  "mae_agent_pts": 21.59,
  "mae_market_pts": 21.18,
  "magnitude_bias_ratio": 0.329,
  "mean_expected_pts": 9.37,
  "mean_realised_abs_pts": 28.45
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-d515ed42 — RETUNE

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** BREAKOUT|dir=-1 magnitude estimate is worse than the option market's implied move (MAE 26.62 vs 22.78 pts, bias 0.313x)

**Why.** The expected-move figure is what the risk gate uses to justify a debit structure. If it is less accurate than the straddle the market is quoting, the agent has no volatility skill and that figure should not be the basis of a debit trade.

**Must pass before promotion:**
1. re-measure with the market implied move on the same horizon
2. check whether using the straddle-implied move directly, instead of an ATR multiple, changes the gate's decisions

**Risk of acting on this.** Adopting the market's implied move makes the gate stricter, which is the safe direction, but it will cut trade count.

<details><summary>evidence</summary>

```json
{
  "scope": "BREAKOUT|dir=-1",
  "n_magnitude": 1105,
  "mae_agent_pts": 26.62,
  "mae_market_pts": 22.78,
  "magnitude_bias_ratio": 0.313,
  "mean_expected_pts": 10.84,
  "mean_realised_abs_pts": 34.63
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-12d7153d — RETUNE

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** OPTIONS_VOL_CHEAP magnitude estimate is worse than the option market's implied move (MAE 50.68 vs 20.34 pts, bias 2.527x)

**Why.** The expected-move figure is what the risk gate uses to justify a debit structure. If it is less accurate than the straddle the market is quoting, the agent has no volatility skill and that figure should not be the basis of a debit trade.

**Must pass before promotion:**
1. re-measure with the market implied move on the same horizon
2. check whether using the straddle-implied move directly, instead of an ATR multiple, changes the gate's decisions

**Risk of acting on this.** Adopting the market's implied move makes the gate stricter, which is the safe direction, but it will cut trade count.

<details><summary>evidence</summary>

```json
{
  "scope": "OPTIONS_VOL_CHEAP",
  "n_magnitude": 9833,
  "mae_agent_pts": 50.68,
  "mae_market_pts": 20.34,
  "magnitude_bias_ratio": 2.527,
  "mean_expected_pts": 78.21,
  "mean_realised_abs_pts": 30.95
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-e9fb7809 — RETUNE

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** OPTIONS_VOL_RICH magnitude estimate is worse than the option market's implied move (MAE 41.72 vs 21.95 pts, bias 2.142x)

**Why.** The expected-move figure is what the risk gate uses to justify a debit structure. If it is less accurate than the straddle the market is quoting, the agent has no volatility skill and that figure should not be the basis of a debit trade.

**Must pass before promotion:**
1. re-measure with the market implied move on the same horizon
2. check whether using the straddle-implied move directly, instead of an ATR multiple, changes the gate's decisions

**Risk of acting on this.** Adopting the market's implied move makes the gate stricter, which is the safe direction, but it will cut trade count.

<details><summary>evidence</summary>

```json
{
  "scope": "OPTIONS_VOL_RICH",
  "n_magnitude": 5767,
  "mae_agent_pts": 41.72,
  "mae_market_pts": 21.95,
  "magnitude_bias_ratio": 2.142,
  "mean_expected_pts": 69.35,
  "mean_realised_abs_pts": 32.38
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-e9765905 — RETUNE

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** VWAP_REVERSION magnitude estimate is worse than the option market's implied move (MAE 21.26 vs 20.09 pts, bias 1.191x)

**Why.** The expected-move figure is what the risk gate uses to justify a debit structure. If it is less accurate than the straddle the market is quoting, the agent has no volatility skill and that figure should not be the basis of a debit trade.

**Must pass before promotion:**
1. re-measure with the market implied move on the same horizon
2. check whether using the straddle-implied move directly, instead of an ATR multiple, changes the gate's decisions

**Risk of acting on this.** Adopting the market's implied move makes the gate stricter, which is the safe direction, but it will cut trade count.

<details><summary>evidence</summary>

```json
{
  "scope": "VWAP_REVERSION",
  "n_magnitude": 618,
  "mae_agent_pts": 21.26,
  "mae_market_pts": 20.09,
  "magnitude_bias_ratio": 1.191,
  "mean_expected_pts": 35.28,
  "mean_realised_abs_pts": 29.61
}
```

</details>

**Operator decision:** _(unfilled)_

---

### P-20260927-98ae9b0a — RETUNE

- **target** `src/market/setups.py` (proposable; not protected)
- **status** `PROPOSED` — not applied
- **finding** VWAP_REVERSION|dir=+1 magnitude estimate is worse than the option market's implied move (MAE 25.62 vs 22.29 pts, bias 1.144x)

**Why.** The expected-move figure is what the risk gate uses to justify a debit structure. If it is less accurate than the straddle the market is quoting, the agent has no volatility skill and that figure should not be the basis of a debit trade.

**Must pass before promotion:**
1. re-measure with the market implied move on the same horizon
2. check whether using the straddle-implied move directly, instead of an ATR multiple, changes the gate's decisions

**Risk of acting on this.** Adopting the market's implied move makes the gate stricter, which is the safe direction, but it will cut trade count.

<details><summary>evidence</summary>

```json
{
  "scope": "VWAP_REVERSION|dir=+1",
  "n_magnitude": 235,
  "mae_agent_pts": 25.62,
  "mae_market_pts": 22.29,
  "magnitude_bias_ratio": 1.144,
  "mean_expected_pts": 39.9,
  "mean_realised_abs_pts": 34.87
}
```

</details>

**Operator decision:** _(unfilled)_

---
