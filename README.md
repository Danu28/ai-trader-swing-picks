# AI-Trader — Swing Picks Skill

Quantitative swing trade screening for Nifty 50 + Nifty Midcap 150 stocks.

## Quick Start

```bash
git clone <repo>
cd AI-Trader
python scripts/init_db.py          # Create DB + populate stock universe
python scripts/pipeline.py --full   # Fetch data + screen + report
```

First `--full` run fetches ~10 years of OHLCV data from Yahoo Finance. Subsequent runs update incrementally.

## Usage

```bash
# Full run (fetch data + screen)
python scripts/pipeline.py --full --top 5

# Skip data update (data already current)
python scripts/pipeline.py --skip-update --top 5

# Custom weights
python scripts/pipeline.py --skip-update --top 5 --weights momentum=0.30,trend_quality=0.25,mean_reversion=0.25,quality=0.20

# Backtest a past date
python scripts/backtest.py --as-of 2026-07-01 --top 5
```

## Structure

```
scripts/
├── init_db.py        # Bootstrap DB with stock universe
├── pipeline.py       # CLI orchestrator
├── updater.py        # yfinance data fetcher
├── factors.py        # 9-factor quant model
├── screener.py       # Composite ranking + entry/target/SL
├── reporter.py       # Console + HTML + JSON output
└── backtest.py       # Historical validation (zero look-ahead)

output/
├── context_YYYY-MM-DD.json   # Full run context for AI
└── swing_report_YYYY-MM-DD.html

data/
└── market_data.db    # SQLite (not tracked in git)
```

## Factor Model

9 factors across 4 categories, cross-sectional percentile ranked (0-100):

| Category (weight) | Factors |
|-------------------|---------|
| Momentum (35%) | Price momentum, Volume momentum, Relative strength |
| Trend Quality (25%) | ADX trend strength, MA structure alignment |
| Mean Reversion (25%) | Pullback depth, RSI zone |
| Quality (15%) | Liquidity, Volatility (inverted) |

Hard filter: liquidity < 25th percentile excluded. Sector cap: max 2 per sector.
