# Swing Picks Skill — Design Spec

**Date**: 2026-07-19
**Status**: Draft
**Author**: AI-Trader

---

## 1. Overview

A skill (`swing-picks`) that when invoked:
1. Updates the SQLite DB with fresh daily OHLCV data via yfinance
2. Computes a 9-factor quant model across all Nifty 50 + Nifty Midcap 150 stocks
3. Ranks stocks by composite score, screens for swing entry setups
4. Outputs the top 5 picks with entry price, target, stoploss, and reasoning
5. Presents results as a console summary + an HTML report
6. Exposes structured JSON context for AI-driven qualitative reasoning

---

## 2. Current State

- **DB**: `data/market_data.db` (SQLite)
  - `stocks`: 197 stocks (48 Nifty 50, 149 Nifty Midcap 150), 36 sectors
  - `daily_ohlcv`: 680K rows, 316 symbols, date range 2016-07-11 to 2026-07-17
- Data freshness: Nifty 50 stocks current to 2026-07-17, some midcaps ~1-2 weeks behind
- No existing Python scripts, no existing skills

---

## 3. Architecture

```
AI-Trader/
├── data/
│   └── market_data.db              # existing, extended with new tables
├── scripts/
│   ├── pipeline.py                 # entry point, orchestrates 4 stages
│   ├── updater.py                  # yfinance fetch → upsert daily_ohlcv
│   ├── factors.py                  # compute 9 factors → factor_scores table
│   ├── screener.py                 # composite rank → screener_results table
│   └── reporter.py                 # console table + HTML report + context JSON
├── output/
│   ├── swing_report_YYYY-MM-DD.html
│   └── context_YYYY-MM-DD.json
├── logs/
│   └── pipeline_YYYY-MM-DD.log
└── .opencode/
    └── skills/
        └── swing-picks/
            └── SKILL.md
```

### 3a. New DB Tables

#### `factor_scores`
| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Stock symbol (PK part) |
| date | TEXT | Trade date (PK part) |
| momentum_price | REAL | ROC(21) vs ROC(63) percentile rank, 0-100 |
| momentum_vol | REAL | 10d avg vol / 50d avg vol percentile, 0-100 |
| rs_momentum | REAL | 21d relative strength vs Nifty 50, 0-100 |
| trend_adx | REAL | ADX(14) ranked, 0-100 |
| ma_structure | REAL | SMA alignment score (20>50>200), 0-100 |
| pullback | REAL | Distance from 20d high (inverted), 0-100 |
| rsi | REAL | RSI(14) converted to entry-zone score, 0-100 |
| liquidity | REAL | Avg daily turnover percentile, 0-100 |
| volatility | REAL | ATR(14)/close (inverted), 0-100 |
| composite | REAL | Weighted composite score, 0-100 |

#### `screener_results`
| Column | Type | Description |
|--------|------|-------------|
| run_date | TEXT | Run timestamp (PK part) |
| rank | INTEGER | Final rank (PK part) |
| symbol | TEXT | Stock symbol |
| composite | REAL | Final composite score |
| factor_breakdown | TEXT | JSON: per-category scores |
| entry_price | REAL | Suggested entry price |
| target_price | REAL | Suggested target |
| stoploss | REAL | Suggested stoploss |
| sector | TEXT | Stock sector |
| universe | TEXT | nifty50 / niftymidcap150 |

#### `market_regime`
| Column | Type | Description |
|--------|------|-------------|
| date | TEXT | Trade date (PK) |
| regime | TEXT | risk_on / neutral / risk_off |
| nifty_trend | TEXT | bullish / bearish / sideways |
| breadth_ratio | REAL | Advancers/decliners ratio |
| vix_proxy | REAL | India VIX or Nifty ATR proxy |

---

## 4. Factor Model

### 4a. Factor Definitions (9 factors, 4 categories)

#### Category 1: Momentum (weight: 35%)
| # | Factor | Formula | Signal |
|---|--------|---------|--------|
| 1 | Price Momentum | Percentile rank of ROC(21) × ROC(63) across universe | Higher = stronger multi-timeframe trend |
| 2 | Volume Momentum | Percentile rank of (10d avg vol / 50d avg vol) | >50 = accumulation, <50 = distribution |
| 3 | RS Momentum | Percentile rank of (stock 21d return − Nifty 50 21d return) | >50 = outperforming benchmark |

#### Category 2: Trend Quality (weight: 25%)
| # | Factor | Formula | Signal |
|---|--------|---------|--------|
| 4 | Trend Strength | Percentile rank of ADX(14) | >50 = trending, <30 = sideways/choppy |
| 5 | MA Structure | Score: +1 per aligned SMA (20>50, 50>200, 20>200), +1 if price above 20, scaled 0-100 | 100 = perfect bullish alignment |

#### Category 3: Mean Reversion / Entry Timing (weight: 25%)
| # | Factor | Formula | Signal |
|---|--------|---------|--------|
| 6 | Pullback Depth | 100 − percentile_rank(distance_from_20d_high) where distance = (high − close) / high | 60-80 = 3-8% pullback in uptrend (entry zone) |
| 7 | RSI Context | If RSI(14) in [40,60]: score=100; in [30,40] or [60,70]: score=60; else score=20 | 40-60 = not extended, room to run |

#### Category 4: Quality / Liquidity (weight: 15%)
| # | Factor | Formula | Signal |
|---|--------|---------|--------|
| 8 | Liquidity | Percentile rank of avg daily turnover (close × volume, 20d avg) | Higher = more liquid, lower slippage |
| 9 | Volatility (inverted) | 100 − percentile_rank(ATR(14) / close) | Lower vol = more predictable, less whipsaw |

### 4b. Composite Score
```
category_score(cat) = mean(factors in cat)
composite = Σ (category_weight × category_score)
```
All factor values are 0-100 percentile ranks, so no normalization needed.

### 4c. Filters
| Filter | Rule |
|--------|------|
| Hard filter | Liquidity factor < 25 (bottom quartile) → excluded |
| Sector cap | Max 2 stocks per sector in final top-N |
| Data minimum | Min 200 trading days of history required |

### 4d. Entry / Target / Stoploss
| Value | Default method | Fallback |
|-------|---------------|----------|
| Entry | Current close (or 20-SMA if pullback factor > 65) | — |
| Target | Entry + (2 × ATR(14)) | Entry + (1.5 × ATR) if 2× ATR exceeds 52w high |
| Stoploss | Entry − (1 × ATR(14)) | Min of ATR stop and recent 10d swing low |

Target/stop are suggestions; the AI adds qualitative judgment.

---

## 5. Script Design

### 5a. pipeline.py — CLI
```
python scripts/pipeline.py --full            # all 4 stages
python scripts/pipeline.py --skip-update     # skip updater
python scripts/pipeline.py --top 10          # override default top-5
python scripts/pipeline.py --weights momentum=0.40,trend_quality=0.20,mean_reversion=0.25,quality=0.15
python scripts/pipeline.py --sector-cap 3    # override sector cap
```

### 5b. Structured Logging
Every module writes JSON lines to `logs/pipeline_YYYY-MM-DD.log`. Each line has:
```json
{"stage": "<module>", "ts": "<iso timestamp>", ...stage-specific fields...}
```

Concrete log contract per stage is defined in Section 7 (Appendix).

### 5c. Context JSON (`output/context_YYYY-MM-DD.json`)
```json
{
  "run_metadata": {
    "run_date": "2026-07-19",
    "pipeline_version": "1.0",
    "data_freshness_pct": 98.5,
    "symbols_total": 197,
    "symbols_scored": 195,
    "symbols_filtered": 2,
    "top_n": 5,
    "weights_used": {"momentum": 0.35, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.15}
  },
  "market_regime": {
    "regime": "risk_on",
    "nifty_trend": "bullish",
    "breadth_ratio": 0.72,
    "vix_proxy": 12.3
  },
  "top_picks": [
    {
      "rank": 1,
      "symbol": "RELIANCE.NS",
      "composite": 87.2,
      "factor_breakdown": {
        "momentum": 75.0,
        "trend_quality": 80.5,
        "mean_reversion": 57.5,
        "quality": 83.5
      },
      "factor_detail": {
        "momentum_price": 78,
        "momentum_vol": 65,
        "rs_momentum": 82,
        "trend_adx": 71,
        "ma_structure": 90,
        "pullback": 55,
        "rsi": 60,
        "liquidity": 95,
        "volatility": 72
      },
      "entry_price": 2850.50,
      "target_price": 3120.00,
      "stoploss": 2760.00,
      "sector": "Energy",
      "universe": "nifty50"
    }
  ],
  "filters_applied": {
    "min_liquidity_percentile": 25,
    "sector_cap": 2,
    "rejected": [
      {"symbol": "XYZ.NS", "reason": "sector_cap", "would_have_ranked": 3},
      {"symbol": "ABC.NS", "reason": "low_liquidity"}
    ]
  },
  "factor_distribution": {
    "top_decile_sectors": ["Financial Services", "Energy"],
    "composite_distribution": {"p25": 42, "p50": 58, "p75": 72, "p90": 83}
  },
  "update_summary": {
    "symbols_updated": 42,
    "symbols_skipped": 153,
    "symbols_failed": ["XYZ.NS"],
    "data_through_date": "2026-07-17"
  },
  "warnings": [
    "XYZ.NS update failed — using stale data from 2026-07-10",
    "Financial Services sector hit cap, 3 additional stocks displaced"
  ]
}
```

---

## 6. SKILL File Design

Location: `.opencode/skills/swing-picks/SKILL.md`

### 6a. Triggers
- `/swing-picks`
- `/swing`
- User request: "find swing trades", "top swing picks", "swing trading suggestions"

### 6b. Workflow
1. Run `python scripts/pipeline.py --full`
2. Read `output/context_YYYY-MM-DD.json`
3. Load `market-regime` skill for regime context
4. Validate picks against quality gates (see 6c)
5. Generate reasoning for each pick using factor breakdown
6. Print console summary table
7. Open HTML report in browser
8. Offer follow-up analysis

### 6c. AI Quality Gates
| Gate | Condition | Action |
|------|-----------|--------|
| Conviction threshold | Top pick composite < 60 | Warn: "No high-conviction setups today" |
| Sector concentration | >3 picks from same sector | Warn: "Sector concentration risk" |
| Stale data | Any pick data >3 days old | Warn: "Stale data — verify manually" |
| Extended chase | Pullback < 40 AND Momentum > 80 | Warn: "Extended — chasing risk, wait for pullback" |
| Regime mismatch | risk_off regime, high momentum picks | Warn: "Risk-off regime — consider defensive positions or skip" |

### 6d. AI Reasoning Template
```
**#{rank} {symbol}** ({sector}) — Score: {composite}/100
  Drivers: {top_2_factors_with_scores}
  Setup: {entry_logic_from_factors}
  Entry: ₹{entry} | Target: ₹{target} | SL: ₹{stoploss}
  Risk: {any_flags_or_none}
```

### 6e. Follow-up Questions AI Can Answer
- "Why didn't {symbol} make the cut?" → Check `rejected` list and factor scores
- "Show me all {sector} stocks" → Read `factor_scores` filtered by sector
- "Explain {symbol}'s factor breakdown" → Read `factor_detail`
- "Any data issues?" → Read `warnings` + `update_summary`
- "Overweight momentum this week?" → Use market-regime skill to advise

### 6f. Regime Override Logic
```python
if regime == "risk_off":
    weights = {"momentum": 0.20, "trend_quality": 0.20, "mean_reversion": 0.25, "quality": 0.35}
    ai_flag = "Risk-off regime — quality and defense overweighted"
elif regime == "risk_on":
    weights = standard (defined in Section 4a)
    ai_flag = "Risk-on regime — standard weights"
```

If regime override is active, re-run `screener.py` with modified weights.

---

## 7. Dependencies

### Python packages
```
yfinance>=0.2.40
pandas>=2.0
numpy>=1.24
sqlite3 (stdlib)
json (stdlib)
argparse (stdlib)
logging (stdlib)
```

### Skills loaded
- `market-regime` — regime classification and context
- `quant-research` — factor validation methodology
- `beautiful-reports` — HTML report customization (optional)

---

## 8. Non-Goals (v1)
- Intraday or tick-level data
- Fundamental data (P/E, earnings, etc.)
- Automated order placement or broker integration
- Backtesting the factor model (separate skill — use `backtesting` skill)
- Portfolio allocation / position sizing beyond entry-target-stoploss
- Email/notification delivery
- Scheduled automatic updates

---

## 9. Appendix: Log Contract Per Stage

### updater.py
```
{"stage":"update","status":"start","symbols_total":197,"ts":"..."}
{"stage":"update","symbol":"RELIANCE.NS","action":"insert","rows":5,"date_range":["2026-07-13","2026-07-17"],"ts":"..."}
{"stage":"update","symbol":"TCS.NS","action":"no_new_data","reason":"already_current","ts":"..."}
{"stage":"update","symbol":"XYZ.NS","action":"error","error":"yfinance timeout","retries":3,"ts":"..."}
{"stage":"update","status":"complete","updated":42,"skipped":153,"errors":2,"errors_detail":[{"symbol":"XYZ.NS","error":"timeout"}],"ts":"..."}
```

### factors.py
```
{"stage":"factors","status":"start","symbols":197,"factors":["momentum_price","momentum_vol","rs_momentum","trend_adx","ma_structure","pullback","rsi","liquidity","volatility"],"ts":"..."}
{"stage":"factors","symbol":"XYZ.NS","scores":{...},"warnings":["low_liquidity_rejected"],"ts":"..."}
{"stage":"factors","status":"complete","computed":195,"filtered_out":2,"filter_reasons":{"XYZ.NS":"low_liquidity","ABC.NS":"insufficient_data"},"ts":"..."}
```

### screener.py
```
{"stage":"screen","status":"start","top_n":5,"weights":{...},"sector_cap":2,"ts":"..."}
{"stage":"screen","rank":1,"symbol":"RELIANCE.NS","composite":87.2,"breakdown":{...},"entry":2850.50,"target":3120.00,"stoploss":2760.00,"sector":"Energy","ts":"..."}
{"stage":"screen","status":"complete","top_n":5,"sector_distribution":{"Energy":1},"ts":"..."}
```

### reporter.py
```
{"stage":"report","status":"start","ts":"..."}
{"stage":"report","file":"output/context_2026-07-19.json","size_kb":14.2,"ts":"..."}
{"stage":"report","file":"output/swing_report_2026-07-19.html","size_kb":45.8,"ts":"..."}
{"stage":"report","status":"complete","ts":"..."}
```
