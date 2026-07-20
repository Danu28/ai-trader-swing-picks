# RESEARCH REPORT: R:R Ratio, Position Sizing & Trading Charges

**Branch:** `research/rr-positionsize-charges`
**Date:** 2026-07-20
**Author:** Institutional Quant Research — AI-Trader System

---

## Table of Contents

1. [Current State Assessment](#1-current-state-assessment)
2. [R:R Ratio Analysis](#2-rr-ratio-analysis)
3. [Position Sizing Analysis](#3-position-sizing-analysis)
4. [NSE Trading Charges Analysis](#4-nse-trading-charges-analysis)
5. [Integrated Recommendations](#5-integrated-recommendations)
6. [Implementation Plan](#6-implementation-plan)
7. [References](#7-references)

---

## 1. Current State Assessment

### 1.1 How Target and Stoploss Are Calculated (screener.py L215-L222)

```python
entry_price = price
target_price = entry_price + (1.5 * atr_val) if atr_val > 0 else entry_price * 1.04
stoploss = entry_price - (1.5 * atr_val) if atr_val > 0 else entry_price * 0.96
```

**Key observation:** Both target and stoploss are set at **1.5× ATR** from entry. This produces a **1:1 risk:reward ratio** — symmetrical. The fallback (no ATR) uses 4% each way, also 1:1.

### 1.2 How Returns Are Calculated (backtest.py L852-L857)

```python
if result == "WIN":
    return_pct = (target - entry) / entry * 100    # ≈ +1.84% avg
elif result == "LOSS":
    return_pct = (stoploss - entry) / entry * 100   # ≈ -1.84% avg
else:
    return_pct = (end_close - entry) / entry * 100  # ≈ 0% avg
```

**No position sizing, no capital tracking.** Returns are raw percentages summed across trades as if each trade is a fixed 1-unit bet.

### 1.3 Baseline Performance (as of 2026-07-20)

| Metric | Overall | risk_on | neutral | risk_off |
|--------|---------|---------|---------|----------|
| Win Rate | 68.0% | 66.7% | 55.6% | 80.0% |
| Avg Return | +1.84% | — | — | — |
| Total Return | +91.96% | +19.24% | +9.52% | +63.20% |
| Avg Hold Days | ~5-7 | — | — | — |
| R:R | 1:1 | 1:1 | 1:1 | 1:1 |

### 1.4 Critical Gaps Identified

| Gap | Impact |
|-----|--------|
| **No position sizing** | `total_return = sum(return_pct)` assumes equal 1-unit bets. No capital compounding. |
| **No trading costs** | STT, brokerage, exchange fees, GST are all ignored. True net returns are overstated. |
| **R:R is 1:1 (fixed)** | Never adjusted. May be suboptimal given the observed 68% win rate. |
| **No portfolio-level tracking** | No max drawdown, Sharpe ratio, or risk-of-ruin metrics. |
| **Return measured as sum of %** | A trade with +5% on a ₹100 stock counts same as +5% on a ₹3000 stock. |

---

## 2. R:R Ratio Analysis

### 2.1 The Mathematics

**Current system at 1:1 (68% win rate):**

```
EV = (WinRate × WinAmount) - (LossRate × LossAmount)
EV = (0.68 × 1R) - (0.32 × 1R)
EV = +0.36R per trade
```

**Alternative: Widen target to 1.5:1 (keeping stoploss at 1.5 ATR, target at 2.25 ATR):**

This would increase the target distance from 1.5 ATR to 2.25 ATR (+50% wider target).

If win rate drops to ~55% (reasonable estimate — farther targets hit less often):
```
EV = (0.55 × 1.5R) - (0.45 × 1R)
EV = +0.375R per trade
```
**Higher EV than current!**

**Alternative: 2:1 R:R (target at 3.0 ATR, stop at 1.5 ATR):**

If win rate drops to ~45%:
```
EV = (0.45 × 2R) - (0.55 × 1R)
EV = +0.35R per trade
```
Approximately same EV as current.

### 2.2 Breakeven Win Rates by R:R

| R:R Ratio | Breakeven WR | Current WR | Edge |
|-----------|-------------|------------|------|
| 1:1 | 50.0% | 68.0% | +18pp |
| 1.5:1 | 40.0% | ~55%* | +15pp |
| 2:1 | 33.3% | ~45%* | +12pp |
| 2.5:1 | 28.6% | ~38%* | +9pp |
| 3:1 | 25.0% | ~33%* | +8pp |

*Estimated WR at wider targets.

### 2.3 What Professionals Use

**Research findings (Indian market focus):**
- **Median recommendation:** 1:2 minimum for swing trades across multiple sources (Rupeepath 2026, Olox, Finovatives)
- **Conservative:** 1:1.5 minimum (Finovatives, MomentumIQ)
- **Aggressive:** 1:3 minimum for 2026 markets (CashSutra 2026 Framework)
- **Key insight:** "A 40% win rate at 1:2 R:R beats a 70% win rate at 1:1 R:R over time" — this is a widely cited principle because the EV is higher (0.40×2 − 0.60×1 = +0.20R vs 0.70×1 − 0.30×1 = +0.40R — actually current wins here, but the CAGR advantage of asymmetric payoffs compounds better).

Wait, let me be precise:

At 1:1 R:R with 68% WR: EV = +0.36R
At 2:1 R:R with 40% WR: EV = 0.40×2 − 0.60×1 = +0.20R

So the 1:1 with 68% WR actually has higher raw EV. But:

**The real benefit of wider R:R is about position sizing:** With a wider stoploss (same 1.5 ATR but farther target), you can risk the same dollar amount per trade for a larger potential payoff. But actually in our case the stoploss distance stays the same (1.5 ATR) — we'd be widening the target only.

**Revised analysis — Widen target only, keep stop at 1.5 ATR:**

This means: R:R = target_distance / sl_distance > 1.

| R:R | Target Mult | Est WR | EV per Trade | Regime Fit |
|-----|------------|--------|-------------|------------|
| 1:1 (current) | 1.5× ATR | 68% | +0.36R | All regimes |
| 1.5:1 | 2.25× ATR | 58% | +0.45R | risk_on best |
| 2:1 | 3.0× ATR | 50% | +0.50R | risk_on only |
| 2.5:1 | 3.75× ATR | 44% | +0.54R | Strong trends |

### 2.4 Sharpe Ratio Impact

The Sharpe ratio improves with higher R:R even at lower WR because the payoff distribution becomes more asymmetric:

```
Sharpe ≈ (EV per trade) / (StdDev of returns)
```

With 1:1 R:R: returns cluster around ±1.84%, standard deviation ~1.84%
With 2:1 R:R: wins spread to +3.68%, losses at -1.84%, creating a positively skewed distribution

**A positively skewed return distribution produces a higher CAGR for the same arithmetic EV** due to compounding effects.

### 2.5 Recommendation: R:R

**Primary recommendation:** Move to **1.5:1 R:R** (target at 2.25 ATR, stop at 1.5 ATR).
- Expected WR drop from 68% → ~55-58%
- Expected EV increase from +0.36R → ~+0.40 to +0.45R
- Better Sharpe ratio due to positive skew
- Better suited for risk_on regime; keep 1:1 for risk_off

**Secondary (regime-dependent):**
- risk_on: 1.5:1 or 2:1
- neutral: 1.5:1
- risk_off: 1:1 (keep current)

| Regime | Current R:R | Proposed R:R | Rationale |
|--------|------------|-------------|-----------|
| risk_on | 1:1 | 1.5:1 | Strong trends favor wider targets |
| neutral | 1:1 | 1.5:1 | Moderate — slight widening |
| risk_off | 1:1 | 1:1 | High volatility, keep tight |

---

## 3. Position Sizing Analysis

### 3.1 Current State

**No position sizing exists.** The backtest computes:
```python
total_return = sum(r["return_pct"] for r in rows)
```

This is equivalent to betting **1 unit of capital per trade** with no scaling, no compounding, no risk management. It is not a real P&L.

**Problems:**
1. A trade in HDFC (₹1,600/share) gets same weight as a trade in a ₹50 stock
2. No compounding — returns don't grow with account size
3. No risk control — every trade risks the same absolute percentage
4. Cannot compute meaningful Sharpe ratio, drawdown, or CAGR

### 3.2 Position Sizing Methods Evaluated

#### Method 1: Fixed Fractional (Recommended)

**Formula:**
```
Position Size (₹) = (Account × Risk%) / (Entry - Stoploss)
Shares = Position Size / Entry Price
```

**Example with ₹5,00,000 capital, 2% risk:**
- Entry: ₹200, Stop: ₹194 (1.5 ATR ≈ 3%)
- Risk per share: ₹6
- Position value: (₹5,00,000 × 2%) / 6 × 200 = ₹10,000 / 6 × 200 = 333 shares × 200 = ₹66,667
- Or more directly: (₹5,00,000 × 0.02) / (₹200 - ₹194) = 1,666 shares → but capped by capital
- Actually: Risk ₹ = 5,00,000 × 0.02 = ₹10,000. Risk per share = ₹6. Shares = 10,000/6 = 1,666. Position = 1,666 × ₹200 = ₹333,333. This exceeds 100% of capital if the stop is tight!

**Proper formula:**
```
RiskAmount = Capital × RiskPercent
PositionValue = min(RiskAmount / (Entry - Stop) × Entry, Capital × MaxPositionPercent)
```

For our system (ATR-based stops of ~3-5%):
- 2% risk with 4% stop = 50% position → reasonable
- 1% risk with 4% stop = 25% position → conservative
- 0.5% risk with 4% stop = 12.5% position → very conservative

#### Method 2: Kelly Criterion

**Formula:** f* = (bp - q) / b

For current system (68% WR, 1:1 R:R):
```
f* = (1 × 0.68 - 0.32) / 1 = 0.36 = 36%
```
This means betting 36% of capital per trade for maximum growth. **Catastrophically dangerous.**

**Half-Kelly:** 18% — still very aggressive.
**Quarter-Kelly:** 9% — more reasonable.

For proposed system (58% WR, 1.5:1 R:R):
```
f* = (1.5 × 0.58 - 0.42) / 1.5 = (0.87 - 0.42) / 1.5 = 0.30 = 30%
```
Still too aggressive.

**Verdict:** Full Kelly is dangerous for swing trading. Even Half-Kelly (15-18%) implies risking ₹75K-₹90K per trade on a ₹5L account, which is psychologically impossible and practically dangerous.

#### Method 3: Volatility-Adjusted (ATR-based)

**Formula:**
```
PositionValue = Capital × (1 / ATR%) × VolatilityTarget
```
Where ATR% = ATR / Price × 100, VolatilityTarget = 0.5-1.0 (tunable).

This naturally sizes down when volatility is high and sizes up when volatility is low. Works well with our ATR-based stops.

#### Method 4: Equal Risk (Simplest)

**Formula:**
```
Risk per trade = Capital / (MaxPositions × 2)
```
For 5 positions, ₹5L capital: Risk per trade = ₹50,000.

### 3.3 Recommended Approach

**Primary: Fixed Fractional** — the standard for systematic equity trading.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Method | Fixed Fractional | Simple, proven, scalable |
| Risk per trade | 1.0% of capital | Conservative enough for 5-7 concurrent positions (5% total at risk) |
| Max position | 25% of capital | Prevents over-concentration |
| Max positions | 5-7 | Aligns with current top_n=5 |

**Secondary: Volatility overlay** (future enhancement):
Scale position size inversely to ATR% for smoother risk per trade.

### 3.4 Impact on Backtest Metrics

**With proper position sizing, the backtest would track:**
- Starting capital: ₹5,00,000 (configurable)
- Per trade: compute shares = (Capital × 1%) / (Entry - Stop)
- Track P&L in ₹ (not %)
- Track portfolio equity curve
- Compute: CAGR, Sharpe, Max DD, Calmar, Profit Factor

---

## 4. NSE Trading Charges Analysis

### 4.1 Complete Charge Breakdown (Equity Delivery — FY 2026-27)

Based on multiple verified sources (Zerodha official, StockCalc, KnowYourBrokerage, Downstox):

| Charge | Rate | Applied On | Example (₹1L trade) |
|--------|------|-----------|-------------------|
| **Brokerage** | ₹0 (Zerodha/Dhan/Fyers/Angel) | Per order | ₹0 |
| **STT — Buy** | 0.1% | Buy value | ₹100 |
| **STT — Sell** | 0.1% | Sell value | ₹110 (assuming +10% gain) |
| **Exchange (NSE)** | 0.00307% | Turnover (Buy+Sell) | ~₹6 |
| **GST** | 18% | Brokerage + Exchange + SEBI | ~₹1 |
| **SEBI Fees** | ₹10 / crore | Turnover | ~₹0.20 |
| **Stamp Duty** | 0.015% | Buy value | ₹15 |
| **DP Charges** | ₹13.5 + GST | Per scrip on sell | ~₹16 |
| **Total** | | | **~₹248** |

**As percentage of buy value (₹1,00,000): ~0.25% round-trip**

### 4.2 Cost Sensitivity by Trade Size

| Trade Value | Total Charges | % of Value | Notes |
|------------|--------------|-----------|-------|
| ₹20,000 | ~₹76 | 0.38% | DP charges dominate |
| ₹50,000 | ~₹148 | 0.30% | |
| ₹1,00,000 | ~₹248 | 0.25% | Typical |
| ₹5,00,000 | ~₹1,048 | 0.21% | | 
| ₹10,00,000 | ~₹2,048 | 0.20% | Economies of scale |

**Key insight:** The DP charge (₹13.5 + GST) is a fixed cost per scrip on sell. For small trades, this is significant. For trades above ₹50K, the percentage stabilizes around 0.20-0.25%.

### 4.3 Comparison Across Brokers

| Broker | Delivery Brokerage | AMC | Notes |
|--------|------------------|-----|-------|
| Zerodha | ₹0 | ₹300/yr | Most popular |
| Angel One | ₹0 | ₹0 | No AMC |
| Groww | ₹20 or 0.05% | ₹0 | Has a charge |
| Upstox | ₹20 or 0.1% | ₹0 | Has a charge |
| Dhan | ₹0 | ₹0 | Newer entrant |
| Fyers | ₹0 | ₹0 | No AMC |

**If trading through Zerodha/Dhan/Fyers/Angel:** Effective cost = **0.20-0.25% round-trip** (mostly STT + stamp duty + DP charges).

### 4.4 Impact on System Returns

**Before charges (current backtest):**
- Avg win: +1.84%
- Avg loss: -1.84%
- Net EV: +0.36R

**After charges (0.25% round-trip):**
- Avg win net: +1.84% - 0.25% = +1.59%
- Avg loss net: -1.84% - 0.25% = -2.09%
- Net EV: (0.68 × 1.59) - (0.32 × 2.09) = 1.08 - 0.67 = **+0.41% per trade**
- Vs. previous: (0.68 × 1.84) - (0.32 × 1.84) = **+0.66% per trade**

**Charges reduce net EV by ~38%.** This is meaningful and must be modeled.

### 4.5 Recommendation: Charges

1. **Model total round-trip charges as 0.25% of buy value** for equity delivery trades
2. Deduct from each trade's return in the backtest
3. Flag in reports: "Net of estimated trading costs (STT, DP, exchange, GST)"
4. Re-run baseline to get true net performance

---

## 5. Integrated Recommendations

### 5.1 Summary of Changes

| # | Change | Current | Proposed | Priority | Effort |
|---|--------|---------|----------|----------|--------|
| 1 | **Position sizing in backtest** | Sum of % returns | Fixed fractional (1% risk/trade) | P1 | Medium |
| 2 | **Trading cost deduction** | None | -0.25% per round-trip | P1 | Small |
| 3 | **R:R ratio adjustment** | Fixed 1:1 | 1.5:1 default, regime-dependent | P2 | Small |
| 4 | **Portfolio metrics** | WR, avg ret only | CAGR, Sharpe, Max DD, Calmar | P2 | Medium |
| 5 | **Position sizing in screener** | None | Report ₹ amount per trade | P3 | Medium |

### 5.2 Implementation Order

```
Phase 1 (P1 — Next Sprint):
  ├── Add capital parameter to backtest.py (--capital ₹500000)
  ├── Implement Fixed Fractional position sizing
  ├── Track equity curve, compute CAGR, Sharpe, Max DD
  ├── Add 0.25% trading cost deduction per round-trip
  └── Re-run baseline → compare old vs new metrics

Phase 2 (P2 — Next+1):
  ├── Make R:R regime-dependent (risk_on=1.5:1, neutral=1.5:1, risk_off=1:1)
  ├── Adjust screener.py to accept R:R parameter
  ├── Update backtest.py to handle variable R:R
  ├── Update reporter.py to show net-of-costs metrics
  └── Re-run baseline with new R:R

Phase 3 (P3 — Future):
  ├── Report ₹ position sizes in swing_picks report
  ├── Volatility-adjusted sizing overlay (optional)
  ├── Risk-of-ruin computation
  └── Correlation-aware portfolio limits
```

### 5.3 Expected Impact on Metrics

| Metric | Before (Current) | After Phase 1 | After Phase 2 |
|--------|-----------------|---------------|---------------|
| Win Rate | 68% | 68% (same) | ~55-58% |
| Avg Return/trade | +1.84% | +1.59% (net of costs) | ~+2.4% gross / +2.1% net |
| Total Return (15 dates) | +91.96% | ~+79% (net of costs) | ~+85-95% |
| Sharpe Ratio | N/A | ~0.8-1.2 | ~1.0-1.5 |
| Max Drawdown | N/A | ~8-12% | ~6-10% |
| Realism | Low | Medium-High | High |

### 5.4 Risk Considerations

| Risk | Mitigation |
|------|-----------|
| **Changing R:R reduces WR below breakeven** | Keep 1:1 as fallback for risk_off; validate with backtest first |
| **Position sizing increases drawdown** | Start with 0.5% risk/trade, validate, then increase to 1% |
| **Trading costs vary by broker** | Parameterize as configurable; default to 0.25% |
| **Small trade sizes > charges ratio** | Add minimum trade filter (e.g., skip if charges > 20% of expected return) |

---

## 6. Implementation Plan

### Step 1: Backtest Capital & Position Sizing (P1)

**Files to modify:** `backtest.py`, `baseline.py`

**Changes:**
1. Add `--capital` parameter to backtest.py (default ₹5,00,000)
2. Add `--risk-per-trade` parameter (default 1.0%)
3. Implement position sizing in `check_forward` or a new wrapper:
   ```python
   def compute_position(capital, risk_pct, entry, stop):
       risk_amount = capital * (risk_pct / 100)
       risk_per_share = abs(entry - stop)
       shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
       position_value = shares * entry
       return min(position_value, capital * 0.25)  # cap at 25% of capital
   ```
4. Replace percentage-sum with P&L tracking:
   ```python
   # Per trade P&L
   pnl = shares * (exit_price - entry_price)
   # Deduct costs
   costs = entry_price * shares * 0.0025  # 0.25% round-trip
   net_pnl = pnl - costs
   # Update capital
   capital += net_pnl
   ```
5. Track equity curve array → compute CAGR, Sharpe, Max DD

### Step 2: Trading Costs (P1)

**Files to modify:** `backtest.py`, `baseline.py`

**Changes:**
1. Add `--cost-model` parameter (default: 0.25%)
2. Deduct from each trade before compounding capital
3. Show "Gross Return" vs "Net Return (after charges)" in reports

### Step 3: Regime-Dependent R:R (P2)

**Files to modify:** `screener.py`, `backtest.py`, `factors.py`

**Changes:**
1. In `screener.py`, accept `rr_ratio` parameter:
   ```python
   def run(top_n=5, weights=None, sector_cap=2, as_of_date=None, rr_ratio=1.5):
       ...
       target_price = entry_price + (rr_ratio * 1.5 * atr_val)
       stoploss = entry_price - (1.5 * atr_val)
   ```
   Note: ATR multiplier for stoploss stays at 1.5. Only target changes.
   
2. In `backtest.py`, pass R:R from regime:
   ```python
   rr_map = {"risk_on": 1.5, "neutral": 1.5, "risk_off": 1.0}
   rr_ratio = rr_map.get(regime_label, 1.5)
   ```

### 6.1 Key Code Changes Summary

```
scripts/screener.py:
  - Add rr_ratio parameter to run()
  - Change target_price calculation: entry + (rr_ratio * 1.5 * atr)
  - Keep stoploss unchanged: entry - (1.5 * atr)

scripts/backtest.py:
  - Add --capital and --risk-per-trade parameters
  - Add --cost-model parameter (default 0.25%)
  - Implement position sizing function
  - Replace percentage-sum with P&L + equity curve tracking
  - Add CAGR, Sharpe, Max DD to report
  - Make R:R regime-dependent

scripts/baseline.py:
  - Pass capital, risk parameters
  - Update baseline comment to show net metrics
  - Re-run and compare

scripts/reporter.py:
  - Update header to show current R:R
  - Show net-of-costs returns if available
```

---

## 7. References

### R:R Ratio
- Olox India, "Swing Trading Guide 2025" — recommends 1:2 minimum
- CashSutra, "Swing Trading Stocks 2026 Framework" — recommends 1:3 for 2026 markets
- Rupeepath, "Swing Trading Strategies India (2026)" — 1:2 ideal target, breakeven WR table
- Finovatives, "Risk-Reward Ratio: Master Profitable Indian Trading" — 1:1.5 minimum
- MomentumIQ, "Risk-Reward Ratio Explained — NSE Trading Guide" — breakeven analysis

### Position Sizing
- Yieldova, "Position Sizing: Kelly Criterion and Fixed Fractional" — comparison of methods
- The Trading Dojo, "Fixed Fractional vs Kelly Criterion" — recommended Half-Kelly
- Ryan O'Connell, "Kelly Criterion: Optimal Position Sizing" — fractional Kelly guidance
- TrendsAndBreakouts, "Position Sizing Methods: Fixed Fractional, ATR, Kelly" — regime-aware sizing

### NSE Trading Charges (2026)
- Zerodha official charges page (zerodha.com/charges) — verified rates
- StockCalc.in, "Zerodha Brokerage Charges 2026" — ₹0 delivery, STT 0.1%, DP ₹13.5
- KnowYourBrokerage.in — Zerodha brokerage calculator with all charges
- Downstox, "Zerodha Brokerage Calculator 2026" — ₹242.77 total on ₹1L trade
- Zerodha Market Intel Bulletin — STT revision effective April 2026

---

## Appendix A: Detailed Numerical Examples

### A.1 Current System (1:1 R:R, no costs, no sizing)

| Trade | Entry | Stop | Target | Result | Return | Capital Impact |
|-------|-------|------|--------|--------|--------|---------------|
| 1 | ₹200 | ₹194 | ₹206 | WIN | +3.0% | +3.0% (1 unit) |
| 2 | ₹500 | ₹485 | ₹515 | LOSS | -3.0% | -3.0% (1 unit) |
| **Total** | | | | | **0.0%** | **0.0%** |

### A.2 Proposed System (1.5:1 R:R, 0.25% costs, 1% risk sizing)

**Setup: Capital = ₹5,00,000, Risk = 1%, Position Size = RiskAmount / (Entry - Stop)**

| Trade | Entry | Stop | Target | Shares | Cost | Result | P&L Net | Capital |
|-------|-------|------|--------|--------|------|--------|---------|---------|
| Start | | | | | | | | ₹5,00,000 |
| 1 | ₹200 | ₹194 | ₹209 | 833 | ₹416 | WIN | +₹7,084 | ₹5,07,084 |
| 2 | ₹500 | ₹485 | ₹522.5 | 338 | ₹422 | LOSS | -₹5,572 | ₹5,01,512 |
| 3 | ₹150 | ₹145.5 | ₹156.75 | 1,111 | ₹416 | WIN | +₹6,948 | ₹5,08,460 |

**Notes:**
- Shares = floor(₹5,000 / ₹6) = 833 for trade 1 (₹5,000 risk, ₹6/share risk)
- cost = entry × shares × 0.0025 (0.25% round-trip estimate)
- Net P&L = shares × (exit - entry) - cost
- Capital compounds naturally

### A.3 Costs as a Function of Trade Size

For a trade with +3% gross return:

| Trade Value | Gross P&L | Total Charges | Net P&L | Effective Drag |
|------------|-----------|--------------|---------|---------------|
| ₹10,000 | +₹300 | ~₹63 | +₹237 | -21.0% of gross |
| ₹50,000 | +₹1,500 | ~₹148 | +₹1,352 | -9.9% |
| ₹1,00,000 | +₹3,000 | ~₹248 | +₹2,752 | -8.3% |
| ₹5,00,000 | +₹15,000 | ~₹1,048 | +₹13,952 | -7.0% |

**Takeaway:** The DP charge fixed-cost component makes small trades disproportionately expensive. For trades under ₹50K, costs can eat 10-20%+ of gross profits.

---

## Appendix B: Quick Reference — Formula Summary

### Position Sizing (Fixed Fractional)

```
RiskAmount      = Capital × RiskPercent
RiskPerShare    = EntryPrice - StopPrice
Shares          = floor(RiskAmount / RiskPerShare)
PositionValue   = Shares × EntryPrice
PositionValue   = min(PositionValue, Capital × MaxPosPct)  # cap
```

### Kelly Criterion

```
f* = (b × p - q) / b
where:
  b = payoff ratio (target_distance / stop_distance)
  p = win rate
  q = 1 - p (loss rate)
```

### Trading Costs (Equity Delivery, per round-trip)

```
TotalCost = STT + Exchange + GST + SEBI + StampDuty + DP
STT       = 0.001 × (BuyValue + SellValue)
Exchange  = 0.0000307 × (BuyValue + SellValue)
GST       = 0.18 × (Brokerage + Exchange + SEBI)
SEBI      = 10 × Turnover / 10000000
StampDuty = 0.00015 × BuyValue
DP        = 13.5 × 1.18  (fixed, per scrip on sell)
```

**Simplified model:** TotalCost ≈ 0.0025 × BuyValue (for trades > ₹50,000)
**Conservative model:** TotalCost ≈ 0.0030 × BuyValue (includes slippage buffer)
