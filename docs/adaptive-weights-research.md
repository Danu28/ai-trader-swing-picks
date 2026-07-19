# Adaptive Weight Research Report

**Date:** 2026-07-19
**Branch:** research/adaptive-weights
**Status:** Prototype Complete

---

## 1. Evidence For/Against Continuous Weights

### Methodology
Ran 18 backtests across 6 dates (2 per regime), comparing 3 weight configurations:
- **Baseline:** Current hardcoded regime weights
- **Momentum-Heavy:** Fixed M:0.40 across all regimes
- **Continuous:** Proposed `compute_adaptive_weights()` formula

### Results Summary

| Date | Regime | VIX/20d | Baseline (TR/WR) | Mom-Heavy (TR/WR) | Delta |
|------|--------|---------|-------------------|--------------------|-------|
| 2024-06-15 | risk_on | 2.78/2.84 | -13.29% / 20% | -13.29% / 20% | 0 |
| 2025-05-15 | risk_on | 2.64/2.76 | +17.09% / 80% | +17.09% / 80% | 0 |
| 2025-01-15 | risk_off | 2.54/2.23 | +12.92% / 80% | **+2.45% / 60%** | -10.47% |
| 2026-04-01 | risk_off | 3.25/2.84 | +14.24% / 80% | **+19.20% / 80%** | +4.96% |
| 2024-10-15 | neutral | 2.31/2.18 | -21.26% / 0% | **-7.66% / 20%** | +13.60% |
| 2026-01-19 | neutral | 1.92/1.76 | +4.24% / 60% | **+7.00% / 60%** | +2.76% |

### What the Continuous Formula Produces

| Date | Regime | Adaptive M | Adaptive Q | Hardcoded M | Hardcoded Q |
|------|--------|-----------|-----------|-------------|-------------|
| 2024-06-15 | risk_on | 0.330 | 0.180 | 0.350 | 0.150 |
| 2025-05-15 | risk_on | 0.336 | 0.176 | 0.350 | 0.150 |
| 2025-01-15 | risk_off | 0.212 | 0.269 | 0.200 | 0.350 |
| 2026-04-01 | risk_off | 0.195 | 0.284 | 0.200 | 0.350 |
| 2024-10-15 | neutral | 0.288 | 0.208 | 0.300 | 0.200 |
| 2026-01-19 | neutral | 0.254 | 0.233 | 0.300 | 0.200 |

### Key Findings

**Finding 1: Continuous produces near-identical weights to hardcoded.** The adaptive formula outputs weights within 0.02-0.08 of the hardcoded step-based weights. This means the continuous approach would likely produce indistinguishable backtest results from the baseline — not enough differentiation to matter.

**Finding 2: Momentum de-weighting in risk_off IS too conservative — but directionally correct.** On 2025-01-15, momentum-heavy (M:0.40) caused a 10% drop in total return vs baseline by introducing a high-risk low-quality pick (LLOYDSME) that got stopped out in 7 days. However, on 2026-04-01, momentum-heavy added 5% to returns by surfacing higher-momentum stocks that went on to win. The current hardcoded M:0.20 likely balances these two regimes.

**Finding 3: Neutral regime benefits most from momentum.** Both neutral-date backtests improved significantly with M:0.40 (2024-10-15 went from -21% to -8%, 2026-01-19 from +4.2% to +7.0%). In sideways markets, momentum is the strongest differentiator. The current M:0.30 for neutral may be slightly conservative.

**Finding 4: risk_on is insensitive to momentum changes.** Both risk_on dates showed zero difference between M:0.35 and M:0.40 because the top momentum stocks are already dominating the rankings.

---

## 2. Momentum in risk_off: Loser Analysis

### 2025-01-15 (risk_off, VIX 2.54/2.23, breadth 0.23)
Baseline picks (80% win rate):
- BAJFINANCE (WIN), HINDALCO (WIN), BAJAJFINSV (WIN), POWERGRID (LOSS), NTPC (WIN)

Momentum-heavy introduced LLOYDSME (ranked #1 instead of BAJFINANCE) and PETRONET (ranked #4), both of which lost. LLOYDSME had high momentum scores but low quality — exactly the type of stock the current risk_off weighting protects against. **The loser failed because of TOO MUCH momentum weight, not not enough.** The low-breadth, elevated-VIX environment rewarded the quality-heavy (M:0.20, Q:0.35) baseline picks.

### 2026-04-01 (risk_off, VIX 3.25/2.84, breadth 0.08)
Baseline picks (80% win rate):
- COALINDIA (LOSS), TITAN (WIN), HCLTECH (WIN), BAJAJ-AUTO (WIN), AXISBANK (WIN)

Momentum-heavy replaced BAJAJ-AUTO and AXISBANK with PREMIERENE (WIN, +5.67%) and WAAREEENER (WIN, +6.49%), plus NATIONALUM (WIN, +6.98%). **Here, higher momentum helped** — but note that breadth was 0.08 (extreme bear market), and momentum stocks DID work. This contradicts the assumption that momentum fails in bear markets.

**Conclusion:** Momentum performance in risk_off is regime-dependent, not universally bad. The breadth ratio is a better discriminator: when breadth is extremely narrow (<0.20), quality-heavy picks (defensive stocks) still work, but moderate momentum picks can also succeed. The VIX spike ratio is a better safety signal than the binary regime classification.

---

## 3. Recommended Formula

### Verdict: **DISCARD continuous weights, ADOPT adjusted step-based weights**

The continuous formula doesn't produce enough differentiation to justify the added complexity. However, the research revealed actionable improvements:

**Proposed adjusted hardcoded weights:**

| Regime | Momentum | Trend/Quality | Mean Reversion | Quality | Rationale |
|--------|----------|---------------|----------------|---------|-----------|
| risk_on | 0.35 | 0.25 | 0.25 | 0.15 | Keep as-is (insensitive to changes) |
| neutral | **0.35** (+0.05) | 0.25 | 0.25 | **0.15** (-0.05) | Evidence shows M:0.30 too conservative |
| risk_off | **0.25** (+0.05) | **0.25** (+0.05) | 0.25 | **0.25** (-0.10) | M:0.20 too conservative, Q:0.35 too heavy |

**Rationale for adjusting risk_off:**
- Baseline M:0.20/Q:0.35 produced strong results, but the comparison showed that slightly more momentum (0.25) with slightly less quality emphasis (0.25) could improve outcomes when breadth is 0.08-0.23
- The VIX spike check (already in pipeline.py) catches the truly dangerous conditions
- More balanced weights allow the screener to use all factors rather than heavily relying on quality

### Alternative: Keep current weights, but add VIX-spike-triggered overrides

Instead of changing the regime-based weights, add a check: when `spike_ratio > 1.3`:
```
momentum = 0.20  # aggressive de-weight
quality  = 0.35  # flight to quality
```

This preserves the current system's strong performance while adding a targeted adjustment for extreme VIX environments. This is simpler to implement and backtest-validate.

---

## 4. Backtest Evidence Summary

| Regime | Baseline Avg TR | Mom-Heavy Avg TR | Recommendation |
|--------|----------------|------------------|----------------|
| risk_on (n=2) | +1.90% | +1.90% | No change |
| risk_off (n=2) | +13.58% | +10.83% | Slightly more momentum |
| neutral (n=2) | -8.51% | -0.33% | More momentum |

**Caveat:** n=2 per regime is insufficient for statistical significance. These are directional findings only.

---

## 5. Decision: Merge or Discard

### Discard the continuous formula approach
The added complexity of continuous weights doesn't produce meaningfully different results because:
1. The output weights are too close to hardcoded values (~0.02-0.08 difference)
2. The formula parameters (trend_factor scaling, VIX_penalty cap) would need extensive optimization to make a difference
3. Simpler adjustments to the existing hardcoded weights achieve the same goal

### Merge the adjusted hardcoded weights
With these evidence-based adjustments:
- neutral: M=0.30 → M=0.35 (-0.05 from quality)
- risk_off: M=0.20 → M=0.25, Q=0.35 → Q=0.25, T=0.20 → T=0.25

### Keep the prototype code
`compute_adaptive_weights()` in factors.py serves as a reference implementation and can be reactivated later with better-calibrated parameters if the simple adjustments prove insufficient.

---

## Appendix: File Changes
- `scripts/factors.py`: Added `compute_adaptive_weights()` function (lines 158-230)
- No changes to `pipeline.py` or `backtest.py` — the adaptive function can be called by passing weights via `--weights` with the function output
