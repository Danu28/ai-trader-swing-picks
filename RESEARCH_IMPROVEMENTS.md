# Research: Swing Picks Quant Improvements

**Branch:** `research/improvements`
**Date:** 2026-07-20
**Author:** Quant Researcher
**Status:** Research only — no code changes implemented

---

## Current Baseline (15 dates across all regimes)

| Metric | Overall | risk_on | neutral | risk_off |
|--------|---------|---------|---------|----------|
| Win Rate | 60.9% | 53.3% | 58.8% | 65.6% |
| Avg Return | +0.93% | — | — | — |
| Total Return | +59.78% | +4.71% | +12.39% | +42.68% |
| Avg Hold Days | 8.9 | — | — | — |

**Known weakness:** risk_on WR is barely above breakeven (53.3%). Combined with 1:1 R:R, this gives near-zero expectancy in bull regimes.

---

## Idea 1 (Highest Impact): Fix momentum_price Double-Negative Bug

- **File:** `scripts/factors.py`, line 90
- **Type:** Bug fix

### Hypothesis
The `momentum_price` factor (`ROC21 × ROC63`) produces a **positive raw score when both ROC21 and ROC63 are negative**. This systematically ranks declining stocks as having high momentum, inverting the factor's intent during drawdowns.

### Evidence
On 2026-03-16 (geopolitical crash, baseline date):
- TCS.NS: ROC21=-10.5%, ROC63=-24.1% → product = **+252.9** (ranked near top decile)
- HDFCBANK.NS: ROC21=-7.0%, ROC63=-15.6% → product = **+109.3** (ranked high)
- These stocks are in a clear downtrend but get HIGH momentum_price scores

The intended behavior: stocks with strong **upward** momentum in both timeframes should score highest.

### Implementation
Replace line 90 in `factors.py`:

**Current:**
```python
momentum_price_raw = roc_21.iloc[-1] * roc_63.iloc[-1]
```

**Proposed:**
```python
momentum_price_raw = (roc_21.iloc[-1] + roc_63.iloc[-1]) / 2.0
```

**Rationale:** Simple average naturally handles sign. A stock up in both periods has positive momentum. A stock down in both has negative momentum. A stock with mixed direction scores near zero. The percentile rank then correctly ranks upward-trending stocks higher.

**Alternative considered:** `max(0, roc21) * max(0, roc63)` — closer to original amplifiction intent but creates a discontinuity at zero.

### Expected Impact
- **All regimes benefit** — no regime gets worse
- Most impactful in **risk_off** where many stocks have negative ROCs and the bug is most active
- Estimated improvement in risk_off WR: +2-5% (reducing inversion in the momentum category)
- Estimated improvement in risk_on WR: +1-3% (cleaner signal for trending stocks)

### Risk
- Very low risk — this is a bug fix. The product was never intended to reward declining stocks.
- If ranks shift significantly, sector cap behavior could change (different stocks pass the filter). Must verify that the number of picks above score-70 doesn't drop.

### Test
```bash
python scripts/baseline.py --experiment-name fix_momentum_price_bug
```
Compare: Overall WR, Total Return, regime WRs against baseline.

---

## Idea 2 (High Impact): Dynamic Risk:Reward by Regime

- **File:** `scripts/screener.py`, lines 197-199
- **Type:** Strategy parameter change

### Hypothesis
With a fixed 1.5× ATR target and 1.5× ATR stop (R:R = 1:1), the system requires >50% WR to be profitable. Each regime has a different natural WR, so the R:R should be regime-adaptive to maximize expectancy.

### Current WR by regime & implied expectancy (1:1 R:R):
| Regime | WR | Expectancy | Observation |
|--------|----|-----------|-------------|
| risk_on | 53.3% | +0.066 | Barely above breakeven — low confidence |
| neutral | 58.8% | +0.176 | Decent |
| risk_off | 65.6% | +0.312 | Strong — leaving money on table with 1:1 |

### Implementation
In `screener.py`, modify target/stop computation in the `compute_atr` section:

**Current (all regimes):**
```python
target_price = entry_price + (1.5 * atr_val)
stoploss = entry_price - (1.5 * atr_val)
```

**Proposed (regime-adaptive):**
```python
# In screener.py run(), accept regime parameter from caller
# target_mult and stop_mult set based on regime

risk_reward_map = {
    "risk_on":  (2.0, 1.0),   # R:R = 2:1, breakeven at 33.3% WR
    "neutral":  (1.5, 1.5),   # R:R = 1:1, breakeven at 50% WR (keep current)
    "risk_off": (2.0, 1.5),   # R:R = 1.33:1, breakeven at 42.9% WR
}
t_mult, s_mult = risk_reward_map.get(regime, (1.5, 1.5))
target_price = entry_price + (t_mult * atr_val)
stoploss = entry_price - (s_mult * atr_val)
```

**Note:** `backtest.py` and `baseline.py` both call `run_screener()` — the regime parameter needs to flow through. Currently `screener.py` doesn't accept regime; it uses `DEFAULT_WEIGHTS` and `auto_weights()`. We'd add `regime=None` parameter.

### Expected Impact
- **risk_on:** If WR drops to ~45% but R:R = 2:1, expectancy = 0.45×2 + 0.55×(-1) = **+0.35** (vs current +0.066). **5× improvement.**
- **risk_off:** If WR stays at ~65% with R:R = 1.33:1, expectancy = 0.656×1.33 + 0.344×(-1) = **+0.53** (vs current +0.312). **70% improvement.**
- **neutral:** Unchanged.

### Risk
- **risk_on:** Wider targets may not get hit as often. If WR drops below 33%, expectancy goes negative. Need to verify empirically.
- **risk_off:** The 1.33:1 R:R improvement depends on WR not dropping materially with the wider target. If the wider target rarely hits, the gain is lost.
- **Filled rate:** Wider targets = fewer filled trades = more DRAWs.

### Test
```bash
python scripts/baseline.py --experiment-name dynamic_rr
```
Key metrics to compare: Total Return, Avg Return, WR, % DRAWS (if dramatically more draws, the wider targets are unrealistic).

---

## Idea 3 (Medium-High Impact): Regime-Adaptive Factor Weight Tilts

- **File:** `scripts/screener.py`, `auto_weights()` function (lines 20-27)
- **Type:** Factor weighting improvement

### Hypothesis
The current `mean_reversion` weight is fixed at 0.25 across all regimes. In strong bull markets (risk_on), mean reversion works against momentum — the best performers are stocks making new highs, not pulling back. The weight tilt between momentum and mean reversion should be more extreme.

### Current weights:

| Category | risk_on | neutral | risk_off |
|----------|---------|---------|----------|
| Momentum | 0.35 | 0.30 | 0.20 |
| Trend Quality | 0.25 | 0.25 | 0.20 |
| Mean Reversion | **0.25** | **0.25** | **0.25** |
| Quality | 0.15 | 0.20 | 0.35 |

**Problem:** Mean reversion is neutrally weighted (0.25) in all regimes. In risk_on this drags on momentum-driven returns. In risk_off this is too conservative when mean reversion is strongest.

### Proposed weights:

| Category | risk_on | neutral | risk_off |
|----------|---------|---------|----------|
| Momentum | **0.45** | 0.30 | 0.15 |
| Trend Quality | 0.25 | 0.25 | 0.20 |
| Mean Reversion | **0.15** | 0.25 | **0.35** |
| Quality | 0.15 | 0.20 | 0.30 |

**Rationale:**
- **risk_on:** In strong bull markets, momentum dominates. Reduce mean reversion (which selects laggards) to 0.15. Increase momentum to 0.45.
- **neutral:** Keep current (works well at 58.8% WR).
- **risk_off:** In bear markets, mean reversion bounces are the primary edge. Momentum is dangerous (selects stocks that fell least, which may catch up on the downside). Increase mean reversion to 0.35. Reduce momentum to 0.15.

### Expected Impact
- **risk_on:** Expected WR improvement from ~53% → ~57-60%. The current mean reversion selection in bull markets picks stocks that are 1-5% off their highs (best case) or in downtrends (worst case). Reducing this drag should boost performance.
- **risk_off:** Neutral to positive. Current risk_off already strong (65.6% WR). The higher mean reversion tilt may increase WR to ~67-70%.

### Risk
- **risk_on risk:** If the market shifts character (e.g., choppy bull with frequent pullbacks), the lower mean reversion could miss good entries. This is partially mitigated because risk_on requires return > 2% AND breadth > 0.5 — it is genuinely a strong trend regime.
- **risk_off risk:** If mean reversion picks fail (e.g., no bounce, continued decline), losses could be larger. The stop-loss at 1.5× ATR provides a floor.

### Test
```bash
python scripts/baseline.py --experiment-name aggressive_tilts
```
Compare regime WR and total return vs baseline. Most attention on risk_on improvement.

---

## Idea 4 (Medium Impact): Continuous RSI Scoring (Replace 3-Bucket System)

- **File:** `scripts/factors.py`, lines 119-125
- **Type:** Factor precision improvement

### Hypothesis
The current RSI scoring uses 3 discrete buckets (100/60/20) which discards granular information. A continuous scoring function preserves signal gradation between stocks with RSI 41 vs RSI 59 (both get 100 currently).

### Current:
```python
if 40 <= rsi_value <= 60:
    rsi_raw = 100
elif 30 <= rsi_value < 40 or 60 < rsi_value <= 70:
    rsi_raw = 60
else:
    rsi_raw = 20
```

### Proposed — continuous inverted-V centered at RSI=50:
```python
rsi_raw = 100 - 2 * abs(rsi_value - 50)
```

**Scoring comparison:**

| RSI | Current | Proposed |
|-----|---------|----------|
| 40 | 100 | 80 |
| 45 | 100 | 90 |
| 50 | 100 | 100 |
| 55 | 100 | 90 |
| 60 | 100 | 80 |
| 65 | 60 | 70 |
| 70 | 60 | 60 |
| 75 | 20 | 50 |

**Optional enhancement — regime-adaptive center:**
```python
center = 60 if regime == "risk_on" else (40 if regime == "risk_off" else 50)
rsi_raw = max(0, 100 - 2 * abs(rsi_value - center))
```

This shifts the optimal RSI zone: trending markets favor slightly overbought (60), bear markets favor slightly oversold (40). Keeps the scoring regime-aware without adding a separate factor.

### Expected Impact
- **risk_on:** With center at 60, stocks in the RSI 50-70 range (typical for trending stocks) get higher scores than the current flat 100/60 split. This aligns mean reversion selection with trending conditions.
- **risk_off:** With center at 40, stocks in RSI 30-50 range (oversold bounces) score higher, aligning with the mean reversion thesis.
- **neutral:** Center at 50 preserves current behavior but with gradation.

### Risk
- Low risk — this is a refinement. The total score range doesn't change and the RSI factor remains within mean_reversion category.
- If the regime-adaptive center is used, it adds one more dependency on regime detection quality.

### Test
```python
# Test continuous first (simpler):
python scripts/baseline.py --experiment-name rsi_continuous
# Then test regime-adaptive if continuous passes:
python scripts/baseline.py --experiment-name rsi_regime_adaptive
```

Compare: Overall WR and total return. Sub-analysis: does the RSI-50-60 zone (currently scored 100) contribute meaningfully to WIN trades, or is it noise?

---

## Idea 5 (Medium Impact): Intra-Week Seasonal Bias / Day-of-Week Entry Filter

- **File:** `scripts/screener.py` (entry logic)
- **Type:** New entry timing rule

### Hypothesis
Indian equities exhibit well-documented day-of-week effects. Monday/Thursday weakness and Tuesday/Friday strength patterns exist in Nifty 50. If picks are generated on a low-expectancy day, deferring entry by 1 day could improve win rate.

Note: This is the **weakest** of the 5 ideas and should only be pursued if Ideas 1-4 pass testing.

### Implementation
In `screener.py`, add a pre-filter check on `as_of_date`:

```python
from datetime import datetime
dow = datetime.strptime(as_of_date, "%Y-%m-%d").weekday()
# Monday=0, Tuesday=1, ..., Friday=4
LOW_EXPECTANCY_DAYS = [0, 3]  # Monday, Thursday
if dow in LOW_EXPECTANCY_DAYS and regime == "neutral":
    # Skip — wait for better entry day
    return {"warning": f"Skipping {as_of_date} ({['Mon','Tue','Wed','Thu','Fri'][dow]}) — low expectancy day"}
```

### Expected Impact
- Marginal, ~1-3% WR improvement on affected dates
- Mostly affects neutral regime where edge is already modest

### Risk
- Data mining risk — day-of-week effects shift over time
- Reduces number of trading opportunities (lost trades on skipped days could have been winners)
- Indian market open interest / FII/DII flows might dominate any calendar effect

### Test
```bash
# Analyze historical trade outcomes by day of week first
# Then run baseline with filter active
python scripts/baseline.py --experiment-name dow_filter
```
Primary metric: WR change. Secondary: total opportunity cost (skipped profitable trades).

---

## Summary Recommendation

### Priority order for implementation:

| Rank | Idea | Type | Est. Impact | Risk | Files Touched |
|------|------|------|-------------|------|---------------|
| 1 | Fix momentum_price double-negative bug | Bug fix | High | Very Low | `factors.py` (1 line) |
| 2 | Dynamic R:R by regime | Strategy param | High | Medium | `screener.py`, `backtest.py`, `baseline.py` |
| 3 | Regime-adaptive factor weight tilts | Weight opt | Medium-High | Low | `screener.py` only |
| 4 | Continuous RSI scoring | Factor refinement | Medium | Very Low | `factors.py` (~5 lines) |
| 5 | Day-of-week entry filter | Timing | Low-Medium | Medium | `screener.py` |

### Recommended first iteration: **Ideas 1 + 4 together**

These are the lowest-risk, highest-confidence changes:
- **Idea 1** is a confirmed bug fix with no downside
- **Idea 4** is a pure precision improvement with smooth degradation

Both modify only `factors.py` and can be validated together in a single baseline run:

```bash
git checkout -b implement/factor-fixes
# Edit factors.py: fix momentum_price bug + continuous RSI
python scripts/baseline.py --experiment-name factor_fixes_v1
```

If the factor fixes pass (total return improves or stays flat, no regime regresses), immediately proceed to:

### Recommended second iteration: **Idea 2 (Dynamic R:R)**

This has the highest potential to transform the risk_on performance from marginal to solid. It requires changes to the screener (to accept regime and compute regime-specific multiples) and the backtest/baseline callers.

### If Ideas 1+2+4 all pass: **Idea 3 (Aggressive Tilts)**

This is the most aggressive change and should only be applied after the factor and R:R foundations are de-risked.

---

## Appendix: Current Factor Bug Confirmation

Query on `2026-03-16` (geopolitical crash, note: baseline labels this risk_off):

| Symbol | ROC21 | ROC63 | Product | momentum_price percentile |
|--------|-------|-------|---------|--------------------------|
| KPITTECH.NS | — | — | — | 100.0 (top) |
| COFORGE.NS | — | — | — | 99.49 |
| TRENT.NS | — | — | — | 98.46 |
| TCS.NS | -10.5% | -24.1% | +252.9 | ~70 (mid-high) |
| RELIANCE.NS | -1.7% | -10.4% | +17.9 | ~50 (mid) |
| TATASTEEL.NS | — | — | — | 2.56 (bottom) |

All top-ranked stocks on this crash date have **negative** 21-day and 63-day returns. The momentum_price factor is selecting the most consistently-declining stocks, not the strongest upward movers. This is inverted from the factor's intent.
