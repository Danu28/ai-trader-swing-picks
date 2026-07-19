import sys
import os
import sqlite3
import json
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factors import run as run_factors
from screener import run as run_screener

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')


def check_forward(conn, symbol, as_of_date, entry_price, target_price, stoploss):
    df_rows = conn.execute(
        "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date > ? ORDER BY date",
        (symbol, as_of_date)
    ).fetchall()

    if not df_rows:
        return "DRAW", None, f"No forward data after {as_of_date}"

    hit_target = None
    hit_stoploss = None
    max_gain_pct = 0
    max_loss_pct = 0
    end_close = float(df_rows[-1][3])
    end_date = df_rows[-1][0]

    for row in df_rows:
        dt, high, low, close = row[0], float(row[1]), float(row[2]), float(row[3])

        if hit_target is None and high >= target_price:
            hit_target = dt
        if hit_stoploss is None and low <= stoploss:
            hit_stoploss = dt

        gain_pct = (high - entry_price) / entry_price
        loss_pct = (low - entry_price) / entry_price
        if gain_pct > max_gain_pct:
            max_gain_pct = gain_pct
        if loss_pct < max_loss_pct:
            max_loss_pct = loss_pct

        if hit_target is not None and hit_stoploss is not None:
            break

    if hit_target and hit_stoploss:
        if hit_target <= hit_stoploss:
            result = "WIN"
            detail = f"Target hit on {hit_target} (before SL on {hit_stoploss})"
        else:
            result = "LOSS"
            detail = f"SL hit on {hit_stoploss} (before target on {hit_target})"
    elif hit_target:
        result = "WIN"
        detail = f"Target hit on {hit_target}"
    elif hit_stoploss:
        result = "LOSS"
        detail = f"SL hit on {hit_stoploss}"
    else:
        end_change = (end_close - entry_price) / entry_price
        result = "DRAW"
        detail = f"Neither hit. Closed at {end_close:.2f} ({end_change:+.1%}) on {end_date}"

    target_pct = round((target_price - entry_price) / entry_price * 100, 2)
    return result, detail, {
        "max_gain": round(max_gain_pct * 100, 2),
        "max_loss": round(max_loss_pct * 100, 2),
        "target_pct": target_pct,
        "end_close": end_close,
        "end_date": end_date,
        "hit_target_date": hit_target,
        "hit_sl_date": hit_stoploss
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', type=str, required=True, help='Backtest date YYYY-MM-DD')
    parser.add_argument('--top', type=int, default=5)
    parser.add_argument('--weights', type=str, default=None)
    args = parser.parse_args()

    as_of_date = args.as_of
    top_n = args.top

    print("=" * 60)
    print(f"  BACKTEST -- As-of: {as_of_date}")
    print("=" * 60)

    print(f"\n[1/3] Computing factors as of {as_of_date}...")
    factor_result = run_factors(as_of_date=as_of_date)
    print(f"      {factor_result['computed']} scored, {factor_result['filtered_out']} filtered")

    regime = factor_result.get("regime", {})
    regime_label = regime.get("regime", "unknown")
    if regime:
        print(f"      Regime: {regime_label.upper()} | Nifty: {regime.get('nifty_trend')}")

    if not args.weights:
        if regime_label == "risk_off":
            weights = {"momentum": 0.20, "trend_quality": 0.20, "mean_reversion": 0.25, "quality": 0.35}
            print(f"      Weights: risk_off (M:0.20, T:0.20, MR:0.25, Q:0.35)")
        elif regime_label == "neutral":
            weights = {"momentum": 0.30, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.20}
            print(f"      Weights: neutral (M:0.30, T:0.25, MR:0.25, Q:0.20)")
        else:
            weights = {"momentum": 0.35, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.15}
            print(f"      Weights: {regime_label} (standard)")
    else:
        for pair in args.weights.split(','):
            k, v = pair.split('=')
            weights[k.strip()] = float(v.strip())
        print(f"      Weights: custom ({weights})")

    print(f"\n[2/3] Screening as of {as_of_date}...")
    screen_result = run_screener(top_n=top_n, weights=weights, as_of_date=as_of_date)
    ranked = screen_result["ranked"]
    rejected = screen_result.get("rejected", [])

    if not ranked:
        print("      No picks found.")
        return

    print(f"      Top {len(ranked)} picks:")
    for s in ranked:
        print(f"      #{s['rank']} {s['symbol']} Score:{s['composite']:.1f} Entry:{s['entry_price']:.2f} Target:{s['target_price']:.2f} SL:{s['stoploss']:.2f}")

    print(f"\n[3/3] Forward check from {as_of_date} to today:")

    conn = sqlite3.connect(DB_PATH)
    wins = 0
    losses = 0
    draws = 0

    for s in ranked:
        result, detail, stats = check_forward(
            conn, s["symbol"], as_of_date,
            s["entry_price"], s["target_price"], s["stoploss"]
        )
        tag = {"WIN": "[WIN] ", "LOSS": "[LOSS]", "DRAW": "[DRAW]"}.get(result, "[????]")
        print(f"\n  {tag} {s['symbol']}: {detail}")
        if stats:
            target_str = f"Target: {stats['target_pct']:+.2f}%" if result == "WIN" or result == "LOSS" else ""
            print(f"      {target_str} | Max gain: {stats['max_gain']:+.2f}% | Max loss: {stats['max_loss']:+.2f}%")

        if result == "WIN":
            wins += 1
        elif result == "LOSS":
            losses += 1
        else:
            draws += 1

    conn.close()

    print(f"\n  --- Summary ---")
    print(f"  Wins: {wins}/{len(ranked)} | Losses: {losses}/{len(ranked)} | Draws: {draws}/{len(ranked)}")
    hit_rate = wins / len(ranked) * 100 if len(ranked) > 0 else 0
    print(f"  Win rate: {hit_rate:.0f}%")


if __name__ == '__main__':
    main()
