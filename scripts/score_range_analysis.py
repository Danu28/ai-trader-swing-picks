"""
Score Range Win Rate Analysis
==============================
Runs backtest simulation across 10 diverse dates, groups trades by
composite score buckets, and computes win rate / avg return per bucket.

Usage: python scripts/score_range_analysis.py
Output: output/score_range_analysis.csv
"""

import sqlite3
import os
import sys
import csv
from datetime import datetime

# Add scripts dir to path so we can import backtest.check_forward
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import check_forward, DB_PATH, OUTPUT_DIR

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATES = [
    "2024-06-15",
    "2024-12-15",
    "2025-01-15",
    "2025-05-15",
    "2025-08-15",
    "2025-10-15",
    "2026-02-15",
    "2026-04-01",
    "2026-06-19",
    "2026-03-16",
]

TOP_N = 10
SECTOR_CAP = 2

REGIME_WEIGHTS = {
    "risk_on":  {"momentum": 0.35, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.15},
    "neutral":  {"momentum": 0.30, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.20},
    "risk_off": {"momentum": 0.20, "trend_quality": 0.20, "mean_reversion": 0.25, "quality": 0.35},
}

SCORE_BUCKETS = [
    (55, 60),
    (60, 65),
    (65, 70),
    (70, 75),
    (75, 80),
    (80, 101),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_regime(conn, as_of_date):
    row = conn.execute(
        "SELECT regime FROM market_regime WHERE date = ?", (as_of_date,)
    ).fetchone()
    if row and row[0]:
        return row[0]
    conn.close()
    sys.exit(f"ERROR: No regime data for {as_of_date}. Run factors first.")


def compute_atr(conn, symbol, period=14, as_of_date=None):
    import pandas as pd
    import numpy as np

    df = pd.read_sql_query(
        "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT ?",
        conn, params=(symbol, as_of_date, period + 5)
    )
    if len(df) < period:
        return 0.0

    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df = df.sort_values('date')

    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift(1))
    tr3 = abs(df['low'] - df['close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    val = atr.iloc[-1]
    return float(val) if np.isfinite(val) else 0.0


def get_current_price(conn, symbol, as_of_date=None):
    row = conn.execute(
        "SELECT close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (symbol, as_of_date)
    ).fetchone()
    return float(row[0]) if row else 0.0


def compute_composite(row, weights):
    """Compute composite score from factor_scores row using screener.py formula."""
    (symbol, date, mp, mv, rs, ta, ms, pb, rsi, liq, vol, sector, universe) = row
    mp = mp or 0; mv = mv or 0; rs = rs or 0
    ta = ta or 0; ms = ms or 0; pb = pb or 0
    rsi = rsi or 0; liq = liq or 0; vol = vol or 0

    momentum_cat = (mp + mv + rs) / 3.0
    trend_cat = (ta + ms) / 2.0
    mean_rev_cat = (pb + rsi) / 2.0
    quality_cat = (liq + vol) / 2.0

    return (
        weights["momentum"] * momentum_cat
        + weights["trend_quality"] * trend_cat
        + weights["mean_reversion"] * mean_rev_cat
        + weights["quality"] * quality_cat
    )


def bucket_key(score):
    for lo, hi in SCORE_BUCKETS:
        if lo <= score < hi:
            return f"{lo}-{hi - 1}" if hi <= 100 else f"{lo}+"
    # Below 55
    return "below-55"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    conn = sqlite3.connect(DB_PATH)

    all_trades = []

    for as_of_date in DATES:
        regime = get_regime(conn, as_of_date)
        weights = REGIME_WEIGHTS[regime]
        print(f"\n{'='*70}")
        print(f"  DATE: {as_of_date}  |  REGIME: {regime.upper()}")
        print(f"{'='*70}")

        # 1. Fetch factor scores for this date
        rows = conn.execute('''
            SELECT f.symbol, f.date,
                   f.momentum_price, f.momentum_vol, f.rs_momentum,
                   f.trend_adx, f.ma_structure, f.pullback, f.rsi,
                   f.liquidity, f.volatility,
                   s.sector, s.universe_slug
            FROM factor_scores f
            JOIN stocks s ON f.symbol = s.symbol
            WHERE f.date = ?
        ''', (as_of_date,)).fetchall()

        if not rows:
            print("  WARNING: No factor_scores found — skipping.")
            continue

        # 2. Compute composite, filter, rank
        stocks_data = []
        for r in rows:
            liq = r[9] or 0
            vol = r[10] or 0
            if liq < 25:
                continue
            if vol > 85:
                continue
            comp = compute_composite(r, weights)
            stocks_data.append({
                "symbol": r[0],
                "sector": r[11] or "Unknown",
                "composite": comp,
            })

        stocks_data.sort(key=lambda x: x["composite"], reverse=True)

        # Sector cap + top-N
        ranked = []
        sector_counts = {}
        for s in stocks_data:
            sec = s["sector"]
            cnt = sector_counts.get(sec, 0)
            if cnt >= SECTOR_CAP:
                continue
            s["rank"] = len(ranked) + 1
            ranked.append(s)
            sector_counts[sec] = cnt + 1
            if len(ranked) >= TOP_N:
                break

        if not ranked:
            print("  WARNING: No picks after filtering — skipping.")
            continue

        # 3. Compute entry/target/SL and run check_forward
        for s in ranked:
            symbol = s["symbol"]
            price = get_current_price(conn, symbol, as_of_date=as_of_date)
            atr_val = compute_atr(conn, symbol, as_of_date=as_of_date)

            entry_price = price
            target_price = entry_price + (1.5 * atr_val) if atr_val > 0 else entry_price * 1.04
            stoploss = entry_price - (1.5 * atr_val) if atr_val > 0 else entry_price * 0.96

            result, detail, stats = check_forward(
                conn, symbol, as_of_date, entry_price, target_price, stoploss
            )

            if result == "WIN":
                return_pct = round(
                    (target_price - entry_price) / entry_price * 100, 2
                )
            elif result == "LOSS":
                return_pct = round(
                    (stoploss - entry_price) / entry_price * 100, 2
                )
            else:
                return_pct = round(
                    (stats["end_close"] - entry_price) / entry_price * 100, 2
                )

            composite_score = round(s["composite"], 1)

            trade = {
                "date": as_of_date,
                "regime": regime,
                "rank": s["rank"],
                "symbol": s["symbol"],
                "sector": s["sector"],
                "composite_score": composite_score,
                "result": result,
                "return_pct": return_pct,
                "entry_filled": stats["entry_filled"],
                "detail": detail,
            }
            all_trades.append(trade)

            status_icon = {"WIN": "+", "LOSS": "-", "DRAW": "~"}.get(result, "?")
            print(
                f"  #{s['rank']:>2}  {symbol:<16}  comp={composite_score:>5.1f}  "
                f"{result:<4}  {return_pct:>+7.2f}%  "
                f"{'filled' if stats['entry_filled'] else 'unfilled'}"
            )

    conn.close()

    # -----------------------------------------------------------------------
    # 4. Group by score buckets
    # -----------------------------------------------------------------------
    buckets = {}
    bucket_order = []
    for lo, hi in SCORE_BUCKETS:
        label = f"{lo}-{hi - 1}" if hi <= 100 else f"{lo}+"
        buckets[label] = []
        bucket_order.append(label)

    # Extra bucket for below-55
    buckets["below-55"] = []
    bucket_order.insert(0, "below-55")

    for t in all_trades:
        bk = bucket_key(t["composite_score"])
        if bk in buckets:
            buckets[bk].append(t)
        else:
            buckets["below-55"].append(t)

    # -----------------------------------------------------------------------
    # 5. Compute per-bucket stats
    # -----------------------------------------------------------------------
    print(f"\n\n{'='*80}")
    print(f"  SCORE RANGE ANALYSIS — {len(all_trades)} trades across {len(DATES)} dates")
    print(f"{'='*80}")

    header = f"  {'Score Range':<12} {'Trades':>6} {'Win Rate':>9} {'Avg Return':>10} {'Total Ret':>10}"
    print(header)
    print(f"  {'-'*12} {'-'*6} {'-'*9} {'-'*10} {'-'*10}")

    summary_rows = []
    for bk in bucket_order:
        trades = buckets[bk]
        if not trades:
            continue
        n = len(trades)
        wins = sum(1 for t in trades if t["result"] == "WIN")
        wr = wins / n * 100
        avg_ret = sum(t["return_pct"] for t in trades) / n
        total_ret = sum(t["return_pct"] for t in trades)
        summary_rows.append((bk, n, wr, avg_ret, total_ret))
        print(
            f"  {bk:<12} {n:>6} {wr:>8.1f}% {avg_ret:>+9.2f}% {total_ret:>+9.2f}%"
        )

    # -----------------------------------------------------------------------
    # 6. Analysis
    # -----------------------------------------------------------------------
    print(f"\n{'='*80}")
    print(f"  ANALYSIS")
    print(f"{'='*80}")

    # Find threshold for 60%+ win rate
    threshold_60 = None
    for bk, n, wr, avg, total in summary_rows:
        if wr >= 60:
            threshold_60 = int(bk.split("-")[0])
            break

    if threshold_60:
        print(f"\n  >> Min score for 60%+ win rate: {threshold_60}")
    else:
        print(f"\n  >> No bucket reaches 60% win rate.")

    # Find threshold for positive avg return
    threshold_pos = None
    for bk, n, wr, avg, total in summary_rows:
        if avg > 0:
            threshold_pos = int(bk.split("-")[0])
            break

    if threshold_pos:
        print(f"  >> Min score for positive avg return: {threshold_pos}")
    else:
        print(f"  >> No bucket has positive avg return.")

    # Sweet spot (highest avg return)
    best_bucket = max(summary_rows, key=lambda r: r[3])
    print(f"  >> Best bucket (highest avg return): {best_bucket[0]} ({best_bucket[3]:+.2f}%, {best_bucket[1]} trades, {best_bucket[2]:.0f}% WR)")

    # Summary: are higher scores always better?
    if len(summary_rows) >= 2:
        wr_vals = [r[2] for r in summary_rows]
        avg_vals = [r[3] for r in summary_rows]
        if all(wr_vals[i] <= wr_vals[i+1] for i in range(len(wr_vals)-1)):
            print(f"  >> Win rate monotonically increases with score — higher = better.")
        else:
            print(f"  >> Win rate does NOT monotonically increase — there may be a sweet spot.")

    # -----------------------------------------------------------------------
    # 7. Save CSV
    # -----------------------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, "score_range_analysis.csv")
    fieldnames = [
        "date", "regime", "rank", "symbol", "sector",
        "composite_score", "result", "return_pct", "entry_filled", "detail"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_trades)

    print(f"\n  Raw data saved to: {csv_path}")
    print(f"  Total trades analyzed: {len(all_trades)}")


if __name__ == "__main__":
    main()
