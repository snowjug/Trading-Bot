# Strategy Parity Audit — Runtime vs Research

Baseline: `41deaf0` → corrective branch `fix/codex-xhigh-corrective`
Safety gate: `LIVE_TRADING_ENABLED = false`

Classification rule applied: **importing the same class is not parity.** A bot is
PASS only when the live runtime supplies the features the canonical strategy
reads, the entry decision is the strategy's own output, and contract/position
construction is either specified by the research or is a single-leg ATM contract
the research itself assumes.

---

## 1. Six-bot parity matrix

| Bot | Canonical class | Live adapter | Parity | Evidence |
|---|---|---|---|---|
| 1 Apex VRP | `NiftyWeeklyIronCondorStrategy` | bound, **entry gated off** | **FAIL → fails closed** | Research `generate_signals` emits only a rangebound 0/1 flag. Strike construction exists solely in `simulate_weekly_condors` (backtest-only, `@staticmethod`), which models **two short strikes and no wings** despite `wing_sd=2.4`, and books a **fabricated flat credit** (`credit_per_lot = 2500.0 * (1.5/otm_sd)`) and a fabricated `margin_per_lot = 55000.0`. Runtime built an unhedged ±300 strangle — materially different. Live entries now return `STRATEGY_PARITY_UNRESOLVED`. |
| 2 Zen Curvature | `CurvatureCreditSpreadStrategy` | bound, **entry gated off** | **FAIL → fails closed** | Research `generate_signals` emits only `vix < max_vix`. The RSI-branched Bull Put / Bear Call / Condor selection and the overnight holding semantics appear **only in the docstring and in a backtest-only simulator**. Runtime was a fixed same-day call vertical with forced EOD close. Live entries now return `STRATEGY_PARITY_UNRESOLVED`. |
| 3 Confluence Gamma | `ConfluenceGammaScalperStrategy` | `LiveStrategyAdapter` | **PASS** | Strategy computes all indicators internally from the OHLCV frame (`compute_indicators`); adapter supplies authentic daily history + forming bar. Single-leg ATM CE/PE matches the research's stated instrument. Direction taken from `signal`. |
| 4 Golden Trend | `GoldenTrendOptionBuyerStrategy` | `LiveStrategyAdapter` | **PARTIAL** | Signal path is faithful (indicators computed internally). **Divergence:** only the bullish CE leg is implemented live; a `-1` signal cannot be acted on. Recorded as an unsupported-direction rejection, not silently dropped. |
| 5 Velocity-5 | `ActiveMomentumOptionScalperStrategy` | `LiveStrategyAdapter` | **PASS** | Indicators internal; both CE and PE branches implemented and direction-matched. |
| 6 Micro Sniper | `MicroMomentumBuyerStrategy` | `LiveStrategyAdapter` | **PASS** | Indicators internal; reads `df["vix"]`, which the adapter now supplies from **real INDIA VIX** (previously would have defaulted to 15.0). Both directions implemented. **Risk-bypass defect on the CE branch is fixed** (Codex CRITICAL #1). |

### Per-bot detail (items 1–12 requested)

| Item | Bot 1 | Bot 2 | Bot 3 | Bot 4 | Bot 5 | Bot 6 |
|---|---|---|---|---|---|---|
| Canonical class | NiftyWeeklyIronCondor | CurvatureCreditSpread | ConfluenceGammaScalper | GoldenTrendOptionBuyer | ActiveMomentumOptionScalper | MicroMomentumBuyer |
| Live adapter | bound / gated | bound / gated | LiveStrategyAdapter | LiveStrategyAdapter | LiveStrategyAdapter | LiveStrategyAdapter |
| Required features | vix, rsi_14 | vix, rsi_14 | OHLCV | OHLCV | OHLCV | OHLCV, vix |
| Feature source | Dhan/yfinance + local daily history | same | same | same | same | same |
| Entry conditions | research regime flag (not executable alone) | research `vix<max_vix` (not executable alone) | strategy `signal` | strategy `signal` (CE only) | strategy `signal` | strategy `signal` |
| Exit conditions | runtime fixed %; research undefined live | runtime fixed %; research overnight | runtime fixed % | runtime fixed % | runtime fixed % | runtime fixed % |
| Strike construction | **unspecified by research for live** | **unspecified by research for live** | ATM | ATM | ATM | ATM |
| Position structure | 2-leg short strangle (legged) | 2-leg vertical (legged) | single leg | single leg | single leg | single leg |
| Risk checks | central gate, per leg | central gate, per leg | central gate | central gate | central gate | central gate |
| Holding semantics | intraday (research: weekly) | intraday (research: overnight) | intraday | intraday | intraday | intraday |
| EOD behaviour | 15:35 square-off, fail-closed on no quote | same | same | same | same | same |
| Backtest vs live | **materially different** | **materially different** | forming-bar only | forming-bar + CE-only | forming-bar only | forming-bar only |

---

## 2. Indicator matrix

`SOURCE → TRANSFORMATION → TIMESTAMP → FEATURE → STRATEGY`

| Bot | Indicator | Live source | Causal | Fresh | Status |
|---|---|---|---|---|---|
| 1, 2 | `rsi_14` | Real closes (history + forming bar) → `_attach_rsi_column` (rolling 14) | Yes — leading NaNs dropped, never back-filled | Yes — forming bar TTL 20s | **LIVE COMPUTED** (was fabricated as 50.0) |
| 1, 2, 6 | INDIA VIX | Dhan `IDX_I:21` / yfinance → `_attach_vix_column`, ffill only | Yes — no back-fill | Yes | **LIVE COMPUTED** (was 16.0/15.0 default) |
| 3 | EMA 9/20/50 | OHLCV frame → strategy `compute_indicators` | Yes | Forming bar | **LIVE COMPUTED AND USED** |
| 3 | Bollinger Bands + squeeze | OHLCV frame → strategy | Yes | Forming bar | **LIVE COMPUTED AND USED** |
| 3 | VWAP (20-bar proxy) | OHLCV frame → strategy | Yes | Forming bar | **LIVE COMPUTED AND USED** — the research itself uses a rolling proxy, not true session VWAP |
| 3, 4 | Volume + `vol_ma20` | Index volume from intraday feed | Yes | Forming bar | **LIVE COMPUTED** — note: index volume is frequently 0 in the feed, which suppresses volume-confirmed signals (fails closed, does not fabricate) |
| 3, 6 | RSI 14 (internal) | OHLCV frame → strategy | Yes | Forming bar | **LIVE COMPUTED AND USED** |
| 3, 4, 6 | ATR 14 | OHLCV frame → strategy | Yes | Forming bar | **LIVE COMPUTED AND USED** |
| 4 | EMA 20/50 + VWAP pullback | OHLCV frame → strategy | Yes | Forming bar | **LIVE COMPUTED AND USED** |
| 5 | 9/20 EMA, RSI, momentum | OHLCV frame → strategy | Yes | Forming bar | **LIVE COMPUTED AND USED** |
| 6 | Triple EMA 9/21/50 | OHLCV frame → strategy | Yes | Forming bar | **LIVE COMPUTED AND USED** |
| all | SMA 50 | via EMA/SMA in `compute_indicators` | Yes | Forming bar | **LIVE COMPUTED** where the strategy uses it |
| 1, 2 | IV / skew / term structure / curvature | — | — | — | **NOT AVAILABLE LIVE** — no option-chain IV surface is consumed. Bots 1/2 are gated off, so no proxy is substituted |
| 1, 2 | Option Greeks (delta) | `resolve_option_contract` (Black-Scholes) | n/a | n/a | **COMPUTED BUT NOT USED** — stored under `analytical_*`, never read by a decision |
| all | ML confidence | — | — | — | **DEFINED BUT NOT CALLED** — `src/ml/` is not imported by the live path |
| all | News / event features | — | — | — | **DEFINED BUT NOT CALLED** — `src/events/` reaches only `adaptive_fusion.py`, not a live bot. `surprise` / `novelty` have no implementation at all |

No indicator is substituted by a default constant anywhere in the live path. Where
a required feature cannot be produced, `build_strategy_frame` returns `None` and
the adapter emits `DATA_UNAVAILABLE`.

---

## 3. STRATEGY CONFLICT — escalated, not silently resolved

Per the standing rule *"if fixing a problem requires changing the researched
strategy rather than making runtime faithful to it, STOP and report"*:

**Bot 1 (Iron Condor).** The research cannot be executed faithfully because it
does not define an executable condor. `wing_sd = 2.4` is declared but never
simulated; the validated backtest prices **no options at all** — it assumes a
flat ₹2,500 credit per lot and a flat ₹55,000 margin. Building live wings, or
pricing the structure from the real chain, would create behaviour that has never
been validated. **Decision: live entries fail closed.** Resolving this requires a
strategy-owner decision, not an engineering fix.

**Bot 2 (Curvature Credit Spread).** The documented RSI-branched structure
selection and overnight holding exist only in prose and in a backtest-only
simulator. The runtime's same-day vertical with forced EOD closure is a different
strategy. Implementing the documented behaviour live would mean writing an
unvalidated strategy; implementing the runtime's behaviour in research would mean
altering the research. **Decision: live entries fail closed.**

Neither research file was modified. Verified by
`test_research_strategies_were_not_modified`.
