import sqlite3
import os
import json
import sys
from datetime import datetime, date

import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')

DEFAULT_WEIGHTS = {
    "momentum": 0.35,
    "trend_quality": 0.25,
    "mean_reversion": 0.25,
    "quality": 0.15
}


def log(entry):
    print(json.dumps(entry))
    sys.stdout.flush()


def compute_atr(conn, symbol, period=14, as_of_date=None):
    if as_of_date:
        df = pd.read_sql_query(
            "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT ?",
            conn, params=(symbol, as_of_date, period + 5)
        )
    else:
        df = pd.read_sql_query(
            "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            conn, params=(symbol, period + 5)
        )
    if len(df) < period:
        return 0
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
    return float(val) if np.isfinite(val) else 0


def get_current_price(conn, symbol, as_of_date=None):
    if as_of_date:
        row = conn.execute(
            "SELECT close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (symbol, as_of_date)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT close FROM daily_ohlcv WHERE symbol = ? ORDER BY date DESC LIMIT 1",
            (symbol,)
        ).fetchone()
    return float(row[0]) if row else 0


def run(top_n=5, weights=None, sector_cap=2, as_of_date=None):
    if weights is None:
        weights = dict(DEFAULT_WEIGHTS)

    if as_of_date:
        today = as_of_date
    else:
        today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    entry = {"stage": "screen", "status": "start", "top_n": top_n,
             "weights": weights, "sector_cap": sector_cap,
             "ts": datetime.now().isoformat()}
    log(entry)

    rows = c.execute('''
        SELECT f.symbol, f.momentum_price, f.momentum_vol, f.rs_momentum,
               f.trend_adx, f.ma_structure, f.pullback, f.rsi,
               f.liquidity, f.volatility,
               s.sector, s.universe_slug
        FROM factor_scores f
        JOIN stocks s ON f.symbol = s.symbol
        WHERE f.date = ?
    ''', (today,)).fetchall()

    if not rows:
        entry = {"stage": "screen", "status": "error", "error": "no_factor_data",
                 "ts": datetime.now().isoformat()}
        log(entry)
        conn.close()
        return {"error": "no_factor_data"}

    stocks_data = []
    for r in rows:
        symbol, mp, mv, rs, ta, ms, pb, rsi, liq, vol, sector, universe = r
        mp = mp or 0; mv = mv or 0; rs = rs or 0
        ta = ta or 0; ms = ms or 0; pb = pb or 0
        rsi = rsi or 0; liq = liq or 0; vol = vol or 0

        if liq < 25:
            continue

        if vol > 85:
            continue

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
            "factor_breakdown": {
                "momentum": round(momentum_cat, 2),
                "trend_quality": round(trend_cat, 2),
                "mean_reversion": round(mean_rev_cat, 2),
                "quality": round(quality_cat, 2)
            },
            "factor_detail": {
                "momentum_price": mp, "momentum_vol": mv, "rs_momentum": rs,
                "trend_adx": ta, "ma_structure": ms,
                "pullback": pb, "rsi": rsi,
                "liquidity": liq, "volatility": vol
            },
            "sector": sector or "Unknown",
            "universe": universe or "unknown"
        })

    stocks_data.sort(key=lambda x: x["composite"], reverse=True)

    ranked = []
    sector_counts = {}
    rejected = []

    def sector_key(s):
        return s or "Unknown"

    for stock in stocks_data:
        sec = sector_key(stock["sector"])
        count = sector_counts.get(sec, 0)
        if count >= sector_cap:
            rejected.append({"symbol": stock["symbol"], "reason": "sector_cap",
                             "sector": sec, "composite": stock["composite"]})
            continue
        stock["rank"] = len(ranked) + 1
        ranked.append(stock)
        sector_counts[sec] = count + 1
        if len(ranked) >= top_n:
            break

    for stock in ranked:
        symbol = stock["symbol"]
        price = get_current_price(conn, symbol, as_of_date=as_of_date)
        atr_val = compute_atr(conn, symbol, as_of_date=as_of_date)

        entry_price = price

        target_price = entry_price + (1.5 * atr_val) if atr_val > 0 else entry_price * 1.04
        stoploss = entry_price - (1.5 * atr_val) if atr_val > 0 else entry_price * 0.96

        stock["entry_price"] = round(entry_price, 2)
        stock["target_price"] = round(target_price, 2)
        stock["stoploss"] = round(stoploss, 2)

        entry = {"stage": "screen", "rank": stock["rank"], "symbol": symbol,
                 "composite": round(stock["composite"], 2),
                 "breakdown": stock["factor_breakdown"],
                 "entry": stock["entry_price"], "target": stock["target_price"],
                 "stoploss": stock["stoploss"], "sector": stock["sector"],
                 "ts": datetime.now().isoformat()}
        log(entry)

    run_ts = datetime.now().isoformat()
    c.execute("DELETE FROM screener_results WHERE run_date = ?", (run_ts,))
    for stock in ranked:
        c.execute('''
            INSERT INTO screener_results (run_date, rank, symbol, composite,
                factor_breakdown, factor_detail, entry_price, target_price,
                stoploss, sector, universe)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (run_ts, stock["rank"], stock["symbol"], round(stock["composite"], 2),
              json.dumps(stock["factor_breakdown"]),
              json.dumps(stock["factor_detail"]),
              stock["entry_price"], stock["target_price"], stock["stoploss"],
              stock["sector"], stock["universe"]))
    conn.commit()

    sector_dist = {}
    for s in ranked:
        sec = sector_key(s["sector"])
        sector_dist[sec] = sector_dist.get(sec, 0) + 1

    entry = {"stage": "screen", "status": "complete", "top_n": len(ranked),
             "sector_distribution": sector_dist,
             "rejected_count": len(rejected), "rejected": rejected,
             "ts": datetime.now().isoformat()}
    log(entry)

    conn.close()
    return {"ranked": ranked, "rejected": rejected, "run_ts": run_ts}


if __name__ == '__main__':
    result = run()
    if "error" not in result:
        for s in result["ranked"]:
            print(f"#{s['rank']} {s['symbol']} Score:{s['composite']:.1f} Entry:{s['entry_price']} Target:{s['target_price']} SL:{s['stoploss']}")
