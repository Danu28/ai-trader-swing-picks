---
name: swing-picks
description: Generates top swing trade picks using a 9-factor quant model across Nifty 50 and Midcap 150 stocks. Updates data, computes factors, ranks stocks, outputs entry/target/stoploss with reasoning via console and HTML report.
---

# Swing Picks Skill

Skill for generating top swing trade picks using a quantitative multi-factor model across Nifty 50 and Nifty Midcap 150 stocks.

## Triggers

- `/swing-picks`
- `/swing`
- `/swing-picks backtest YYYY-MM-DD` — run historical backtest for a past date
- `/swing backtest YYYY-MM-DD`
- User requests: "find swing trades", "top swing picks", "swing trading suggestions", "what to swing trade this week"
- User requests: "backtest swing picks for YYYY-MM-DD", "how good were picks on YYYY-MM-DD"

## Workflow

When invoked:

### Step 1: Run the Pipeline

```
python scripts/pipeline.py --full --top 5
```

Options:
- `--skip-update` — skip yfinance data refresh (use existing DB data)
- `--top N` — override default 5 picks
- `--weights momentum=0.35,trend_quality=0.25,mean_reversion=0.25,quality=0.15`
- `--sector-cap N` — override sector concentration limit

### Step 2: Read Context

Read `output/context_YYYY-MM-DD.json` for full pipeline output:
- `run_metadata` — data freshness, symbols scored/filtered, weights used
- `market_regime` — current regime classification
- `top_picks` — ranked picks with full factor breakdowns and price levels
- `filters_applied` — rejected stocks and reasons
- `warnings` — pipeline-generated warnings

### Step 3: Validate with Quality Gates

Apply these gates to the top picks:

| Gate | Condition | AI Action |
|------|-----------|-----------|
| Conviction | Top pick composite < 60 | Warn user: "No high-conviction setups today. Top score: {score}." |
| Sector concentration | >2 picks from same sector | Already enforced. Warn if near-limit. |
| Stale data | Any pick's data >3 days old | Flag in output: "Stale data for {symbol} — verify manually." |
| Extended chase | pullback < 40 AND momentum > 80 | Warn: "Extended/chasing risk on {symbol}. Wait for pullback." |
| Regime mismatch | risk_off regime + high momentum picks | Warn: "Risk-off regime — consider defensive positioning." |

### Step 4: Load Market Regime Context

Load the `market-regime` skill to verify and enhance regime classification from the DB. If the market_regime table is empty, compute regime from available data (breadth, VIX proxy, Nifty trend).

### Step 5: Generate AI Reasoning

For each pick, use this template:

```
**#{rank} {symbol}** ({sector}, {universe}) — Composite: {composite}/100
  **Why**: {top 2 driving factors with actual scores} — e.g. "RS momentum (82) + MA alignment (90)"
  **Entry**: ₹{entry_price} — {entry logic: pullback to 20-SMA or current price}
  **Target**: ₹{target_price} — 2× ATR target
  **Stoploss**: ₹{stoploss} — 1× ATR below entry
  **Risk**: {any flags — sector concentration, low liquidity, regime mismatch, earnings proximity}
```

### Step 6: Console Summary

Print formatted table to console:

```
======================================================================
  SWING PICKS — YYYY-MM-DD | Regime: RISK-ON
======================================================================
  Rank  Symbol             Score    Entry        Target       Stoploss
  ----- ------------------ -------- ------------ ------------ ------------
  #1    RELIANCE.NS        87.2     ₹2,850.50    ₹3,120.00    ₹2,760.00
  #2    TCS.NS             84.1     ₹4,100.25    ₹4,350.00    ₹3,980.00
  ...
======================================================================
  Report: output/swing_report_YYYY-MM-DD.html
```

### Step 7: Open HTML Report

Open `output/swing_report_YYYY-MM-DD.html` in the browser.

### Step 8: Offer Follow-up

Ask: "Want me to drill into any of these picks, explain why a specific stock didn't make the cut, or check a different sector?"

## Backtest Workflow

When a backtest date is specified (e.g., `/swing-picks backtest 2026-07-01`):

### Step B1: Run Backtest Script

```
python scripts/backtest.py --as-of YYYY-MM-DD --top 5
```

This simulates the pipeline as if run on the given date (zero look-ahead bias — all OHLCV data filtered to `<= as_of_date`), then checks forward price action to determine if each pick hit its target or stoploss.

### Step B2: Read Results

The backtest outputs for each pick: result (WIN/LOSS/DRAW), detail (which hit first, final close), max gain %, max loss %.

### Step B3: AI Analysis

Generate analysis covering:

1. **Headline summary**: win/loss/draw counts, win rate
2. **Per-pick commentary**: what drove each outcome
   - WIN: "Target hit in X days — momentum continued as expected"
   - LOSS: "SL hit on YYYY-MM-DD — identify what broke (volatility spike, trend reversal)"
   - DRAW: "Neither hit but closed +X% — target was aggressive (2×ATR) but trade was still profitable. Consider tighter target or trailing stop."
3. **Regime context**: what was the market regime at the time and did it align with the picks' styles?
4. **Pattern detection**: any common traits among winners vs losers?
   - Were winners higher quality stocks? Stronger trend? Better pullback entries?
   - Did losers share any warning signs (low liquidity, extended momentum)?
5. **Overall assessment**: Is the strategy performing as expected? Any parameter tweaks suggested?

### Step B4: Offer Deeper Analysis

Offer to:
- Run backtest for additional dates to build sample size
- Drill into factor breakdowns of individual picks on that date
- Compare with benchmark (Nifty 50) performance over the same period

## AI Follow-up Question Handlers

### "Why didn't {symbol} make the cut?"

Read `filters_applied.rejected` in the context JSON. If the symbol is there, explain the rejection reason. If not in rejected, read factor_scores from DB for that symbol and explain which factors dragged the composite down.

### "Show me all {sector} stocks"

Query `factor_scores` joined with `stocks` filtered by sector, ordered by composite descending. Present as ranked table.

### "Explain {symbol}'s factor breakdown"

Read `factor_detail` for the symbol from the context JSON. Present all 9 factor scores with interpretation:
- >75: Strong
- 50-75: Neutral-positive
- 25-50: Neutral-negative
- <25: Weak

### "Any data issues?"

Read `warnings` array and `update_summary` from context JSON. Report failed symbols, stale data flags, freshness percentage.

### "Overweight/underweight a category?"

Use `--weights` flag to re-run screener with modified weights. E.g., to overweight momentum:
```
python scripts/screener.py --top 5 --weights momentum=0.45,trend_quality=0.20,mean_reversion=0.20,quality=0.15
```

## Regime-Based Weight Overrides

When `market_regime.regime` exists:

| Regime | Momentum | Trend Quality | Mean Reversion | Quality | Rationale |
|--------|----------|---------------|----------------|---------|-----------|
| risk_on | 0.35 | 0.25 | 0.25 | 0.15 | Standard — momentum and trend favored |
| neutral | 0.30 | 0.25 | 0.25 | 0.20 | Slightly defensive — quality up |
| risk_off | 0.20 | 0.20 | 0.25 | 0.35 | Defensive — quality and mean reversion over momentum |

If regime is risk_off, re-run screener with overridden weights before generating final output.

## Factor Model Reference

9 factors across 4 categories. All scored 0-100 as cross-sectional percentile ranks.

**Momentum (35%)**: momentum_price (ROC 21×63), momentum_vol (vol ratio 10/50d), rs_momentum (21d vs Nifty)
**Trend Quality (25%)**: trend_adx (ADX 14), ma_structure (20>50>200 alignment)
**Mean Reversion (25%)**: pullback (distance from 20d high), rsi (zone scoring)
**Quality (15%)**: liquidity (avg turnover), volatility (inverted ATR/close)

Hard filter: liquidity < 25th percentile excluded. Sector cap: max 2 per sector.

## Dependencies

- Python packages: yfinance, pandas, numpy, scipy
- Skills: market-regime (for regime classification)
- DB: data/market_data.db with stocks, daily_ohlcv, factor_scores, screener_results, market_regime tables
