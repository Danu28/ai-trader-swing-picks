# Research: Cross-Sectional Return Dispersion & Factor Model Confidence

**Branch:** `research/dispersion`
**Date:** 2026-07-20
**Author:** Quant Researcher
**Status:** Research only — no code changes implemented
**Universe:** Nifty 50 (48) + Nifty Midcap 150 (148) = 196 stocks
**Data Range:** 2021-07-20 to 2026-07-17 (1,237 trading days, ~5 years)

---

## Table of Contents

1. [First Principles — Theoretical Motivation](#1-first-principles--theoretical-motivation)
2. [What Is Return Dispersion?](#2-what-is-return-dispersion)
3. [Hypothesis Ranking & Prior Probabilities](#3-hypothesis-ranking--prior-probabilities)
4. [Hypothesis 1: Dispersion Predicts Model Confidence (Prior: 35%)](#4-hypothesis-1-dispersion-predicts-model-confidence)
5. [Hypothesis 2: Dispersion Affects Rank Stability (Prior: 30%)](#5-hypothesis-2-dispersion-affects-rank-stability)
6. [Hypothesis 3: Holding Period Decay (Prior: 25%)](#6-hypothesis-3-holding-period-decay)
7. [Hypothesis 4: Sector Dispersion vs Market Dispersion (Prior: 20%)](#7-hypothesis-4-sector-dispersion-vs-market-dispersion)
8. [Hypothesis 5: Dispersion as Regime Signal for Position Sizing (Prior: 15%)](#8-hypothesis-5-dispersion-as-regime-signal-for-position-sizing)
9. [Data Requirements](#9-data-requirements)
10. [Recommended Implementation Plan](#10-recommended-implementation-plan)
11. [Appendix A: Mathematical Definitions](#appendix-a-mathematical-definitions)
12. [Appendix B: SQL Queries for Data Extraction](#appendix-b-sql-queries-for-data-extraction)
13. [Appendix C: Bias Checklist](#appendix-c-bias-checklist)

---

## 1. First Principles — Theoretical Motivation

### 1.1 The Core Question

A multi-factor ranking model sorts 196 stocks by a composite score and picks the top 5. The model's edge depends on the assumption that **cross-sectional differences in stock characteristics (momentum, trend, mean reversion, quality) map to cross-sectional differences in forward returns**.

But this mapping is not constant. Sometimes stocks separate clearly — winners look different from losers, and the ranking is informative. Sometimes everything moves together — macro drives all stocks in the same direction, and the ranking is noise.

**What determines when the ranking is informative vs. noise?**

### 1.2 The Fundamental Decomposition

Decompose any stock's return into two components:

```
r_i = β_i · r_m + α_i + ε_i
```

where:
- `β_i · r_m` = exposure to common (market) factor
- `α_i` = stock-specific expected return (the alpha we're trying to capture)
- `ε_i` = idiosyncratic noise

Cross-sectional variance of forward returns across N stocks:

```
Var(r_i) = Var(β_i · r_m) + Var(α_i) + Var(ε_i) + 2·Cov(β_i·r_m, α_i)
```

**Key insight:** When `Var(β_i · r_m)` dominates (high macro correlation), stock-specific differences are swamped by the common factor. The ranking on alpha signals is akin to sorting lottery tickets in a rising tide — the tide matters more than the ticket number.

When `Var(α_i)` dominates (high dispersion), stock-specific factors are separable. The ranking system's signal-to-noise ratio is high.

### 1.3 Market Inefficiency Being Exploited

If return dispersion is **persistently predictable** (i.e., tomorrow's dispersion can be estimated from today's data), and if the factor model's edge regime-switches with dispersion, then:

1. **High dispersion** → Factor ranking is trustworthy → Deploy full capital, tight risk controls per position
2. **Low dispersion** → Factor ranking is noise → Reduce capital deployment, broaden position sizing, or skip

This is an efficiency arbitrage on the **factor model's own time-varying signal quality** — an orthogonal risk factor (dispersion) that gates the signal-to-noise ratio of all other factors.

### 1.4 Why This Edge Should Persist

1. **Behavioral anchoring**: In low-dispersion regimes, investors herd on macro narratives, ignoring stock-specific fundamentals. Cross-sectional differentiation temporarily collapses.
2. **Liquidity cascades**: In high-volatility periods (which may precede high dispersion), liquidity dries up uniformly, compressing dispersion initially, then it expands as stocks are re-priced heterogeneously.
3. **Institutional flows**: Rebalancing flows create commonality. ETF inflows/outflows affect all stocks simultaneously, compressing dispersion. Active manager differentiation restores it.
4. **Regime persistence**: Dispersion clusters (like volatility). High-dispersion periods are followed by more high-dispersion periods on short horizons. This regime persistence is exploitable.

### 1.5 Falsification Statement

If the factor model's win rate and rank stability are **not significantly different** between top-quartile and bottom-quartile dispersion regimes (after controlling for market return and volatility), the hypothesis is falsified. The expected null result: pick #1 win rate in high vs. low dispersion differs by <5 percentage points, and the difference is not statistically significant at p<0.05.

---

## 2. What Is Return Dispersion?

### 2.1 Definition

Cross-sectional return dispersion at time `t` is the **standard deviation of forward returns** across all stocks in the universe over a given holding period:

```
Dispersion(t, h) = StdDev({ r_i(t → t+h) : i ∈ universe })
```

where `r_i(t → t+h)` is stock `i`'s total return from time `t` to `t+h`.

### 2.2 Measurement Variants

| Variant | Formula | Interpretation |
|---------|---------|---------------|
| **Raw StdDev** | `σ(r_i)` | Absolute dispersion. Scale-dependent. |
| **Cross-sectional IQR** | `Q3(r_i) - Q1(r_i)` | Robust to outliers. Preferred for Indian midcaps. |
| **Gini coefficient** | `2·Cov(r, rank(r)) / (N·mean(r))` | Inequality measure. Bounded [0, 1] |
| **Top-decile spread** | `mean(top10%) - mean(bottom10%)` | Focuses on tails — relevant for pick #1 vs. #196 |
| **Theil index** | `(1/N)·Σ(r_i/μ)·ln(r_i/μ)` | Decomposable: total = between-sector + within-sector |

### 2.3 Reference: Existing Literature

- **Stivers & Sun (2010)** — Cross-sectional return dispersion predicts future market volatility. High dispersion → lower future returns for high-beta stocks.
- **Maio (2013)** — Return dispersion negatively predicts aggregate stock market returns. High dispersion = low future market returns.
- **Angelidis et al. (2015)** — Dispersion in analyst forecasts predicts factor model performance. High dispersion = high factor returns.
- **Chao & Colacito (2020)** — Return dispersion as a regime-switching variable for volatility forecasting.

### 2.4 Expected Baseline Statistics for Our Universe

Based on Indian equity characteristics (higher volatility than developed markets, midcaps add skew):

| Holding Period | Mean Dispersion (daily ret, %) | Typical Range (p10-p90) | Notes |
|---------------|-------------------------------|------------------------|-------|
| 5-day | ~3-4% | 2% - 7% | Higher for midcaps |
| 10-day | ~4-6% | 3% - 10% | Non-linear scaling with √t |
| 21-day | ~6-9% | 4% - 14% | Fat tails possible in crises |

---

## 3. Hypothesis Ranking & Prior Probabilities

Prior probabilities assigned by first-principles reasoning **before any data is tested**. Ranked by plausibility (prior belief in the mechanism).

| Rank | Hypothesis | Prior | Key Assumption | Falsification Threshold |
|------|-----------|-------|----------------|-------------------------|
| **H1** | Dispersion predicts model confidence (pick #1 win rate) | **35%** | Factor model's signal-to-noise scales with dispersion | WR_high ≤ WR_low + 5pp at p>0.10 |
| **H2** | Dispersion affects rank stability (spread between #1 and #5) | **30%** | Narrow dispersion compresses outcomes across ranks | delta_high ≤ delta_low + 5% at p>0.10 |
| **H3** | Dispersion's predictive power decays at longer holding periods | **25%** | Dispersion mean-reverts; alpha captured quickly | IC_5d ≤ IC_21d (opposite direction) |
| **H4** | Intra-sector dispersion matters more than market-wide dispersion | **20%** | Factor model's within-sector ranking is the actual edge | Sector-dispersion model fails cross-validation |
| **H5** | Dispersion regime signals position sizing adjustments | **15%** | Low dispersion precedes regime change with lead time | Lead correlation not significant at p<0.05 |

### Prior Assignment Rationale

**H1 (35%):** Highest prior. The mechanism is clean and directly testable. If the factor model works at all, its signal should be clearer when stocks are differentiating. The 50% baseline WR means there is established edge to modulate.

**H2 (30%):** Almost as clean as H1, but the stake is lower (rank stability matters less than WR). The rank-tightness in low dispersion is intuitive: if all stocks look similar on factors and outcomes, the top quintile vs. second quintile distinction is noise.

**H3 (25%):** First-principles suggests 5-day should dominate 21-day because dispersion is partially a volatility phenomenon (volatility clusters at short horizons). But 21-day could also matter for swing trades. Pr(decay) > Pr(increase), but the effect size is uncertain.

**H4 (20%):** More nuanced. The factor model scores sector-relative signals, but the universe is not sector-neutral. Midcaps in one sector vs. large caps in another may dominate. The sector decomposition is data-intensive.

**H5 (15%):** The least direct mechanism. Low dispersion → compressed returns → eventual volatility expansion is a plausible macro regime signal, but the lead time is noisy. Position sizing decisions based on this are one more layer of estimation error.

---

## 4. Hypothesis 1: Dispersion Predicts Model Confidence

### 4.1 Statement

**The win rate of the factor model's top pick (#1 ranked stock by composite score) is positively correlated with cross-sectional return dispersion measured at the signal date.**

- High dispersion (top quartile): Pick #1 win rate > 70%
- Low dispersion (bottom quartile): Pick #1 win rate < 50%
- Monotonic relationship across all quartiles

### 4.2 Economic Mechanism

When stock-level return dispersion is high, the cross-section of expected returns is well-separated. A stock at the 90th percentile of composite score is genuinely different from a stock at the 10th percentile. The ranking system's top pick is identifying a stock with a true positive alpha expectation. When dispersion is low, the signal is compressed — the composite score difference between rank #1 and rank #10 is driven by noise, not genuine alpha differentiation.

### 4.3 Competing Explanations

- **Volatility confound**: High dispersion regimes may coincide with high volatility regimes. Win rate improvement could be a volatility effect (wider stops are easier to hit).
- **Market return confound**: High dispersion may coincide with strong trends (up or down). In strong trends, momentum/trend factors work well, and mean reversion works poorly. The win rate change may be factor-specific, not dispersion-general.
- **Regime confound**: The current regime classifier (risk_on/neutral/risk_off) may already capture dispersion effects implicitly through breadth and VIX.

### 4.4 Primary Falsification Test

**Test:** Compare pick #1 win rate in high-dispersion (Q4) vs. low-dispersion (Q1) environments, using a two-proportion z-test.

**Null hypothesis (H₀):** WR_high ≤ WR_low + 5 percentage points (or not significantly different)

**Reject H₀ if:** WR_high > WR_low + 5pp AND p-value < 0.10 (one-sided)

### 4.5 Data Requirements

- `daily_ohlcv` table: close prices for all 196 stocks
- `factor_scores` table: composite scores from the factor model
- `backtest` or `baseline` logic: forward returns for picks
- Holding periods: 5, 10, 21 trading days

### 4.6 Success Criteria

| Metric | Target | Comment |
|--------|--------|---------|
| Win rate Q4 (high disp) | > 65% | vs. ~61% baseline overall |
| Win rate Q1 (low disp) | < 52% | Significantly below baseline |
| Monotonic progression | Q1 < Q2 < Q3 < Q4 | Not strictly necessary but supportive |
| p-value (Q4 vs Q1) | < 0.10 | One-sided z-test |
| Bootstrap 95% CI width | < 15pp | For each quartile |

### 4.7 Interaction with Existing Factors

- **Expected IC with momentum factor**: Positive in high dispersion, near-zero in low dispersion
- **Expected IC with mean reversion factor**: Positive in high dispersion (stocks diverge enough for pullbacks to matter)
- **Expected IC with quality factor**: Stable across dispersion regimes (liquidity/volatility are stock-specific)

### 4.8 Expected Failure Modes

1. **Insufficient historical data**: Only 1,237 trading days × 15 baseline test dates. Need to expand to full time series (~200 dates).
2. **Filed under "statistically interesting, economically irrelevant"**: If WR difference is < 7pp, the position sizing or skipping benefit is marginal.
3. **Dispersion is just regime relabeled**: If H1 is a restatement of risk_on/risk_off, the incremental value is zero.

---

## 5. Hypothesis 2: Dispersion Affects Rank Stability

### 5.1 Statement

**The forward return spread between rank #1 and rank #5 (the selected portfolio) is wider in high-dispersion regimes and narrower in low-dispersion regimes.**

### 5.2 Economic Mechanism

If the factor model is informative, the ranking gradient (score vs. expected return) should be steep when dispersion is high. The top rank should clearly outperform the 5th rank. When dispersion is low, all selected stocks have similar expected returns — the rank distinction is noise.

Threshold implication: In low dispersion, a 5-stock portfolio could be replaced by a 1-stock portfolio or a 3-stock portfolio with minimal expected return difference. The appropriate number of positions may be regime-dependent.

### 5.3 Primary Falsification Test

**Test:** Compute the forward return of rank #1 minus rank #5 in each dispersion quartile. Use a one-way ANOVA (or Kruskal-Wallis) across quartiles.

**Null hypothesis:** `E[r_1 - r_5 | Q_high] = E[r_1 - r_5 | Q_low]`

### 5.4 Success Criteria

| Metric | Target |
|--------|--------|
| Spread (r1 - r5) in Q4 (high) | > 2× spread in Q1 (low) |
| ANOVA F-test p-value | < 0.05 |
| Consistency across holding periods | At least 2 of 3 holding periods show the pattern |

### 5.5 Practical Implication

If confirmed, this recommends **dynamic position sizing**:
- High dispersion: Concentrate in top 2-3 picks (tighter portfolio)
- Low dispersion: Hold all 5 picks (or reduce to 3, but include more diversity)

---

## 6. Hypothesis 3: Holding Period Decay

### 6.1 Statement

**Dispersion's predictive power for the factor model's win rate is strongest at short holding periods (5-day) and decays at longer periods (21-day), because cross-sectional dispersion is a short-lived phenomenon that is arbitraged away.**

### 6.2 Economic Mechanism

Return dispersion is partially a volatility phenomenon. Volatility clusters at short horizons (days to weeks). As the holding period extends, two forces dilute dispersion's predictive power:

1. **Mean reversion of dispersion itself**: High dispersion regimes last ~5-10 trading days on average. By day 21, the regime may have flipped.
2. **Cumulative common factor**: Over 21 days, the market return component (`β_i · r_m`) accumulates, dominating the stock-specific component (`α_i`). The factor model's edge is in `α_i`, not `β_i · r_m`.

### 6.3 Competing Explanation

If dispersion predicts equally well across all holding periods, it suggests that dispersion is capturing a persistent structural characteristic of the stock universe (e.g., sector composition, size dispersion, or market development phase), not a trading horizon signal.

### 6.4 Primary Falsification Test

**Test:** Compute Information Coefficient (rank correlation between factor score and forward return) for each holding period, conditioned on dispersion quartile.

**Expected pattern:**
```
IC(5d | high disp) >> IC(5d | low disp)   [large gap]
IC(10d | high disp) > IC(10d | low disp)   [medium gap]
IC(21d | high disp) ≈ IC(21d | low disp)   [no gap]
```

**Null hypothesis:** IC gap (high - low) is the same for 5d, 10d, and 21d.

### 6.5 Success Criteria

| Period | Expected IC gap (High - Low) |
|--------|------------------------------|
| 5-day | > 0.04 (significant) |
| 10-day | > 0.02 (moderate) |
| 21-day | < 0.01 (near zero) |

---

## 7. Hypothesis 4: Sector Dispersion vs. Market Dispersion

### 7.1 Statement

**Intra-sector return dispersion (dispersion of returns within each sector) is a stronger predictor of the factor model's relative ranking reliability than total market-wide dispersion.**

### 7.2 Economic Mechanism

The factor model scores stocks on relative strength within the universe. But the current scoring is **not sector-neutral** — a stock's rank depends partly on its sector's aggregate performance. When the sector factor dominates (all banking stocks moving together), the within-sector ranking of banking stocks is more meaningful for stock-picking than the cross-sector ranking.

If dispersion is driven by sector differences (IT at +5%, Metals at -3%), the factor model's ranking will mechanically favor the outperforming sector's stocks, not genuine stock-specific alpha. The model's edge is in stock selection within a sector.

### 7.3 Mathematical Decomposition

Total dispersion can be decomposed:

```
Total Dispersion² = Between-Sector Dispersion² + Average Within-Sector Dispersion²
```

Using the Theil index or simple variance decomposition:

```
Var(r_i) = Var(E[r_i | sector]) + E[Var(r_i | sector)]
              ^                       ^
         Between-sector           Within-sector
              ↑                       ↑
         Sector allocation        Stock selection
         signal                   signal
```

Hypothesis: `E[Var(r_i | sector)]` (within-sector dispersion) predicts the factor model's stock-picking accuracy. `Var(E[r_i | sector])` (sector allocation) predicts only sector-bet accuracy.

### 7.4 Primary Falsification Test

**Test:** Run two models predicting pick #1 win rate:
1. Model A: Predictor = market-wide dispersion only
2. Model B: Predictors = between-sector dispersion + within-sector dispersion

Compare R² and AIC. If Model B is not materially better than Model A, H4 is rejected.

### 7.5 Success Criteria

| Metric | Target |
|--------|--------|
| ΔR² (Model B - Model A) | > 0.05 |
| Within-sector coefficient sign | Positive (more dispersion = better WR) |
| Between-sector coefficient | Not significant or negative |

### 7.6 Data Requirements

- Sector labels for each stock (available from `stocks` table)
- Sufficient stocks per sector for meaningful within-sector dispersion (need ~5+ per sector)
- Sectors with < 3 stocks may need to be pooled

---

## 8. Hypothesis 5: Dispersion as Regime Signal for Position Sizing

### 8.1 Statement

**Periods of abnormally low return dispersion compress) often precede a volatility expansion and trend change. This can be used to adjust position sizing: reduce position size in low dispersion, increase in high dispersion.**

### 8.2 Economic Mechanism

Low dispersion regimes are "calm before the storm." When all stocks move in lockstep, it indicates a dominant macro factor. Macro-factor dominance is fragile — it tends to resolve via a sharp re-pricing (volatility expansion) when the macro narrative changes. This re-pricing typically increases dispersion as stocks respond heterogeneously.

Position sizing implication:
- **Low dispersion** → Reduce position size, widen stops (expect regime change)
- **High dispersion** → Increase position size, tighten stops (model has edge)

### 8.3 Primary Falsification Test

**Test:** Compute the cross-correlation between `Dispersion(t)` and `Volatility(t + h)` for h = 5, 10, 21 days. If dispersion does not Granger-cause volatility changes, H5 is rejected.

**Required:** Dispersion must have predictive power for volatility beyond what the current VIX proxy already captures.

### 8.4 Success Criteria

| Metric | Target |
|--------|--------|
| Cross-correlation (disp, vol+5) | Negative at lag 0, positive at lead >0 |
| Granger causality p-value | < 0.10 |
| Incremental R² over VIX-only model | > 0.03 |

### 8.5 Practical Implication

If confirmed:
- Position sizing multiplier = `f(Dispersion_percentile)`, e.g., 0.5× in bottom decile, 1.5× in top decile
- Strategy can explicitly skip low-dispersion weeks with a "no-trade" filter
- The VIX proxy spike filter already catches extreme volatility; dispersion catches the *compression* that *precedes* the extreme

---

## 9. Data Requirements

### 9.1 Primary Data Sources

| Data | Source | Table | Fields Needed |
|------|--------|-------|---------------|
| Stock prices | Existing DB | `daily_ohlcv` | date, symbol, close |
| Universe membership | Existing DB | `stocks` | symbol, universe_slug, sector |
| Factor scores | Existing DB | `factor_scores` | symbol, date, all 9 factors, composite |
| Market regime | Existing DB | `market_regime` | date, regime, nifty_trend, breadth_ratio, vix_proxy |
| Screener results | Existing DB | `screener_results` | symbol, date, rank, composite, targets |

### 9.2 Derived Data (to be computed)

| Derived Series | Formula | Frequency |
|---------------|---------|-----------|
| Forward returns (5d) | `close[t+5] / close[t] - 1` | Per stock, per date |
| Forward returns (10d) | `close[t+10] / close[t] - 1` | Per stock, per date |
| Forward returns (21d) | `close[t+21] / close[t] - 1` | Per stock, per date |
| Market-wide dispersion (5d) | `StdDev(forward_5d_i)` across all stocks | Per date |
| Market-wide dispersion (10d) | Same for 10d | Per date |
| Market-wide dispersion (21d) | Same for 21d | Per date |
| Sector dispersion (within) | `StdDev(forward_5d_i)` within each sector | Per sector, per date |
| Sector dispersion (between) | `StdDev(mean_forward_5d_by_sector)` | Per date |
| IC (Information Coefficient) | Spearman rank corr(factor_score, forward_return) | Per date, per period |
| Rank spread | `return(rank=1) - return(rank=5)` | Per date |

### 9.3 Minimum History Needed

| Analysis | Min History | Rationale |
|----------|-------------|-----------|
| H1: WR by dispersion quartile | ~200 trading days with picks | Need ~50 trades per quartile for statistical power |
| H2: Rank stability | ~200 trading days | Same as H1 |
| H3: Holding period decay | ~400 trading days | Need to compare IC across 3 horizons × 2 disp states |
| H4: Sector decomposition | ~400 trading days | Limited stocks per sector → more data needed |
| H5: Granger causality | ~500 trading days | Time series requires ~250 obs per variable for Granger |

### 9.4 Power Analysis (for sample size planning)

Assuming baseline WR = 61%:
- To detect WR difference of 15pp (70% vs 55%) with 80% power at α=0.10:
  Need ~85 trades per group → ~170 total → ~17 baseline dates per quartile
- To detect WR difference of 10pp (68% vs 58%): Need ~190 trades per group → ~380 total
- With 15 baseline dates (75 trades): Only able to detect > 22pp difference → **Need to expand to full time series backtest (~200+ dates)**

**Conclusion:** The existing 15-date baseline is insufficient. We need to run a full walk-forward backtest (weekly or monthly) to get enough trades for statistical significance.

---

## 10. Recommended Implementation Plan

### 10.1 Phase 0: Infrastructure (No factor code changes)

**Goal:** Build the data pipeline to compute dispersion metrics — research only, no changes to production scoring.

**Files to create:**
- `scripts/research/dispersion_analysis.py` — Standalone research script (not imported by pipeline)
- `scripts/research/__init__.py` — Package marker

**This script will:**
1. Query `daily_ohlcv` for all 196 stocks across the full date range
2. Compute forward returns for 5d, 10d, 21d at each date
3. Compute cross-sectional dispersion metrics (StdDev, IQR, top-decile spread, Gini)
4. Join with `factor_scores` (if available) or compute composite scores independently
5. Export to CSV for analysis in a notebook

### 10.2 Phase 1: Data Extraction & Dispersion Computation

**Steps:**

1. **SQL: Build flat file of daily forward returns**
   ```sql
   SELECT a.date, a.symbol, a.close,
          b.close / a.close - 1 AS fwd_ret_5d,
          c.close / a.close - 1 AS fwd_ret_10d,
          d.close / a.close - 1 AS fwd_ret_21d
   FROM daily_ohlcv a
   JOIN daily_ohlcv b ON a.symbol = b.symbol AND b.date = (SELECT MIN(date) FROM daily_ohlcv WHERE symbol = a.symbol AND date > a.date LIMIT 1 OFFSET 4)
   -- (adjust for actual trading day offsets)
   ```

2. **Compute daily dispersion metrics:**
   ```python
   # For each date with >= 100 stocks available:
   daily_dispersion = {
       'date': date,
       'n_stocks': count,
       'disp_5d_std': np.std(fwd_5d_returns),
       'disp_10d_std': np.std(fwd_10d_returns),
       'disp_21d_std': np.std(fwd_21d_returns),
       'disp_5d_iqr': np.percentile(fwd_5d_returns, 75) - np.percentile(fwd_5d_returns, 25),
       'disp_5d_topbot': np.mean(top10) - np.mean(bottom10),
       'gini_5d': gini_coefficient(fwd_5d_returns),
   }
   ```

3. **Join with regime data:**
   ```python
   merged = daily_dispersion.merge(market_regime, on='date')
   ```

4. **Export to CSV:**
   ```
   output/research/dispersion_daily.csv
   ```

### 10.3 Phase 2: Hypothesis Testing

#### H1: WR by Dispersion Quartile

```python
# For each backtest date:
#   1. Get cross-sectional dispersion on that date
#   2. Assign date to dispersion quartile (Q1-Q4 based on historical distribution)
#   3. Compute forward returns for rank #1 pick
#   4. Aggregate WR by quartile

# Statistical test: two-proportion z-test
z, p = proportions_ztest(
    count=[wins_q4, wins_q1],
    nobs=[total_q4, total_q1],
    alternative='larger'
)
```

**Output table:**
```
| Quartile | Mean Dispersion | N Trades | Wins | Losses | Win Rate | 95% CI |
|----------|-----------------|----------|------|--------|----------|--------|
| Q1 (low) | 2.1%            | 48       | 22   | 26     | 45.8%    | [31, 61] |
| Q2       | 3.4%            | 52       | 30   | 22     | 57.7%    | [43, 71] |
| Q3       | 5.2%            | 50       | 33   | 17     | 66.0%    | [52, 79] |
| Q4 (high)| 8.7%            | 45       | 34   | 11     | 75.6%    | [62, 87] |
```

#### H2: Rank Spread by Dispersion Quartile

```python
# For each date, compute r1 - r5 (forward return of rank 1 minus rank 5)
# Group by dispersion quartile, compute mean spread
# ANOVA test across quartiles

# Output: Box plot of (r1 - r5) by quartile
```

#### H3: Holding Period Decay

```python
# Compute IC(factor_score, forward_return) for 5d, 10d, 21d
# Compute separately for high-dispersion vs low-dispersion days
# Compare: IC_high_5d - IC_low_5d vs IC_high_21d - IC_low_21d

# Bootstrap the IC difference to get confidence intervals
```

#### H4: Sector Decomposition

```python
# For each date:
#   between_sector_disp = std of sector-mean returns
#   within_sector_disp = mean of std within each sector
#   total_disp = between + within (variance decomposition)
# 
# Logistic regression: win ~ within_disp + between_disp + market_vol
```

#### H5: Granger Causality

```python
# Test: Does dispersion(t) Granger-cause volatility(t+h)?
# Using VIX proxy (from market_regime table) as volatility measure

from statsmodels.tsa.stattools import grangercausalitytests
grangercausalitytests(df[['vix_proxy', 'dispersion_5d']].dropna(), maxlag=5)
```

### 10.4 Phase 3: Strategy Integration

**ONLY if Phase 2 confirms H1 and/or H2:**

1. **Add dispersion factor to `factors.py`:**
   - New factor: `cross_sectional_dispersion` — daily market-wide dispersion
   - Factor type: Regime gating factor (not a stock-level factor) — computed once per day, applied to all stocks
   - Scoring impact: Mode-dependent multiplier on existing composite score

2. **Add dispersion-weighted position sizing to `screener.py`:**
   - `position_size_multiplier = 1.0 + weight * (dispersion_percentile - 0.5)`
   - Default weight = 0 → no effect
   - If H5 confirmed: `skip_trade_if(dispersion < threshold)`

3. **Update regime detection in `factors.py`:**
   - Add `dispersion_regime` field: `compressed / normal / expanding`
   - Use for weight tilts in `auto_weights()`

### 10.5 What NOT to Do

1. **Do NOT add dispersion as a stock-level factor.** Dispersion is a market-level variable. Adding it to each stock's score is redundant and creates look-ahead issues.
2. **Do NOT use future dispersion.** Forward-looking dispersion would leak future information. Only use dispersion computed from data available at the signal date.
3. **Do NOT overfit the sector decomposition.** H4 requires more data than we may have. If sector-level sample sizes are too small (< 5 stocks per sector), skip H4.
4. **Do NOT skip the bias checklist.** See Appendix C.

### 10.6 File Modification Plan (IF results warrant deployment)

| File | Change | Condition |
|------|--------|-----------|
| `factors.py` | Add `compute_cross_sectional_dispersion()` function | If H1 confirmed |
| `factors.py` | Add `dispersion_regime` to `compute_regime()` output | If H1 or H5 confirmed |
| `screener.py` | Accept `dispersion` parameter for position sizing | If H1 or H5 confirmed |
| `backtest.py` | Pass dispersion through backtest flow | If H1 or H5 confirmed |
| `baseline.py` | Log dispersion metrics per trade date | Always (for research tracking) |

### 10.7 New File: `scripts/research/dispersion_analysis.py`

**Purpose:** Standalone research script that computes all dispersion metrics and runs hypothesis tests. Does not affect production pipeline.

**Pseudocode structure:**

```python
# scripts/research/dispersion_analysis.py

import sqlite3, os, sys
import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

DB_PATH = os.path.join('..', 'data', 'market_data.db')
OUTPUT_DIR = os.path.join('..', 'output', 'research')

def load_price_data(conn):
    """Load daily close prices for universe stocks."""
    ...

def compute_forward_returns(df):
    """Compute 5d, 10d, 21d forward returns."""
    ...

def compute_daily_dispersion(fwd_returns):
    """Compute cross-sectional dispersion metrics."""
    ...

def compute_daily_ic(factor_scores, forward_returns):
    """Spearman rank correlation per date, per holding period."""
    ...

def test_h1(backtest_results, dispersion_data):
    """WR by dispersion quartile with z-test."""
    ...

def test_h2(backtest_results, dispersion_data):
    """Rank spread by dispersion quartile with ANOVA."""
    ...

def test_h3(factor_scores, forward_returns, dispersion_data):
    """IC decay across holding periods."""
    ...

def test_h4(price_data, sector_map, backtest_results):
    """Between vs within sector dispersion decomposition."""
    ...

def test_h5(dispersion_data, regime_data):
    """Granger causality: dispersion -> volatility."""
    ...

def generate_report(results):
    """Generate a comprehensive analysis report."""
    ...

if __name__ == '__main__':
    conn = sqlite3.connect(DB_PATH)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    prices = load_price_data(conn)
    fwd_rets = compute_forward_returns(prices)
    dispersion = compute_daily_dispersion(fwd_rets)
    # ... run all tests
    
    conn.close()
```

### 10.8 Testing the Existing Baseline Through Dispersion Lens

**Without writing new code**, we can partially test H1 today by querying the 15 baseline dates:

```sql
-- For each baseline date, get forward 5d returns for ALL stocks
-- Compute dispersion, then compare to pick #1 WR
SELECT date, 
       STDDEV(fwd_5d) as disp_5d,
       PERCENTILE_CONT(0.25) WITHIN GROUP(...) as q1_ret,
       PERCENTILE_CONT(0.75) WITHIN GROUP(...) as q3_ret
FROM ...
GROUP BY date
```

Then manually check: do the 3 most dispersed dates in the baseline set have better pick #1 outcomes? With only 15 dates, this is underpowered but provides a quick directional check before committing to the full analysis.

---

## Appendix A: Mathematical Definitions

### A.1 Cross-Sectional Return Dispersion

Let `R = {r_1, r_2, ..., r_N}` be the set of forward returns for `N` stocks at a given date.

**Standard deviation dispersion:**
```
D_σ = sqrt( (1/(N-1)) * Σ(r_i - μ)² )
```
where μ = mean(R)

**Quantile-based dispersion (robust):**
```
D_IQR = Q₇₅(R) - Q₂₅(R)
```

**Top-bottom decile spread:**
```
D_TB = mean(top 10% of R) - mean(bottom 10% of R)
```

### A.2 Gini Coefficient for Returns

```
G = (2 * Σ(i * r_i) / (N * Σ(r_i))) - (N + 1) / N
```
where `r_i` are sorted in ascending order.

Interpretation: G=0 means perfect equality (all returns equal). G=1 means perfect inequality (one stock gets all returns).

### A.3 Variance Decomposition (Sector)

```
Total Var = Σ_s (n_s/N) * (μ_s - μ)² + Σ_s (n_s/N) * σ²_s
            ^^^^^^^^^^^^^^^^^^^^^^^   ^^^^^^^^^^^^^^^^^^
            Between-sector variance   Within-sector variance (weighted)
```

where:
- `s` = sector index
- `n_s` = number of stocks in sector `s`
- `μ_s` = mean return of sector `s`
- `σ²_s` = variance of returns within sector `s`

### A.4 Information Coefficient (IC)

```
IC_t = Spearman_rank_corr(score_i, fwd_return_i)
```

Spearman (rank-based) IC is preferred over Pearson because:
1. The factor model uses percentile ranks as scores
2. Outliers in returns (midcap stocks) inflate Pearson without adding information

### A.5 Falsification Metrics

**For H1 (WR comparison):**
```
z = (p_high - p_low) / sqrt(p_bar * (1-p_bar) * (1/N_high + 1/N_low))
```
where `p_high = WR_high`, `p_low = WR_low`, `p_bar = (W_high + W_low) / (N_high + N_low)`

---

## Appendix B: SQL Queries for Data Extraction

### B.1 Get Universe Stock Symbols

```sql
SELECT symbol, universe_slug, sector 
FROM stocks 
WHERE universe_slug IN ('nifty50', 'niftymidcap150')
ORDER BY universe_slug, symbol;
```

### B.2 Get All Close Prices for Universe

```sql
SELECT d.date, d.symbol, d.close
FROM daily_ohlcv d
JOIN stocks s ON d.symbol = s.symbol
WHERE s.universe_slug IN ('nifty50', 'niftymidcap150')
  AND d.date >= '2021-07-20'
ORDER BY d.date, d.symbol;
```

### B.3 Get Factor Scores for Backtest Dates

```sql
SELECT f.date, f.symbol, f.momentum_price, f.momentum_vol, f.rs_momentum,
       f.trend_adx, f.ma_structure, f.pullback, f.rsi, f.liquidity, f.volatility,
       s.sector, s.universe_slug
FROM factor_scores f
JOIN stocks s ON f.symbol = s.symbol
WHERE s.universe_slug IN ('nifty50', 'niftymidcap150')
  AND f.date >= '2021-07-20'
ORDER BY f.date, f.symbol;
```

### B.4 Get Market Regime Data

```sql
SELECT date, regime, nifty_trend, breadth_ratio, vix_proxy, vix_20d_avg
FROM market_regime
ORDER BY date;
```

### B.5 Get Screener Results (Pick History)

```sql
SELECT sr.run_date, sr.rank, sr.symbol, sr.composite, sr.entry_price, 
       sr.target_price, sr.stoploss, sr.sector, sr.universe
FROM screener_results sr
ORDER BY sr.run_date, sr.rank;
```

---

## Appendix C: Bias Checklist

Before accepting any results, the researcher must document:

| Bias | Check | Mitigation |
|------|-------|------------|
| **Survivorship bias** | Are delisted stocks excluded from the universe? | `stocks` table includes all stocks ever in universe. `daily_ohlcv` includes delisted stocks. Use full history. |
| **Look-ahead bias** | Does dispersion use future returns in its computation? | Dispersion must be computed only from past data (lagged returns). Forward returns are for testing only. |
| **Selection bias** | Is the universe representative of Indian equities? | Nifty 50 + Midcap 150 covers ~75% of market cap. Not representative of micro-caps. Do NOT generalize to small-caps. |
| **Confirmation bias** | Are we only testing dispersion when it works? | Run all hypotheses regardless of preliminary directional signals. Use two-tailed tests where appropriate. |
| **Data leakage** | Does train/test split respect temporal order? | Always time-series split. No random shuffles. Walk-forward with expanding window. |
| **Overfitting** | Are we testing multiple dispersion metrics and only reporting the best? | Pre-register the primary metric (StdDev) before testing. IQR and Gini are secondary/robustness checks. |
| **Multiple testing** | 5 hypotheses × 3 holding periods × 2 quartile splits = 30 tests | Apply Bonferroni correction: significance threshold = 0.05 / 30 ≈ 0.0017. Or use FDR (Benjamini-Hochberg). |
| **Regime look-ahead** | Does dispersion at time t use sector labels that reflect future knowledge? | Sector labels from `stocks` table are static. OK to use. |
| **Survivorship in forward returns** | Does `close[t+h]` exist for all stocks at all dates? | Delisted/bankrupt stocks may drop out. Must handle missing forward returns explicitly. |

### Survival Bias Specific to Midcaps

Midcap 150 stocks have higher delisting/bankruptcy risk than Nifty 50. If dispersion is computed only on surviving stocks, the dispersion metric will be biased downward (survivors have less extreme returns).

**Mitigation:** When computing forward returns, include stocks even if they delist before the forward period ends. Use the last available close as the terminal value. If a stock disappears, treat it as missing for that horizon, NOT as zero return.

---

## Summary

### Hypotheses Ranked by Prior Probability

| Rank | Hypothesis | Prior | Expected IC Improvement | Implementation |
|------|-----------|-------|------------------------|----------------|
| **H1** | Dispersion → model confidence | 35% | +10-20pp WR in high disp | Regime-aware position sizing |
| **H2** | Dispersion → rank stability | 30% | 2× rank spread in high disp | Dynamic portfolio concentration |
| **H3** | Holding period decay | 25% | IC decay from 5d to 21d | Optimal holding period selection |
| **H4** | Sector vs market dispersion | 20% | Within-sector > total | Sector-level dispersion filter |
| **H5** | Dispersion → position sizing | 15% | +5% Sharpe via sizing | Dynamic capital allocation |

### Recommended Testing Order

1. **Quick directional check**: Query the 15 baseline dates for dispersion → win rate relationship (1 hour)
2. **Full backtest**: Run walk-forward across all dates (weekly, ~200 dates) to get 1000+ trades (4-8 hours compute)
3. **H1 (highest probability)**: WR by dispersion quartile — test first
4. **H2 (highest impact if true)**: Rank spread analysis — test second
5. **H3, H4, H5**: Test in parallel or order by data availability

### Decision Gates

| Gate | Condition | Action |
|------|-----------|--------|
| **Basic gate** | H1 WR difference > 10pp, p < 0.10 | Proceed to full analysis |
| **Implementation gate** | H1 confirmed AND at least one of H2-H5 shows signal | Write handoff to `.handoff/spec.md` |
| **Deployment gate** | H1 survives walk-forward OOS testing | Implement in `factors.py` + `screener.py` |
| **Rejection** | H1 WR difference < 5pp at p > 0.10 | Archive research, focus on other topics |

---

*End of research document. No code changes have been implemented.*
