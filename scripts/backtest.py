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
    # Verify entry was fillable on signal date
    entry_row = conn.execute(
        "SELECT high, low, close FROM daily_ohlcv WHERE symbol = ? AND date = ?",
        (symbol, as_of_date)
    ).fetchone()

    entry_filled = False
    if entry_row:
        day_high, day_low, day_close = float(entry_row[0]), float(entry_row[1]), float(entry_row[2])
        entry_filled = day_low <= entry_price <= day_high

    df_rows = conn.execute(
        "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date > ? ORDER BY date",
        (symbol, as_of_date)
    ).fetchall()

    if not df_rows:
        return "DRAW", None, f"No forward data after {as_of_date}", entry_filled

    hit_target = None
    hit_stoploss = None
    tgt_high = None
    sl_low = None
    max_gain_pct = 0
    max_loss_pct = 0
    end_close = float(df_rows[-1][3])
    end_date = df_rows[-1][0]

    for row in df_rows:
        dt, high, low, close = row[0], float(row[1]), float(row[2]), float(row[3])

        if hit_target is None and high >= target_price:
            hit_target = dt
            tgt_high = high
        if hit_stoploss is None and low <= stoploss:
            hit_stoploss = dt
            sl_low = low

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
        "hit_sl_date": hit_stoploss,
        "tgt_high": round(tgt_high, 2) if tgt_high else None,
        "sl_low": round(sl_low, 2) if sl_low else None,
        "entry_filled": entry_filled
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

    print(f"\n[1/3] Computing factors as of {as_of_date}...")
    factor_result = run_factors(as_of_date=as_of_date)
    regime = factor_result.get("regime", {})
    regime_label = regime.get("regime", "unknown")

    print("=" * 60)
    breadth = regime.get('breadth_ratio', '?') if regime else '?'
    print(f"  BACKTEST -- As-of: {as_of_date} | Regime: {regime_label.replace('_',' ').upper()} | Breadth: {breadth}")
    print("=" * 60)
    if not args.weights:
        if regime_label == "risk_off":
            weights = {"momentum": 0.20, "trend_quality": 0.20, "mean_reversion": 0.25, "quality": 0.35}
        elif regime_label == "neutral":
            weights = {"momentum": 0.30, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.20}
        else:
            weights = {"momentum": 0.35, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.15}
    else:
        for pair in args.weights.split(','):
            k, v = pair.split('=')
            weights[k.strip()] = float(v.strip())

    screen_result = run_screener(top_n=top_n, weights=weights, as_of_date=as_of_date)
    ranked = screen_result["ranked"]

    if not ranked:
        print("      No picks found.")
        return

    conn = sqlite3.connect(DB_PATH)

    rows = []
    for s in ranked:
        result, detail, stats = check_forward(
            conn, s["symbol"], as_of_date,
            s["entry_price"], s["target_price"], s["stoploss"]
        )
        rows.append({
            "rank": s["rank"], "symbol": s["symbol"], "sector": s["sector"],
            "entry_date": as_of_date, "entry": s["entry_price"],
            "entry_filled": "YES" if stats["entry_filled"] else "NO",
            "target_date": stats["hit_target_date"] or "--",
            "target": s["target_price"],
            "tgt_high": stats["tgt_high"],
            "sl_date": stats["hit_sl_date"] or "--",
            "sl": s["stoploss"],
            "sl_low": stats["sl_low"],
            "result": result, "target_pct": stats["target_pct"],
            "max_gain": stats["max_gain"]
        })

    conn.close()

    sep = "-" * 148
    print(f"\n{sep}")
    hdr = f"{'#':<3} {'Symbol':<16} {'Sector':<16} {'Ent Date':<12} {'Entry':>10} Fill {'Tgt Date':<12} {'Target':>10} {'Tgt Hi':>8} {'SL Date':<12} {'SL':>10} {'SL Lo':>8} {'Res':>4} {'Tgt%':>7} {'MaxGain':>8}"
    print(hdr)
    print(sep)
    wins = losses = draws = 0
    for r in rows:
        tgth = f"{r['tgt_high']:>8.2f}" if r['tgt_high'] else "      --"
        sll = f"{r['sl_low']:>8.2f}" if r['sl_low'] else "      --"
        print(f"{r['rank']:<3} {r['symbol']:<16} {r['sector']:<16} {r['entry_date']:<12} {r['entry']:>10.2f} {r['entry_filled']:<4} {r['target_date']:<12} {r['target']:>10.2f} {tgth} {r['sl_date']:<12} {r['sl']:>10.2f} {sll} {r['result']:>4} {r['target_pct']:>+6.2f}% {r['max_gain']:>+7.2f}%")
        if r['result'] == "WIN": wins += 1
        elif r['result'] == "LOSS": losses += 1
        else: draws += 1
    print(sep)
    hit_rate = wins / len(ranked) * 100 if len(ranked) > 0 else 0
    print(f"Wins: {wins}/{len(ranked)} | Losses: {losses}/{len(ranked)} | Draws: {draws}/{len(ranked)} | Win rate: {hit_rate:.0f}%")


if __name__ == '__main__':
    main()
