# AI-Trader — Swing Picks Skill

> **Daily Report:** [danu28.github.io/ai-trader-swing-picks](https://danu28.github.io/ai-trader-swing-picks/)  
> Top 5 swing picks updated every market day at 5:00 PM IST via GitHub Actions.

Quantitative swing trade screening across Nifty 50 and Nifty Midcap 150 stocks. A multi-factor model ranks 196 stocks daily, outputs the top 5 picks with entry price, target, stoploss, and reasoning via console, HTML report, and structured JSON for AI consumption.

## Quick Start

```bash
# Clone — the repo includes a baseline DB with 5 years of data
git clone <repo>
cd AI-Trader
pip install yfinance pandas numpy scipy

# Run immediately — no init_db needed; fetches only latest days
python scripts/pipeline.py --full --top 5
```

The repo ships with a pre-built `data/market_data.db` (tables + ~5 years of OHLCV data).
First run fetches only the missing trading days since the snapshot.

## Usage

### Forward Picks

```bash
# Full run after market close (fetch fresh data + screen)
python scripts/pipeline.py --full --top 5

# Skip data update when data is already current (weekends, same-day re-runs)
python scripts/pipeline.py --skip-update --top 5

# Custom factor weights
python scripts/pipeline.py --skip-update --top 5 \
  --weights momentum=0.30,trend_quality=0.25,mean_reversion=0.25,quality=0.20

# Override sector concentration limit
python scripts/pipeline.py --skip-update --top 10 --sector-cap 3
```

### Backtesting

```bash
# Check what picks would have been made on a past date + whether they hit target/SL
python scripts/backtest.py --as-of 2026-07-01 --top 5
```

The backtest uses zero look-ahead bias — all OHLCV data is filtered to `<= as_of_date`. It then checks forward price action to determine if each pick hit target (WIN), stoploss (LOSS), or neither (DRAW).

### Opencode Skill

The skill is loaded automatically by opencode. Triggers:

- `/swing-picks` — run forward screening
- `/swing-picks backtest YYYY-MM-DD` — run historical backtest with AI analysis
- `/swing` — alias

The AI applies quality gates (conviction threshold, sector concentration, stale data, extended chase, regime mismatch) and generates per-pick reasoning with factor attribution.

## Reports

Each run generates two files in `output/`:

| File | Purpose |
|------|---------|
| `context_YYYY-MM-DD.json` | Full structured context for AI — run metadata, regime, factor breakdowns, warnings, filtered stocks |
| `swing_report_YYYY-MM-DD.html` | Dark-themed standalone HTML report with ranked picks, drivers, price levels, and meta cards |

Console output includes a formatted table with ranked picks and pipeline warnings.

## Project Structure

```
AI-Trader/
├── scripts/
│   ├── init_db.py         # Bootstrap empty DB with 196 stock universe
│   ├── pipeline.py        # CLI orchestrator — chains updater → factors → screener → reporter
│   ├── updater.py         # yfinance OHLCV fetcher with retry + structured JSON logging
│   ├── factors.py         # 9-factor quant engine + percentile ranking + regime detection
│   ├── screener.py        # Composite scoring, sector cap, entry/target/SL derivation
│   ├── reporter.py        # Console table, context JSON, HTML report
│   └── backtest.py        # Historical validation — simulates past run + target/SL hit checking
├── output/                # Generated reports (gitignored)
├── logs/                  # Per-run JSON logs (gitignored)
├── data/market_data.db    # SQLite database (committed — 5yr baseline snapshot)
├── .opencode/skills/swing-picks/SKILL.md
└── README.md
```

## Database Schema

5 tables in `data/market_data.db`:

| Table | Purpose |
|-------|---------|
| `stocks` | Stock universe — symbol, company name, sector, universe (nifty50/midcap150) |
| `daily_ohlcv` | Daily open, high, low, close, volume, adj close per stock |
| `factor_scores` | Per-stock per-date 9-factor values (0-100 percentile ranks) |
| `screener_results` | Final ranked output per run — rank, composite, entry/target/SL, factor breakdown |
| `market_regime` | Daily regime classification — risk_on/neutral/risk_off, breadth ratio, VIX proxy |

## Factor Model

9 factors across 4 categories. All scored 0-100 as cross-sectional percentile ranks — no normalization needed.

### Momentum (weight: 35%)

| Factor | Formula | Signal |
|--------|---------|--------|
| Price Momentum | Percentile rank of ROC(21) × ROC(63) | Higher = stronger multi-timeframe trend |
| Volume Momentum | Percentile rank of 10d avg vol / 50d avg vol | >50 = accumulation |
| RS Momentum | Percentile rank of (stock 21d return − Nifty 50 21d return) | >50 = outperforming benchmark |

### Trend Quality (weight: 25%)

| Factor | Formula | Signal |
|--------|---------|--------|
| Trend Strength (ADX) | Percentile rank of ADX(14) | >50 = trending, <30 = sideways |
| MA Structure | Scored alignment: +25 each for 20>50, 50>200, 20>200, price>20SMA | 100 = perfect bullish alignment |

### Mean Reversion / Entry Timing (weight: 25%)

| Factor | Formula | Signal |
|--------|---------|--------|
| Pullback Depth | 100 − percentile rank of distance from 20d high | 60-80 = 3-8% pullback in uptrend (entry zone) |
| RSI Context | 100 if RSI(14) in [40,60]; 60 if [30,40] or [60,70]; 20 otherwise | 100 = ideal zone, not extended, not broken |

### Quality / Liquidity (weight: 15%)

| Factor | Formula | Signal |
|--------|---------|--------|
| Liquidity | Percentile rank of avg daily turnover (close × volume, 20d) | Higher = lower slippage |
| Volatility (inverted) | 100 − percentile rank of ATR(14)/close | Higher = more predictable, less whipsaw |

### Composite Score

```
category_score = mean(factors in category)
composite = Σ (category_weight × category_score)
```

### Filters

| Filter | Rule |
|--------|------|
| Hard filter | Liquidity < 25th percentile → excluded |
| Sector cap | Max 2 stocks per sector in top-N |
| Data minimum | ≥ 200 trading days of history required |

### Entry / Target / Stoploss

| Value | Method |
|-------|--------|
| Entry | Current close (or 20-SMA if pullback factor > 65) |
| Target | Entry + (2 × ATR(14)) |
| Stoploss | Entry − (1 × ATR(14)) |

## Market Regime Detection

Computed from Nifty 50 stocks as proxy:

| Metric | Method |
|--------|--------|
| Nifty trend | 21-day average return of Nifty 50 stocks |
| Breadth ratio | % of Nifty 50 stocks above 50-day SMA |
| VIX proxy | Average ATR(14)/close across Nifty 50 |

| Regime | Condition | Weight Adjustment |
|--------|-----------|-------------------|
| risk_on | Return > 2% AND breadth > 0.5 | Standard (M:0.35, T:0.25, MR:0.25, Q:0.15) |
| neutral | Between thresholds | Defensive (M:0.30, T:0.25, MR:0.25, Q:0.20) |
| risk_off | Return < −2% AND breadth < 0.4 | Conservative (M:0.20, T:0.20, MR:0.25, Q:0.35) |

## AI Quality Gates

Applied by the opencode skill after pipeline execution:

| Gate | Condition | Action |
|------|-----------|--------|
| Conviction | Top pick composite < 60 | Warn: low-confidence picks |
| Extended chase | Pullback < 40 AND Momentum > 80 | Warn: chasing risk |
| Stale data | Pick data > 3 days old | Warn: verify manually |
| Regime mismatch | risk_off + high momentum picks | Warn: defensive positioning advised |

## Dependencies

```
yfinance >= 0.2.40
pandas >= 2.0
numpy >= 1.24
scipy (for rankdata)
```

## Backtest Results

Run on 2026-07-01 (regime: neutral, 16-day forward window):

| Result | Count |
|--------|-------|
| Wins | 2/5 (40%) |
| Losses | 1/5 |
| Draws (positive) | 2/5 |
| Avg return | +5.4% |

Combined profitable: 4/5. Draws were above entry but didn't reach the aggressive 2× ATR target.

## Non-Goals

- Intraday or tick-level data
- Fundamental data (P/E, earnings)
- Automated order placement / broker integration
- Portfolio allocation / position sizing
- Email / notification delivery
- Scheduled cron updates
