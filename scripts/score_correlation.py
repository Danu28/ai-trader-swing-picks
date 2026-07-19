"""
score_correlation.py
Research: Does the composite score ranking predict trade outcomes?

Runs backtests across 5 dates (top 10 stocks each) and collects:
- rank, symbol, composite score, result (WIN/LOSS/DRAW), return %
- Writes raw data to output/score_correlation_raw.csv
- Computes rank-bucket statistics and prints a research report
"""
import sys
import os
import sqlite3
import csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factors import run as run_factors
from screener import run as run_screener
from backtest import check_forward

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
CSV_PATH = os.path.join(OUTPUT_DIR, 'score_correlation_raw.csv')

DATES = [
    "2025-01-15",  # risk_off
    "2025-05-15",  # risk_on
    "2025-08-15",  # neutral
    "2025-10-15",  # neutral
    "2026-04-01",  # risk_off
]

TOP_N = 10


def get_regime_weights(regime_label):
    """Return factor weights matching backtest.py logic."""
    if regime_label == "risk_off":
        return {"momentum": 0.20, "trend_quality": 0.20,
                "mean_reversion": 0.25, "quality": 0.35}
    elif regime_label == "neutral":
        return {"momentum": 0.30, "trend_quality": 0.25,
                "mean_reversion": 0.25, "quality": 0.20}
    else:
        return {"momentum": 0.35, "trend_quality": 0.25,
                "mean_reversion": 0.25, "quality": 0.15}


def collect_data():
    """Run backtests and collect all records."""
    records = []

    for as_of_date in DATES:
        print(f"\n{'='*60}")
        print(f"  Running backtest for {as_of_date}")
        print(f"{'='*60}")

        # Step 1: Compute factors
        factor_result = run_factors(as_of_date=as_of_date)
        regime = factor_result.get("regime", {})
        regime_label = regime.get("regime", "unknown")
        breadth = regime.get("breadth_ratio", "?")
        vix_proxy = regime.get("vix_proxy")
        vix_20d_avg = regime.get("vix_20d_avg")

        print(f"  Regime: {regime_label}  Breadth: {breadth}")

        # VIX spike check (matches backtest.py)
        spike_blocked = False
        if vix_proxy is not None and vix_20d_avg is not None and vix_20d_avg > 0:
            spike_ratio = vix_proxy / vix_20d_avg
            if spike_ratio > 1.5:
                print(f"  SKIPPED: Volatility spike ({spike_ratio:.2f}x)")
                spike_blocked = True

        if spike_blocked:
            continue

        # Step 2: Screen top N
        weights = get_regime_weights(regime_label)
        screen_result = run_screener(top_n=TOP_N, weights=weights,
                                      as_of_date=as_of_date)
        ranked = screen_result["ranked"]

        if not ranked:
            print("  No picks found.")
            continue

        # Step 3: Forward-check each pick
        conn = sqlite3.connect(DB_PATH)

        for s in ranked:
            result, detail, stats = check_forward(
                conn, s["symbol"], as_of_date,
                s["entry_price"], s["target_price"], s["stoploss"]
            )

            # Compute return %
            if result == "WIN":
                return_pct = round(
                    (s["target_price"] - s["entry_price"]) / s["entry_price"] * 100, 2)
            elif result == "LOSS":
                return_pct = round(
                    (s["stoploss"] - s["entry_price"]) / s["entry_price"] * 100, 2)
            else:
                return_pct = round(
                    (stats["end_close"] - s["entry_price"]) / s["entry_price"] * 100, 2)

            # Compute hold days
            try:
                entry_dt = datetime.strptime(str(stats["entry_actual_date"]), "%Y-%m-%d")
                if result == "WIN" and stats["hit_target_date"]:
                    exit_dt = datetime.strptime(str(stats["hit_target_date"]), "%Y-%m-%d")
                elif result == "LOSS" and stats["hit_sl_date"]:
                    exit_dt = datetime.strptime(str(stats["hit_sl_date"]), "%Y-%m-%d")
                else:
                    exit_dt = datetime.strptime(str(stats["end_date"]), "%Y-%m-%d")
                hold_days = (exit_dt - entry_dt).days
            except (ValueError, TypeError):
                hold_days = 0

            rec = {
                "date": as_of_date,
                "regime": regime_label,
                "breadth": breadth,
                "rank": s["rank"],
                "symbol": s["symbol"].replace(".NS", ""),
                "sector": s["sector"],
                "composite_score": round(s["composite"], 2),
                "entry_price": s["entry_price"],
                "target_price": s["target_price"],
                "stoploss": s["stoploss"],
                "result": result,
                "return_pct": return_pct,
                "hold_days": hold_days,
                "entry_filled": stats["entry_filled"],
            }
            records.append(rec)

            outcome_char = {"WIN": "W", "LOSS": "L", "DRAW": "D"}[result]
            print(f"  #{s['rank']:>2} {s['symbol'].replace('.NS',''):<12} "
                  f"Score:{s['composite']:5.1f}  {outcome_char}  {return_pct:+.2f}%")

        conn.close()

    return records


def write_csv(records):
    """Write raw data to CSV."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fieldnames = ["date", "regime", "breadth", "rank", "symbol", "sector",
                  "composite_score", "entry_price", "target_price", "stoploss",
                  "result", "return_pct", "hold_days", "entry_filled"]
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    print(f"\n  Raw data written to: {CSV_PATH}")


def analyze(records):
    """Compute rank-bucket statistics and print research report."""
    wins = [r for r in records if r["result"] == "WIN"]
    losses = [r for r in records if r["result"] == "LOSS"]

    # Bucket definitions
    buckets = {
        "1-3 (Top)": lambda r: r["rank"] <= 3,
        "4-6 (Mid)": lambda r: 4 <= r["rank"] <= 6,
        "7-10 (Low)": lambda r: 7 <= r["rank"],
    }

    def bucket_stats(bucket_name, filter_fn):
        bucket_recs = [r for r in records if filter_fn(r)]
        bucket_wins = [r for r in bucket_recs if r["result"] == "WIN"]
        n = len(bucket_recs)
        if n == 0:
            return {"name": bucket_name, "trades": 0, "win_rate": 0,
                    "avg_return": 0, "avg_score": 0}
        win_rate = len(bucket_wins) / n * 100
        avg_return = sum(r["return_pct"] for r in bucket_recs) / n
        avg_score = sum(r["composite_score"] for r in bucket_recs) / n
        return {"name": bucket_name, "trades": n,
                "win_rate": win_rate, "avg_return": avg_return,
                "avg_score": avg_score}

    # Overall stats
    total = len(records)
    overall_wr = len(wins) / total * 100 if total > 0 else 0

    print("\n" + "=" * 75)
    print("  SCORE CORRELATION RESEARCH REPORT")
    print("=" * 75)

    # Summary Table
    print(f"\n  {'Rank Bucket':<14} {'Trades':>6} {'Win Rate':>9} {'Avg Return':>10} {'Avg Score':>10}")
    print(f"  {'-'*14} {'-'*6} {'-'*9} {'-'*10} {'-'*10}")

    bucket_results = []
    for name, fn in buckets.items():
        stats = bucket_stats(name, fn)
        bucket_results.append(stats)
        print(f"  {stats['name']:<14} {stats['trades']:>6} "
              f"{stats['win_rate']:>8.0f}% {stats['avg_return']:>+9.2f}% "
              f"{stats['avg_score']:>9.1f}")

    print(f"  {'---':>60}")
    print(f"  {'ALL':<14} {total:>6} {overall_wr:>8.0f}% "
          f"{sum(r['return_pct'] for r in records)/total:>+9.2f}% "
          f"{sum(r['composite_score'] for r in records)/total:>9.1f}")

    # Hypothesis test
    print("\n  --- HYPOTHESIS TEST ---")
    top = bucket_results[0]
    low = bucket_results[-1]

    if top["trades"] > 0 and low["trades"] > 0:
        wr_spread = top["win_rate"] - low["win_rate"]
        ret_spread = top["avg_return"] - low["avg_return"]
        print(f"  Win rate spread (Top - Low): {wr_spread:+.0f}pp")
        print(f"  Return spread  (Top - Low): {ret_spread:+.2f}%")

        if wr_spread >= 10 and ret_spread > 2:
            verdict = "CONFIRMED - Top-ranked stocks significantly outperform."
        elif wr_spread >= 5 or ret_spread > 0:
            verdict = "WEAKLY CONFIRMED - Top-ranked show some edge but not decisive."
        else:
            verdict = "REJECTED - Composite score ranking does not predict outcomes."

        print(f"  Verdict: {verdict}")

    # Individual rank analysis
    print("\n  --- INDIVIDUAL RANK PERFORMANCE ---")
    print(f"  {'Rank':<6} {'Trades':>6} {'Win Rate':>9} {'Avg Return':>10} {'Avg Score':>10}")
    print(f"  {'-'*6} {'-'*6} {'-'*9} {'-'*10} {'-'*10}")

    rank_stats = []
    for rank in range(1, TOP_N + 1):
        rank_recs = [r for r in records if r["rank"] == rank]
        n = len(rank_recs)
        if n == 0:
            continue
        rank_wins = [r for r in rank_recs if r["result"] == "WIN"]
        wr = len(rank_wins) / n * 100
        avg_ret = sum(r["return_pct"] for r in rank_recs) / n
        avg_sc = sum(r["composite_score"] for r in rank_recs) / n
        rank_stats.append({"rank": rank, "trades": n, "win_rate": wr,
                          "avg_return": avg_ret, "avg_score": avg_sc})

        marker = ""
        if wr >= 80:
            marker = " *** HOT"
        elif wr <= 20:
            marker = " !!! COLD"
        print(f"  #{rank:<5} {n:>6} {wr:>8.0f}% {avg_ret:>+9.2f}% {avg_sc:>9.1f}{marker}")

    # Correlation coefficient
    if len(rank_stats) >= 3:
        import math
        ranks = [s["rank"] for s in rank_stats]
        scores = [s["avg_score"] for s in rank_stats]
        returns = [s["avg_return"] for s in rank_stats]

        n_r = len(ranks)
        sum_xy = sum(ranks[i] * returns[i] for i in range(n_r))
        sum_x = sum(ranks)
        sum_y = sum(returns)
        sum_x2 = sum(r * r for r in ranks)
        sum_y2 = sum(ret * ret for ret in returns)
        denom = math.sqrt((n_r * sum_x2 - sum_x * sum_x) *
                         (n_r * sum_y2 - sum_y * sum_y))
        if denom != 0:
            r_val = (n_r * sum_xy - sum_x * sum_y) / denom
            print(f"\n  Rank-vs-Return Pearson r: {r_val:+.3f} "
                  f"({'negative: lower rank = better' if r_val < 0 else 'positive: unexpected'})")

    # Surprising findings
    print("\n  --- SURPRISING FINDINGS ---")
    surprises = []
    for s in rank_stats:
        if s["win_rate"] == 0 and s["trades"] >= 3:
            surprises.append(f"Rank #{s['rank']} has {s['win_rate']:.0f}% win rate over {s['trades']} trades")
        if s["win_rate"] == 100 and s["trades"] >= 3:
            surprises.append(f"Rank #{s['rank']} has 100% win rate over {s['trades']} trades")

    # Check for specific "always loses" ranks
    for s in rank_stats:
        if s["trades"] >= 4 and s["win_rate"] == 0:
            surprises.append(f"ALERT: Rank #{s['rank']} ALWAYS loses ({s['trades']} trades)")

    if surprises:
        for surprise in surprises:
            print(f"  ! {surprise}")
    else:
        print("  No strongly surprising individual rank patterns.")

    # By-regime breakdown
    print("\n  --- BY REGIME ---")
    for reg in ["risk_on", "neutral", "risk_off"]:
        reg_recs = [r for r in records if r["regime"] == reg]
        if not reg_recs:
            continue
        reg_wins = [r for r in reg_recs if r["result"] == "WIN"]
        n = len(reg_recs)
        wr = len(reg_wins) / n * 100 if n > 0 else 0
        avg_ret = sum(r["return_pct"] for r in reg_recs) / n if n > 0 else 0
        print(f"  {reg.upper().replace('_',' '):<12} {n} trades  "
              f"WR: {wr:.0f}%  Avg Ret: {avg_ret:+.2f}%")

    # Recommendation
    print("\n  --- RECOMMENDATION ---")
    if top["win_rate"] >= 60 and wr_spread >= 10:
        print("  KEEP the ranking system. Top-ranked picks show clear edge.")
        print("  Consider weighting higher-ranked picks more in position sizing.")
    elif wr_spread >= 5:
        print("  KEEP with caution. The ranking has some predictive value but is not strong.")
        print("  Consider refining factor weights or adding new factors.")
    else:
        print("  MODIFY the ranking system. Composite scores lack predictive power.")
        print("  Investigate individual factors for possible collinearity or noise.")
        print("  Consider using a simpler ranking (e.g., momentum-only) as baseline.")

    print("\n" + "=" * 75)


def main():
    print("Score Correlation Analysis")
    print(f"Dates: {', '.join(DATES)}")
    print(f"Top N per date: {TOP_N}")

    records = collect_data()
    print(f"\n  Collected {len(records)} trade records across {len(set(r['date'] for r in records))} dates.")

    if not records:
        print("  ERROR: No records collected. Check data availability.")
        return

    write_csv(records)
    analyze(records)


if __name__ == '__main__':
    main()
