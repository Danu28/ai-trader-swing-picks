#!/usr/bin/env python3
"""
Analyze the impact of the composite score threshold (>=70).

Queries factor_scores + daily_ohlcv directly. Does NOT run the full pipeline.
For each baseline date:
  1. Get all stocks with factor scores
  2. Apply screener filters (liquidity>25, vol<85, 21d return>-15%)
  3. Compute composite using regime-appropriate weights
  4. Rank stocks
  5. For each stock, check forward performance (target=entry+1.5ATR, SL=entry-1.5ATR)
  6. Group by score band

Outputs a concise research summary.
"""

import sqlite3
import os
import sys
from datetime import datetime

import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'market_data.db')

BASELINE_DATES = [
    "2024-02-15",  # risk_on
    "2024-08-15",  # risk_on
    "2025-05-15",  # risk_on
    "2026-04-06",  # risk_off
    "2024-04-15",  # neutral
    "2024-10-15",  # neutral
    "2025-08-15",  # neutral
    "2025-11-15",  # neutral
    "2026-01-20",  # risk_off
    "2025-01-15",  # risk_off
    "2026-03-09",  # risk_off
    "2026-03-16",  # risk_off
    "2026-03-23",  # risk_off
    "2026-03-30",  # risk_off
    "2026-06-08",  # risk_off
]

# Regime info for baseline dates (from market_regime table)
REGIME_MAP = {
    "2024-02-15": "risk_on",
    "2024-08-15": "neutral",
    "2025-05-15": "risk_on",
    "2026-04-06": "risk_off",
    "2024-04-15": "neutral",
    "2024-10-15": "neutral",
    "2025-08-15": "neutral",
    "2025-11-15": "risk_on",
    "2026-01-20": "risk_off",
    "2025-01-15": "risk_off",
    "2026-03-09": "risk_off",
    "2026-03-16": "risk_off",
    "2026-03-23": "risk_off",
    "2026-03-30": "risk_off",
    "2026-06-08": "risk_off",
}

# From screener.py
DEFAULT_WEIGHTS = {"momentum": 0.30, "trend_quality": 0.25, "mean_reversion": 0.30, "quality": 0.15}

def auto_weights(regime_label):
    if regime_label == "risk_off":
        return {"momentum": 0.20, "trend_quality": 0.20, "mean_reversion": 0.35, "quality": 0.25}
    elif regime_label == "neutral":
        return {"momentum": 0.25, "trend_quality": 0.25, "mean_reversion": 0.30, "quality": 0.20}
    else:
        return {"momentum": 0.45, "trend_quality": 0.25, "mean_reversion": 0.15, "quality": 0.15}

def compute_atr(prices_df, period=14):
    """Compute ATR from a DataFrame with high/low/close columns, sorted by date."""
    if len(prices_df) < period + 1:
        return 0
    high = prices_df['high'].astype(float).values
    low = prices_df['low'].astype(float).values
    close = prices_df['close'].astype(float).values
    tr = np.maximum(high - low, np.maximum(
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1))
    ))
    tr[0] = high[0] - low[0]
    atr = pd.Series(tr).ewm(span=period, adjust=False).mean().iloc[-1]
    return float(atr) if np.isfinite(atr) else 0

def get_21d_return(conn, symbol, as_of_date):
    """Get 21-trading-day return ending on or before as_of_date."""
    rows = conn.execute(
        "SELECT close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 21",
        (symbol, as_of_date)
    ).fetchall()
    if len(rows) >= 21:
        # Return from 21 trading days ago to now
        # The first row (index 0) is the most recent date
        close_now = float(rows[0][0])
        close_21d_ago = float(rows[20][0])
        if close_21d_ago > 0:
            return (close_now / close_21d_ago) - 1
    return None

def check_forward(conn, symbol, as_of_date, entry_price, target_price, stoploss):
    """Check forward performance, matching backtest.py check_forward logic."""
    entry_row = conn.execute(
        "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (symbol, as_of_date)
    ).fetchone()

    if not entry_row:
        return "DRAW", 0, "no_entry_data", {"end_close": 0, "end_date": as_of_date}
    
    entry_actual_date = entry_row[0]
    day_low = float(entry_row[2])
    day_high = float(entry_row[1])
    entry_filled = day_low <= entry_price <= day_high

    df_rows = conn.execute(
        "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date > ? ORDER BY date",
        (symbol, as_of_date)
    ).fetchall()

    if not df_rows:
        return "DRAW", 0, "no_forward_data", {"end_close": entry_price, "end_date": as_of_date}

    hit_target = None
    hit_stoploss = None
    end_close = float(df_rows[-1][3])
    end_date = df_rows[-1][0]

    for row in df_rows:
        dt, high, low, close = row[0], float(row[1]), float(row[2]), float(row[3])
        if hit_target is None and high >= target_price:
            hit_target = dt
        if hit_stoploss is None and low <= stoploss:
            hit_stoploss = dt
        if hit_target is not None and hit_stoploss is not None:
            break

    if hit_target and hit_stoploss:
        if hit_target <= hit_stoploss:
            result = "WIN"
        else:
            result = "LOSS"
    elif hit_target:
        result = "WIN"
    elif hit_stoploss:
        result = "LOSS"
    else:
        result = "DRAW"

    if result == "WIN":
        return_pct = (target_price - entry_price) / entry_price * 100
    elif result == "LOSS":
        return_pct = (stoploss - entry_price) / entry_price * 100
    else:
        return_pct = (end_close - entry_price) / entry_price * 100

    return result, return_pct, entry_filled, {
        "end_close": end_close, "end_date": end_date,
        "hit_target_date": hit_target, "hit_sl_date": hit_stoploss
    }

def main():
    conn = sqlite3.connect(DB_PATH)
    
    all_trades = []  # List of dicts with symbol, date, score, rank, result, return_pct

    for date_str in BASELINE_DATES:
        print(f"\n=== Processing {date_str} ===", file=sys.stderr)
        regime = REGIME_MAP.get(date_str, "unknown")
        weights = auto_weights(regime)

        # Get all factor scores for this date
        rows = conn.execute('''
            SELECT f.symbol, f.momentum_price, f.momentum_vol, f.rs_momentum,
                   f.trend_adx, f.ma_structure, f.pullback, f.rsi,
                   f.liquidity, f.volatility,
                   s.sector, s.universe_slug
            FROM factor_scores f
            JOIN stocks s ON f.symbol = s.symbol
            WHERE f.date = ?
        ''', (date_str,)).fetchall()

        if not rows:
            print(f"  No factor data for {date_str}", file=sys.stderr)
            continue

        stocks_data = []
        for r in rows:
            symbol, mp, mv, rs, ta, ms, pb, rsi, liq, vol, sector, universe = r
            mp = mp or 0; mv = mv or 0; rs = rs or 0
            ta = ta or 0; ms = ms or 0; pb = pb or 0
            rsi = rsi or 0; liq = liq or 0; vol = vol or 0

            if liq < 25: continue
            if vol > 85: continue

            # 21d return filter
            ret_21d = get_21d_return(conn, symbol, date_str)
            if ret_21d is not None and ret_21d < -0.15: continue

            momentum_cat = (mp + mv + rs) / 3.0
            trend_cat = (ta + ms) / 2.0
            mean_rev_cat = (pb + rsi) / 2.0
            quality_cat = (liq + vol) / 2.0

            composite = (
                weights["momentum"] * momentum_cat +
                weights["trend_quality"] * trend_cat +
                weights["mean_reversion"] * mean_rev_cat +
                weights["quality"] * quality_cat
            )

            stocks_data.append({
                "symbol": symbol,
                "composite": composite,
                "sector": sector or "Unknown",
                "date": date_str,
                "regime": regime,
            })

        # Sort by composite descending
        stocks_data.sort(key=lambda x: x["composite"], reverse=True)

        # Assign ranks (for tracking, no sector cap since we're analyzing broad data)
        for i, s in enumerate(stocks_data):
            s["rank"] = i + 1

        # Sector-cap: max 2 per sector (matching screener)
        sector_counts = {}
        capped_ranked = []
        for s in stocks_data:
            sec = s["sector"] or "Unknown"
            if sector_counts.get(sec, 0) >= 2:
                continue
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            capped_ranked.append(s)
            if len(capped_ranked) >= 50:  # enough for analysis
                break

        # Now get forward performance for stocks in different score ranges
        # We'll check the top 50 stocks (or all if fewer) after sector cap
        for s in capped_ranked[:50]:
            symbol = s["symbol"]
            price_row = conn.execute(
                "SELECT close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                (symbol, date_str)
            ).fetchone()
            if not price_row:
                continue

            entry_price = float(price_row[0])

            # Compute ATR
            atr_rows = conn.execute(
                "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 20",
                (symbol, date_str)
            ).fetchall()
            if len(atr_rows) >= 15:
                pdf = pd.DataFrame(atr_rows[::-1], columns=['date', 'high', 'low', 'close'])
                atr_val = compute_atr(pdf)
            else:
                atr_val = 0

            if atr_val > 0:
                target_price = entry_price + (1.5 * atr_val)
                stoploss = entry_price - (1.5 * atr_val)
            else:
                target_price = entry_price * 1.04
                stoploss = entry_price * 0.96

            result, return_pct, entry_filled, stats = check_forward(
                conn, symbol, date_str, entry_price, target_price, stoploss
            )

            all_trades.append({
                "date": date_str,
                "regime": regime,
                "rank": s["rank"],
                "symbol": symbol.replace(".NS", ""),
                "score": round(s["composite"], 1),
                "sector": s["sector"],
                "result": result,
                "return_pct": round(return_pct, 2),
                "entry_filled": entry_filled,
            })

    conn.close()

    # ========== ANALYSIS ==========
    if not all_trades:
        print("NO TRADES FOUND")
        return

    df = pd.DataFrame(all_trades)
    
    print(f"\n{'='*80}")
    print(f"  SCORE THRESHOLD ANALYSIS")
    print(f"  {len(BASELINE_DATES)} baseline dates | {len(df)} total stock-date observations")
    print(f"{'='*80}")

    # Score bands
    def score_band(score):
        if score < 60: return "<60"
        elif score < 65: return "60-65"
        elif score < 70: return "65-70"
        elif score < 75: return "70-75"
        elif score < 80: return "75-80"
        else: return "80+"

    df["band"] = df["score"].apply(score_band)

    # 1. Win rate by score band
    print(f"\n  --- Win Rate by Score Band ---")
    print(f"  {'Band':<8} {'Trades':>7} {'Wins':>5} {'Losses':>6} {'Draws':>6} {'WR':>8} {'AvgRet%':>9}")
    print(f"  {'-'*49}")
    
    band_order = ["<60", "60-65", "65-70", "70-75", "75-80", "80+"]
    for band in band_order:
        subset = df[df["band"] == band]
        if len(subset) == 0:
            continue
        wins = len(subset[subset["result"] == "WIN"])
        losses = len(subset[subset["result"] == "LOSS"])
        draws = len(subset[subset["result"] == "DRAW"])
        total = len(subset)
        wr = wins / total * 100
        avg_ret = subset["return_pct"].mean()
        print(f"  {band:<8} {total:>7} {wins:>5} {losses:>6} {draws:>6} {wr:>6.1f}% {avg_ret:>+8.2f}%")

    # Cumulative win rate (above threshold X)
    print(f"\n  --- Win Rate Above Threshold (cumulative) ---")
    print(f"  {'Threshold':<10} {'Trades':>7} {'Wins':>5} {'WR':>8} {'AvgRet%':>9}")
    print(f"  {'-'*41}")
    for threshold in [50, 55, 60, 65, 70, 75, 80]:
        subset = df[df["score"] >= threshold]
        if len(subset) == 0:
            continue
        wins = len(subset[subset["result"] == "WIN"])
        total = len(subset)
        wr = wins / total * 100
        avg_ret = subset["return_pct"].mean()
        print(f"  >= {threshold:<5} {total:>7} {wins:>5} {wr:>6.1f}% {avg_ret:>+8.2f}%")

    # 2. Trade counts at each threshold (all stocks, not just top 50)
    print(f"\n  --- Trade Counts by Threshold (top 15 after sector cap) ---")
    # Re-query for just counts
    conn2 = sqlite3.connect(DB_PATH)
    for date_str in BASELINE_DATES:
        regime = REGIME_MAP.get(date_str, "unknown")
        weights = auto_weights(regime)
        
        rows = conn2.execute('''
            SELECT f.symbol, f.liquidity, f.volatility,
                   f.momentum_price, f.momentum_vol, f.rs_momentum,
                   f.trend_adx, f.ma_structure, f.pullback, f.rsi,
                   s.sector
            FROM factor_scores f
            JOIN stocks s ON f.symbol = s.symbol
            WHERE f.date = ?
        ''', (date_str,)).fetchall()

        # Quick composite compute for all stocks
        all_stocks = []
        for r in rows:
            symbol = r[0]; liq = r[1] or 0; vol = r[2] or 0
            mp = r[3] or 0; mv = r[4] or 0; rs = r[5] or 0
            ta = r[6] or 0; ms = r[7] or 0; pb = r[8] or 0; rsi = r[9] or 0
            sector = r[10] or "Unknown"
            
            if liq < 25: continue
            if vol > 85: continue
            
            ret_21d = get_21d_return(conn2, symbol, date_str)
            if ret_21d is not None and ret_21d < -0.15: continue
            
            mc = (mp + mv + rs) / 3.0
            tc = (ta + ms) / 2.0
            mrc = (pb + rsi) / 2.0
            qc = (liq + vol) / 2.0
            comp = weights["momentum"] * mc + weights["trend_quality"] * tc + weights["mean_reversion"] * mrc + weights["quality"] * qc
            
            all_stocks.append({"symbol": symbol, "composite": comp, "sector": sector})
        
        all_stocks.sort(key=lambda x: x["composite"], reverse=True)
        
        # Apply sector cap (max 2 per sector)
        sect_c = {}
        capped = []
        for s in all_stocks:
            sec = s["sector"] or "Unknown"
            if sect_c.get(sec, 0) >= 2: continue
            sect_c[sec] = sect_c.get(sec, 0) + 1
            capped.append(s)
            if len(capped) >= 15: break
        
        if not capped: continue
        
        scores_70plus = sum(1 for s in capped if s["composite"] >= 70)
        scores_65_70 = sum(1 for s in capped if 65 <= s["composite"] < 70)
        scores_60_65 = sum(1 for s in capped if 60 <= s["composite"] < 65)
        scores_below_60 = sum(1 for s in capped if s["composite"] < 60)
        
        score5 = f"{capped[4]['composite']:.1f}" if len(capped) >= 5 else "N/A"
        print(f"  {date_str} ({regime:<8}): Top15: 70+={scores_70plus}  65-70={scores_65_70}  60-65={scores_60_65}  <60={scores_below_60}  |  #1 score={capped[0]['composite']:.1f}  #5 score={score5}")
    conn2.close()

    # 3. Opportunity cost: trades lost vs gained
    print(f"\n  --- Opportunity Cost Analysis ---")
    # Count total top-5 picks at each threshold
    for threshold in [60, 65, 70, 75]:
        picks_per_date = []
        w余地 = []
        conn3 = sqlite3.connect(DB_PATH)
        for date_str in BASELINE_DATES:
            regime = REGIME_MAP.get(date_str, "unknown")
            weights = auto_weights(regime)
            
            rows = conn3.execute('''
                SELECT f.symbol, f.liquidity, f.volatility,
                       f.momentum_price, f.momentum_vol, f.rs_momentum,
                       f.trend_adx, f.ma_structure, f.pullback, f.rsi,
                       s.sector
                FROM factor_scores f
                JOIN stocks s ON f.symbol = s.symbol
                WHERE f.date = ?
            ''', (date_str,)).fetchall()

            all_stocks = []
            for r in rows:
                symbol = r[0]; liq = r[1] or 0; vol = r[2] or 0
                mp = r[3] or 0; mv = r[4] or 0; rs = r[5] or 0
                ta = r[6] or 0; ms = r[7] or 0; pb = r[8] or 0; rsi = r[9] or 0
                sector = r[10] or "Unknown"
                if liq < 25: continue
                if vol > 85: continue
                ret_21d = get_21d_return(conn3, symbol, date_str)
                if ret_21d is not None and ret_21d < -0.15: continue
                mc = (mp + mv + rs) / 3.0
                tc = (ta + ms) / 2.0
                mrc = (pb + rsi) / 2.0
                qc = (liq + vol) / 2.0
                comp = weights["momentum"] * mc + weights["trend_quality"] * tc + weights["mean_reversion"] * mrc + weights["quality"] * qc
                all_stocks.append({"symbol": symbol, "composite": comp, "sector": sector})
            
            all_stocks.sort(key=lambda x: x["composite"], reverse=True)
            sect_c = {}
            capped = []
            for s in all_stocks:
                sec = s["sector"] or "Unknown"
                if sect_c.get(sec, 0) >= 2: continue
                sect_c[sec] = sect_c.get(sec, 0) + 1
                capped.append(s)
                if len(capped) >= 5: break
            
            # Count how many of the top 5 pass this threshold
            above = [s for s in capped if s["composite"] >= threshold]
            picks_per_date.append(len(above))
            
            # Also count how many are filtered out (in this date's top 5 but below threshold)
            # Only relevant for threshold >= 70 since that's the current one
            if threshold == 70:
                filtered = [s for s in capped if s["composite"] < threshold]
                if filtered:
                    w余地.extend([f"{s['symbol'].replace('.NS','')}({s['composite']:.1f})" for s in filtered])
        
        total_possible = 5 * len(BASELINE_DATES)
        total_actual = sum(picks_per_date)
        pct_filled = total_actual / total_possible * 100 if total_possible > 0 else 0
        avg_per_date = total_actual / len(BASELINE_DATES) if BASELINE_DATES else 0
        print(f"  Threshold >= {threshold:<2}: {total_actual}/{total_possible} picks ({pct_filled:.0f}%) | avg {avg_per_date:.1f}/5 per date")
        
        if threshold == 70:
            lost_trades = total_possible - total_actual
            print(f"    Trades lost vs no-threshold: {lost_trades}")
            if w余地:
                print(f"    Stocks filtered out (below 70 in top 5): {', '.join(w余地)}")

    conn3.close()

    # 4. Specific analysis: 2026-06-22 stocks
    print(f"\n{'='*80}")
    print(f"  SPECIFIC CHECK: 2026-06-22 Filtered Stocks")
    print(f"{'='*80}")
    
    date_str = "2026-06-22"
    regime = REGIME_MAP.get(date_str, "unknown")
    weights = auto_weights(regime)
    
    conn4 = sqlite3.connect(DB_PATH)
    
    # Get factor scores for 2026-06-22
    rows = conn4.execute('''
        SELECT f.symbol, f.momentum_price, f.momentum_vol, f.rs_momentum,
               f.trend_adx, f.ma_structure, f.pullback, f.rsi,
               f.liquidity, f.volatility,
               s.sector
        FROM factor_scores f
        JOIN stocks s ON f.symbol = s.symbol
        WHERE f.date = ?
    ''', (date_str,)).fetchall()
    
    target_symbols = ['INDUSINDBK.NS', 'GMRAIRPORT.NS', 'PAGEIND.NS', 'YESBANK.NS']
    
    print(f"\n  {'Symbol':<15} {'Score':>6} {'Entry':>8} {'Target':>8} {'SL':>8} {'Result':>8} {'Ret%':>7}")
    print(f"  {'-'*62}")
    
    for r in rows:
        symbol = r[0];  
        symbol_clean = symbol.replace('.NS', '')
        if symbol_clean not in ['INDUSINDBK', 'GMRAIRPORT', 'PAGEIND', 'YESBANK']:
            continue
        
        liq = float(r[8] or 0); vol = float(r[9] or 0)
        mp = float(r[1] or 0); mv = float(r[2] or 0); rs = float(r[3] or 0)
        ta = float(r[4] or 0); ms = float(r[5] or 0); pb = float(r[6] or 0); rsi_val = float(r[7] or 0)
        
        mc = (mp + mv + rs) / 3.0
        tc = (ta + ms) / 2.0
        mrc = (pb + rsi_val) / 2.0
        qc = (liq + vol) / 2.0
        comp = weights["momentum"] * mc + weights["trend_quality"] * tc + weights["mean_reversion"] * mrc + weights["quality"] * qc
        
        price_row = conn4.execute(
            "SELECT close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (symbol, date_str)
        ).fetchone()
        if not price_row:
            continue
        entry_price = float(price_row[0])
        
        atr_rows = conn4.execute(
            "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 20",
            (symbol, date_str)
        ).fetchall()
        if len(atr_rows) >= 15:
            pdf = pd.DataFrame(atr_rows[::-1], columns=['date', 'high', 'low', 'close'])
            atr_val = compute_atr(pdf)
        else:
            atr_val = 0
        
        if atr_val > 0:
            target_price = entry_price + (1.5 * atr_val)
            stoploss = entry_price - (1.5 * atr_val)
        else:
            target_price = entry_price * 1.04
            stoploss = entry_price * 0.96
        
        result, return_pct, ef, stats = check_forward(
            conn4, symbol, date_str, entry_price, target_price, stoploss
        )
        
        print(f"  {symbol_clean:<15} {comp:>6.1f} {entry_price:>8.2f} {target_price:>8.2f} {stoploss:>8.2f} {result:>8} {return_pct:>+6.2f}%")
    
    conn4.close()
    
    # 5. Broader analysis: what's the WR for stocks ranked 6-10 and 11-15?
    print(f"\n{'='*80}")
    print(f"  BACKFILL: Stocks outside Top 5 by rank")
    print(f"{'='*80}")
    
    # Use the all_trades data
    for rank_range, label in [((1,5), "Top 5"), ((6,10), "Ranks 6-10"), ((11,15), "Ranks 11-15"), ((16,20), "Ranks 16-20")]:
        subset = df[(df["rank"] >= rank_range[0]) & (df["rank"] <= rank_range[1])]
        if len(subset) == 0:
            continue
        wins = len(subset[subset["result"] == "WIN"])
        losses = len(subset[subset["result"] == "LOSS"])
        draws = len(subset[subset["result"] == "DRAW"])
        total = len(subset)
        wr = wins / total * 100 if total > 0 else 0
        avg_ret = subset["return_pct"].mean()
        print(f"  {label:<15}: {total:>4} trades, {wins:>3}W/{losses:>3}L/{draws:>3}D, WR={wr:>5.1f}%, AvgRet={avg_ret:>+6.2f}%")
    
    # 6. Optimal threshold: at what score does WR cross 50%?
    print(f"\n  --- WR by Score Bucket (5-point buckets) ---")
    for lo in range(50, 85, 5):
        hi = lo + 5
        subset = df[(df["score"] >= lo) & (df["score"] < hi)]
        if len(subset) == 0:
            continue
        wins = len(subset[subset["result"] == "WIN"])
        total = len(subset)
        wr = wins / total * 100 if total > 0 else 0
        avg_ret = subset["return_pct"].mean()
        print(f"  {lo}-{hi}: {total:>4} trades, WR={wr:>5.1f}%, AvgRet={avg_ret:>+6.2f}%")
    
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    
    # Compare: current baseline (top 5, score >= 70) vs what-if (top 5, score >= 60 or no threshold)
    baseline_subset = df[(df["rank"] <= 5) & (df["score"] >= 70)]
    baseline_wins = len(baseline_subset[baseline_subset["result"] == "WIN"])
    baseline_total = len(baseline_subset)
    baseline_wr = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0
    baseline_avg_ret = baseline_subset["return_pct"].mean()
    print(f"\n  Current (top 5, >=70): {baseline_total} trades, WR={baseline_wr:.1f}%, AvgRet={baseline_avg_ret:+.2f}%")
    
    relaxed_subset = df[(df["rank"] <= 5) & (df["score"] >= 60)]
    relaxed_wins = len(relaxed_subset[relaxed_subset["result"] == "WIN"])
    relaxed_total = len(relaxed_subset)
    relaxed_wr = relaxed_wins / relaxed_total * 100 if relaxed_total > 0 else 0
    relaxed_avg_ret = relaxed_subset["return_pct"].mean()
    print(f"  Relaxed (top 5, >=60): {relaxed_total} trades, WR={relaxed_wr:.1f}%, AvgRet={relaxed_avg_ret:+.2f}%")
    
    nothreshold_subset = df[df["rank"] <= 5]
    nt_wins = len(nothreshold_subset[nothreshold_subset["result"] == "WIN"])
    nt_total = len(nothreshold_subset)
    nt_wr = nt_wins / nt_total * 100 if nt_total > 0 else 0
    nt_avg_ret = nothreshold_subset["return_pct"].mean()
    print(f"  No threshold (top 5): {nt_total} trades, WR={nt_wr:.1f}%, AvgRet={nt_avg_ret:+.2f}%")

if __name__ == '__main__':
    main()
