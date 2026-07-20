#!/usr/bin/env python3
"""Baseline performance measurement for swing-picks system.

Usage:
    python scripts/baseline.py
    python scripts/baseline.py --experiment-name my_experiment
"""

# Baseline (auto-updated 2026-07-20):
#   Overall: Win Rate=60.9%, Avg Return=+0.93%, Total Return=+59.78%
#   risk_on:  Win Rate=53.3%, Total Return=+4.71%
#   neutral:  Win Rate=58.8%, Total Return=+12.39%
#   risk_off: Win Rate=65.6%, Total Return=+42.68%

import sys
import os
import sqlite3
import csv
import argparse
import contextlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factors import run as run_factors, VIX_SPIKE_THRESHOLD
from screener import run as run_screener, auto_weights
from backtest import check_forward, DB_PATH, OUTPUT_DIR

BASELINE_DATES = [
    "2024-02-15",  # risk_on
    "2024-08-15",  # risk_on
    "2025-05-15",  # risk_on
    "2026-04-06",  # risk_off (but profitable)
    "2024-04-15",  # neutral
    "2024-10-15",  # neutral
    "2025-08-15",  # neutral
    "2025-11-15",  # neutral
    "2026-01-20",  # risk_off (but profitable)
    "2025-01-15",  # risk_off
    "2026-03-09",  # risk_off
    "2026-03-16",  # risk_off (geopolitical crash)
    "2026-03-23",  # risk_off
    "2026-03-30",  # risk_off
    "2026-06-08",  # risk_off
]

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'


suppress_stdout = lambda: contextlib.redirect_stdout(open(os.devnull, 'w'))


def compute_return_pct(result, stats, entry_price, target_price, stoploss):
    """Determine actual return % based on trade outcome, matching backtest.py."""
    if result == "WIN":
        return round((target_price - entry_price) / entry_price * 100, 2)
    elif result == "LOSS":
        return round((stoploss - entry_price) / entry_price * 100, 2)
    else:
        return round((stats["end_close"] - entry_price) / entry_price * 100, 2)


def compute_hold_days(stats, result):
    """Calculate calendar days between entry and exit, matching backtest.py."""
    try:
        entry_dt = datetime.strptime(str(stats["entry_actual_date"]), "%Y-%m-%d")
        if result == "WIN" and stats["hit_target_date"]:
            exit_dt = datetime.strptime(str(stats["hit_target_date"]), "%Y-%m-%d")
        elif result == "LOSS" and stats["hit_sl_date"]:
            exit_dt = datetime.strptime(str(stats["hit_sl_date"]), "%Y-%m-%d")
        else:
            exit_dt = datetime.strptime(str(stats["end_date"]), "%Y-%m-%d")
        return (exit_dt - entry_dt).days
    except (ValueError, TypeError):
        return 0


def update_baseline_comment(script_path, overall, by_regime):
    """Update the baseline values comment at the top of this script file."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# Baseline (auto-updated {today_str}):",
        f"#   Overall: Win Rate={overall['win_rate']:.1f}%, Avg Return={overall['avg_return']:+.2f}%, Total Return={overall['total_return']:+.2f}%",
    ]
    for regime in ["risk_on", "neutral", "risk_off"]:
        b = by_regime.get(regime)
        if b and b["trades"] > 0:
            lines.append(
                f"#   {regime + ':':<9} Win Rate={b['win_rate']:.1f}%, Total Return={b['total_return']:+.2f}%"
            )
        else:
            lines.append(f"#   {regime + ':':<9} Win Rate=N/A, Total Return=N/A")

    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace the existing baseline comment block (lines starting with "# Baseline" and following "#   ")
    import re
    new_block = "\n".join(lines)
    content = re.sub(
        r'# Baseline \(auto-updated .*?\):\n(?:# .*\n)*',
        new_block + "\n",
        content,
        count=1
    )

    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser(description="Swing-picks baseline performance measurement")
    parser.add_argument('--experiment-name', type=str, default='default',
                        help='Name for this experiment run (default: default)')
    args = parser.parse_args()

    experiment = args.experiment_name
    csv_path = os.path.join(OUTPUT_DIR, 'baseline_raw.csv')

    print("=" * 74)
    print(f"  BASELINE REPORT — {len(BASELINE_DATES)} dates | Pipeline: factors + screener + forward check")
    if experiment != "default":
        print(f"  Experiment: {experiment}")
    print("=" * 74)

    all_trades = []          # list of dicts, one per trade
    date_summaries = []      # list of dicts, one per date

    for date_str in BASELINE_DATES:
        # --- Stage 1: Factors ---
        with suppress_stdout():
            try:
                factor_result = run_factors(as_of_date=date_str)
            except Exception as e:
                print(f"\n{YELLOW}{date_str}  ERROR in factors: {e}{RESET}")
                date_summaries.append({
                    "date": date_str, "regime": "error", "num_picks": 0,
                    "wins": 0, "losses": 0, "draws": 0, "trades": [],
                })
                continue

        regime_info = factor_result.get("regime", {})
        regime_label = regime_info.get("regime", "unknown")

        # VIX spike check
        vix_proxy = regime_info.get("vix_proxy")
        vix_20d_avg = regime_info.get("vix_20d_avg")
        spike_ratio = None
        is_spike = False
        if vix_proxy is not None and vix_20d_avg is not None and vix_20d_avg > 0:
            spike_ratio = vix_proxy / vix_20d_avg
            if spike_ratio > VIX_SPIKE_THRESHOLD:
                is_spike = True

        if is_spike:
            print(f"  {date_str}   {regime_label:<8}  VIX spike ({spike_ratio:.2f}x) — skipping picks")
            date_summaries.append({
                "date": date_str, "regime": regime_label, "num_picks": 0,
                "wins": 0, "losses": 0, "draws": 0, "trades": [],
            })
            continue

        # --- Stage 2: Screener with auto regime weights ---
        weights = auto_weights(regime_label)
        with suppress_stdout():
            try:
                screen_result = run_screener(top_n=5, weights=weights, as_of_date=date_str)
            except Exception as e:
                print(f"\n{YELLOW}{date_str}  ERROR in screener: {e}{RESET}")
                date_summaries.append({
                    "date": date_str, "regime": regime_label, "num_picks": 0,
                    "wins": 0, "losses": 0, "draws": 0, "trades": [],
                })
                continue

        ranked = screen_result.get("ranked", [])

        if not ranked:
            below = screen_result.get("below_threshold", [])
            if below:
                print(f"  {date_str}   {regime_label:<8}  All {len(below)} picks below threshold (score >= 70)")
            else:
                print(f"  {date_str}   {regime_label:<8}  No picks found")
            date_summaries.append({
                "date": date_str, "regime": regime_label, "num_picks": 0,
                "wins": 0, "losses": 0, "draws": 0, "trades": [],
            })
            continue

        # --- Stage 3: Forward check each pick ---
        conn = sqlite3.connect(DB_PATH)
        day_trades = []

        for s in ranked:
            try:
                result, detail, stats = check_forward(
                    conn, s["symbol"], date_str,
                    s["entry_price"], s["target_price"], s["stoploss"]
                )
            except Exception as e:
                # Log but don't crash; treat as DRAW with no data
                result = "DRAW"
                detail = f"Error: {e}"
                stats = {
                    "entry_actual_date": date_str,
                    "end_close": s["entry_price"],
                    "end_date": date_str,
                    "hit_target_date": None,
                    "hit_sl_date": None,
                    "entry_filled": False,
                }

            return_pct = compute_return_pct(
                result, stats, s["entry_price"], s["target_price"], s["stoploss"]
            )
            hold_days = compute_hold_days(stats, result)

            trade = {
                "experiment": experiment,
                "date": date_str,
                "regime": regime_label,
                "rank": s["rank"],
                "symbol": s["symbol"].replace(".NS", ""),
                "sector": s.get("sector", ""),
                "score": round(s.get("composite", 0), 1),
                "entry_price": s["entry_price"],
                "target_price": s["target_price"],
                "stoploss": s["stoploss"],
                "entry_filled": stats.get("entry_filled", False),
                "entry_actual_date": stats.get("entry_actual_date", date_str),
                "result": result,
                "return_pct": return_pct,
                "hold_days": hold_days,
                "hit_target_date": stats.get("hit_target_date") or "",
                "hit_sl_date": stats.get("hit_sl_date") or "",
                "detail": detail,
            }
            day_trades.append(trade)
            all_trades.append(trade)

        conn.close()

        wins = sum(1 for t in day_trades if t["result"] == "WIN")
        losses = sum(1 for t in day_trades if t["result"] == "LOSS")
        draws = sum(1 for t in day_trades if t["result"] == "DRAW")

        date_summaries.append({
            "date": date_str, "regime": regime_label, "num_picks": len(day_trades),
            "wins": wins, "losses": losses, "draws": draws, "trades": day_trades,
        })

    # ============================================================
    #  OUTPUT: Console table
    # ============================================================
    print()
    hdr = (f"{'Date':<12}  {'Regime':<10}  {'Picks':>5}  {'Wins':>4}  "
           f"{'Losses':>6}  {'Draws':>5}  {'WinRate':>8}  {'AvgRet%':>9}  {'TotalRet%':>9}")
    sep = "-" * len(hdr)
    print(hdr)
    print(sep)

    # Accumulators by regime for the BY REGIME section
    by_regime = {}

    for ds in date_summaries:
        date_str = ds["date"]
        regime_label = ds["regime"]
        picks = ds["num_picks"]
        wins = ds["wins"]
        losses = ds["losses"]
        draws = ds["draws"]

        if picks > 0:
            win_rate = wins / picks * 100
            total_ret = sum(t["return_pct"] for t in ds["trades"])
            avg_ret = total_ret / picks
        else:
            win_rate = 0.0
            total_ret = 0.0
            avg_ret = 0.0

        # Accumulate for BY REGIME
        if regime_label not in by_regime:
            by_regime[regime_label] = {
                "dates": 0, "trades": 0, "wins": 0, "losses": 0, "draws": 0,
                "total_return": 0.0,
            }
        b = by_regime[regime_label]
        b["dates"] += 1
        b["trades"] += picks
        b["wins"] += wins
        b["losses"] += losses
        b["draws"] += draws
        b["total_return"] += total_ret

        row = (f"{date_str:<12}  {regime_label:<10}  {picks:>5}  {wins:>4}  "
               f"{losses:>6}  {draws:>5}  {win_rate:>6.0f}%  "
               f"{avg_ret:>+8.2f}%  {total_ret:>+8.2f}%")

        if picks == 0:
            print(f"{YELLOW}{row}{RESET}")
        elif wins >= losses and wins > 0:
            print(f"{GREEN}{row}{RESET}")
        elif losses > wins:
            print(f"{RED}{row}{RESET}")
        else:
            print(f"{row}")

    print(sep)

    # --- BY REGIME ---
    print(f"\n{'--- BY REGIME ---':^74}")
    print(f"{'Regime':<12} {'Dates':>6} {'Trades':>7} {'Wins':>5} {'Losses':>6} "
          f"{'Draws':>6} {'WinRate':>8} {'AvgRet%':>9} {'TotalRet%':>9}")
    print("-" * 74)

    for regime_label in ["risk_on", "neutral", "risk_off"]:
        b = by_regime.get(regime_label)
        if not b or b["trades"] == 0:
            print(f"{regime_label:<12}  {b['dates'] if b else 0:>6}  {'0':>7}  "
                  f"{'0':>5}  {'0':>6}  {'0':>6}  {'N/A':>8}  {'N/A':>9}  {'N/A':>9}")
            continue
        win_rate = b["wins"] / b["trades"] * 100
        avg_ret = b["total_return"] / b["trades"]
        row = (f"{regime_label:<12}  {b['dates']:>6}  {b['trades']:>7}  "
               f"{b['wins']:>5}  {b['losses']:>6}  {b['draws']:>6}  "
               f"{win_rate:>6.0f}%  {avg_ret:>+8.2f}%  {b['total_return']:>+8.2f}%")
        if win_rate >= 50:
            print(f"{GREEN}{row}{RESET}")
        else:
            print(f"{RED}{row}{RESET}")

    # --- OVERALL ---
    total_trades = len(all_trades)
    total_wins = sum(1 for t in all_trades if t["result"] == "WIN")
    total_losses = sum(1 for t in all_trades if t["result"] == "LOSS")
    total_draws = sum(1 for t in all_trades if t["result"] == "DRAW")
    total_return = sum(t["return_pct"] for t in all_trades)
    total_avg_return = total_return / total_trades if total_trades > 0 else 0.0
    total_win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0.0
    total_hold = sum(t["hold_days"] for t in all_trades)
    total_avg_hold = total_hold / total_trades if total_trades > 0 else 0.0

    print()
    print(f"  --- OVERALL ---")
    print(f"  Total dates: {len(BASELINE_DATES)} | Total trades: {total_trades} | "
          f"Wins: {total_wins} | Losses: {total_losses} | Draws: {total_draws}")
    print(f"  Win rate: {total_win_rate:.1f}% | Avg return: {total_avg_return:+.2f}% | "
          f"Total return: {total_return:+.2f}% | Avg hold days: {total_avg_hold:.1f}")

    # ============================================================
    #  OUTPUT: CSV
    # ============================================================
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fieldnames = [
        "experiment", "date", "regime", "rank", "symbol", "sector", "score",
        "entry_price", "target_price", "stoploss", "entry_filled",
        "entry_actual_date", "result", "return_pct", "hold_days",
        "hit_target_date", "hit_sl_date",
    ]
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for trade in all_trades:
            writer.writerow({k: trade.get(k, "") for k in fieldnames})

    print(f"\n  CSV: {csv_path}")

    # ============================================================
    #  SELF-UPDATE: Baseline comment
    # ============================================================
    overall_stats = {
        "win_rate": total_win_rate,
        "avg_return": total_avg_return,
        "total_return": total_return,
    }
    by_regime_stats = {}
    for regime_label in ["risk_on", "neutral", "risk_off"]:
        b = by_regime.get(regime_label)
        if b and b["trades"] > 0:
            wr = b["wins"] / b["trades"] * 100
            by_regime_stats[regime_label] = {
                "trades": b["trades"],
                "win_rate": wr,
                "total_return": b["total_return"],
            }
        else:
            by_regime_stats[regime_label] = {"trades": 0, "win_rate": 0, "total_return": 0}

    update_baseline_comment(os.path.abspath(__file__), overall_stats, by_regime_stats)
    print(f"  Baseline comment updated in scripts/baseline.py")

    print()
    print(f"{BOLD}Done.{RESET}")


if __name__ == '__main__':
    main()
