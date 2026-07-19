import sqlite3
import os
import json
import sys
from datetime import datetime, date

import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')

# Threshold for VIX spike detection — if VIX proxy / 20d avg exceeds this, skip trades
VIX_SPIKE_THRESHOLD = 1.5


def log(entry):
    print(json.dumps(entry))
    sys.stdout.flush()


def percentile_rank(series):
    return series.rank(pct=True) * 100


def compute_adx(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(span=period, adjust=False).mean() / atr

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx


def compute_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def compute_sma(df, column, period):
    return df[column].rolling(window=period).mean()


def compute_roc(df, column, period):
    return (df[column] / df[column].shift(period) - 1) * 100


def compute_factors_for_symbol(conn, symbol, nifty50_close=None, as_of_date=None):
    if as_of_date:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date",
            conn, params=(symbol, as_of_date)
        )
    else:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM daily_ohlcv WHERE symbol = ? ORDER BY date",
            conn, params=(symbol,)
        )
    if len(df) < 200:
        return None

    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)

    close = df['close']
    volume = df['volume']

    roc_21 = compute_roc(df, 'close', 21)
    roc_63 = compute_roc(df, 'close', 63)
    momentum_price_raw = roc_21.iloc[-1] * roc_63.iloc[-1]
    momentum_price_raw = max(momentum_price_raw, -10000)

    vol_10 = volume.rolling(10).mean()
    vol_50 = volume.rolling(50).mean()
    momentum_vol_raw = (vol_10.iloc[-1] / vol_50.iloc[-1]) if vol_50.iloc[-1] > 0 else 1.0

    adx = compute_adx(df)
    trend_adx_raw = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0

    sma_20 = compute_sma(df, 'close', 20)
    sma_50 = compute_sma(df, 'close', 50)
    sma_200 = compute_sma(df, 'close', 200)
    price = close.iloc[-1]
    ma_score = 0
    if not pd.isna(sma_20.iloc[-1]) and not pd.isna(sma_50.iloc[-1]) and sma_20.iloc[-1] > sma_50.iloc[-1]:
        ma_score += 25
    if not pd.isna(sma_50.iloc[-1]) and not pd.isna(sma_200.iloc[-1]) and sma_50.iloc[-1] > sma_200.iloc[-1]:
        ma_score += 25
    if not pd.isna(sma_20.iloc[-1]) and not pd.isna(sma_200.iloc[-1]) and sma_20.iloc[-1] > sma_200.iloc[-1]:
        ma_score += 25
    if not pd.isna(sma_20.iloc[-1]) and price > sma_20.iloc[-1]:
        ma_score += 25
    ma_structure_raw = ma_score

    high_20 = df['high'].rolling(20).max().iloc[-1]
    pullback_raw = (high_20 - price) / (high_20 + 1e-10) * 100

    rsi = compute_rsi(df)
    rsi_value = rsi.iloc[-1]
    if 40 <= rsi_value <= 60:
        rsi_raw = 100
    elif 30 <= rsi_value < 40 or 60 < rsi_value <= 70:
        rsi_raw = 60
    else:
        rsi_raw = 20

    turnover = close * volume
    liquidity_raw = turnover.rolling(20).mean().iloc[-1]

    atr = compute_adx(df)
    atr_14 = pd.Series(
        pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        ], axis=1).max(axis=1)
    ).ewm(span=14, adjust=False).mean()
    volatility_raw = (atr_14.iloc[-1] / price * 100) if not pd.isna(atr_14.iloc[-1]) and price > 0 else 0

    last_date = df['date'].iloc[-1]
    return {
        'symbol': symbol,
        'date': last_date,
        'momentum_price_raw': momentum_price_raw,
        'momentum_vol_raw': momentum_vol_raw,
        'rs_momentum_raw': None,
        'trend_adx_raw': trend_adx_raw,
        'ma_structure_raw': ma_structure_raw,
        'pullback_raw': pullback_raw,
        'rsi_raw': rsi_raw,
        'liquidity_raw': liquidity_raw,
        'volatility_raw': volatility_raw,
        'df': df,
        'roc_21': roc_21,
        'roc_63': roc_63,
        'close': price,
        'symbol_for_rs': symbol
    }


def compute_regime(conn, date, as_of_date=None):
    nifty50_symbols = [r[0] for r in conn.execute(
        "SELECT symbol FROM stocks WHERE universe_slug = 'nifty50'").fetchall()]
    if len(nifty50_symbols) < 5:
        return None

    # Get last 21 trading dates (current + 20 prior) for rolling average
    ref_date = as_of_date if as_of_date else date
    trading_dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM daily_ohlcv WHERE date <= ? ORDER BY date DESC LIMIT 21",
        (ref_date,)
    ).fetchall()]
    trading_dates_set = set(trading_dates)

    breadth = 0
    returns_21 = []
    atr_sum = 0
    count = 0
    daily_vix = {}  # date -> list of (atr/close)*100 values across stocks

    for sym in nifty50_symbols:
        try:
            if as_of_date:
                df = pd.read_sql_query(
                    "SELECT date, close, high, low FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date",
                    conn, params=(sym, as_of_date))
            else:
                df = pd.read_sql_query(
                    "SELECT date, close, high, low FROM daily_ohlcv WHERE symbol = ? ORDER BY date",
                    conn, params=(sym,))
            if len(df) < 50:
                continue
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['sma_50'] = df['close'].rolling(50).mean()
            above_sma = df['close'].iloc[-1] > df['sma_50'].iloc[-1] if not pd.isna(df['sma_50'].iloc[-1]) else False
            if above_sma:
                breadth += 1
            ret_21 = float(df['close'].iloc[-1] / df['close'].shift(21).iloc[-1]) - 1 if len(df) > 21 else 0
            if abs(ret_21) < 1:
                returns_21.append(ret_21)

            # Compute ATR(14) series
            tr1 = df['high'] - df['low']
            tr2 = abs(df['high'] - df['close'].shift(1))
            tr3 = abs(df['low'] - df['close'].shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr14_series = tr.ewm(span=14, adjust=False).mean()

            # Current date ATR/close
            atr14 = atr14_series.iloc[-1]
            close = df['close'].iloc[-1]
            if close > 0:
                atr_sum += float(atr14 / close) * 100
            count += 1

            # Collect daily ATR/close ratios for rolling average
            mask = df['date'].isin(trading_dates_set)
            if mask.any():
                filtered = df.loc[mask, ['date', 'close']].copy()
                filtered['atr'] = atr14_series.loc[mask].values
                filtered['ratio'] = (filtered['atr'].astype(float) / filtered['close'].astype(float)) * 100
                for _, row in filtered.iterrows():
                    dt = row['date']
                    val = float(row['ratio'])
                    if not pd.isna(val) and row['close'] > 0:
                        if dt not in daily_vix:
                            daily_vix[dt] = []
                        daily_vix[dt].append(val)
        except Exception:
            continue

    if count < 5:
        return None

    breadth_ratio = round(breadth / count, 2)
    avg_return_21 = np.mean(returns_21) if returns_21 else 0
    vix_proxy = round(atr_sum / count, 2)

    # Compute 20-day rolling average from OHLCV-derived daily VIX proxies
    vix_20d_avg = None
    past_daily_avgs = []
    for d in sorted(daily_vix.keys()):
        ratios = daily_vix[d]
        if len(ratios) >= 5:
            past_daily_avgs.append(round(sum(ratios) / len(ratios), 2))
    # Exclude current date from rolling average
    if len(past_daily_avgs) > 1:
        past_daily_avgs = past_daily_avgs[:-1]
    if len(past_daily_avgs) >= 5:
        vix_20d_avg = round(sum(past_daily_avgs) / len(past_daily_avgs), 2)

    if avg_return_21 > 0.02 and breadth_ratio > 0.5:
        regime = "risk_on"
        nifty_trend = "bullish"
    elif avg_return_21 < -0.02 and breadth_ratio < 0.4:
        regime = "risk_off"
        nifty_trend = "bearish"
    else:
        regime = "neutral"
        nifty_trend = "sideways"

    conn.execute("INSERT OR REPLACE INTO market_regime (date, regime, nifty_trend, breadth_ratio, vix_proxy, vix_20d_avg) VALUES (?, ?, ?, ?, ?, ?)",
                 (date, regime, nifty_trend, breadth_ratio, vix_proxy, vix_20d_avg))
    return {"regime": regime, "nifty_trend": nifty_trend, "breadth_ratio": breadth_ratio, "vix_proxy": vix_proxy, "vix_20d_avg": vix_20d_avg}


def run(weights=None, as_of_date=None):
    if as_of_date:
        today = as_of_date
    else:
        today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    symbols = [r[0] for r in c.execute("SELECT symbol FROM stocks").fetchall()]
    factor_names = ['momentum_price', 'momentum_vol', 'rs_momentum',
                    'trend_adx', 'ma_structure', 'pullback', 'rsi',
                    'liquidity', 'volatility']

    entry = {"stage": "factors", "status": "start", "symbols": len(symbols),
             "factors": factor_names, "ts": datetime.now().isoformat()}
    log(entry)

    nifty_close = None
    try:
        if as_of_date:
            nifty_df = pd.read_sql_query(
                "SELECT date, close FROM daily_ohlcv WHERE symbol = '^NSEI' AND date <= ? ORDER BY date",
                conn, params=(as_of_date,)
            )
        else:
            nifty_df = pd.read_sql_query(
                "SELECT date, close FROM daily_ohlcv WHERE symbol = '^NSEI' ORDER BY date",
                conn
            )
        if len(nifty_df) > 0:
            nifty_close = nifty_df.set_index('date')['close'].astype(float)
    except Exception:
        pass

    results = []
    filtered_out = {}
    computed = 0

    for symbol in symbols:
        try:
            result = compute_factors_for_symbol(conn, symbol, as_of_date=as_of_date)
            if result is None:
                filtered_out[symbol] = "insufficient_data"
                entry = {"stage": "factors", "symbol": symbol, "status": "skipped",
                         "reason": "insufficient_data", "ts": datetime.now().isoformat()}
                log(entry)
                continue
            results.append(result)
        except Exception as e:
            filtered_out[symbol] = str(e)
            entry = {"stage": "factors", "symbol": symbol, "status": "error",
                     "error": str(e), "ts": datetime.now().isoformat()}
            log(entry)

    if len(results) == 0:
        entry = {"stage": "factors", "status": "complete", "computed": 0,
                 "filtered_out": len(filtered_out), "filtered_reasons": filtered_out,
                 "ts": datetime.now().isoformat()}
        log(entry)
        conn.close()
        return {"computed": 0, "filtered_out": len(filtered_out)}

    momentum_prices = np.array([r['momentum_price_raw'] for r in results])
    momentum_vols = np.array([r['momentum_vol_raw'] for r in results])
    trend_adxs = np.array([r['trend_adx_raw'] for r in results])
    ma_structures = np.array([r['ma_structure_raw'] for r in results], dtype=float)
    pullbacks = np.array([r['pullback_raw'] for r in results])
    rsis = np.array([r['rsi_raw'] for r in results])
    liquiditys = np.array([r['liquidity_raw'] for r in results])
    volatilitys = np.array([r['volatility_raw'] for r in results])

    for arr in [momentum_prices, momentum_vols, trend_adxs, ma_structures, pullbacks, rsis, liquiditys, volatilitys]:
        finite_mask = np.isfinite(arr)
        if not np.all(finite_mask):
            arr[~finite_mask] = np.nan

    from scipy.stats import rankdata

    def safe_percentile_rank(arr):
        valid = ~np.isnan(arr)
        if valid.sum() == 0:
            return np.full_like(arr, 50.0)
        ranks = np.full_like(arr, np.nan)
        ranks[valid] = rankdata(arr[valid]) / valid.sum() * 100
        return np.nan_to_num(ranks, nan=50.0)

    p_momentum_price = safe_percentile_rank(momentum_prices)
    p_momentum_vol = safe_percentile_rank(momentum_vols)
    p_trend_adx = safe_percentile_rank(trend_adxs)
    p_ma_structure = safe_percentile_rank(ma_structures)
    p_rsi = rsis
    p_liquidity = safe_percentile_rank(liquiditys)
    p_volatility = 100 - safe_percentile_rank(volatilitys)

    rs_momentum_arr = np.zeros(len(results))
    if nifty_close is not None:
        for i, r in enumerate(results):
            stock_ret = r['close'] / r['df']['close'].shift(21).iloc[-1] - 1 if len(r['df']) > 21 else 0
            nifty_ret = 0
            if len(nifty_close) > 21:
                nifty_ret = float(nifty_close.iloc[-1]) / float(nifty_close.shift(21).iloc[-1]) - 1
                if not np.isfinite(nifty_ret):
                    nifty_ret = 0
            rs_momentum_arr[i] = (stock_ret - nifty_ret) * 100
    p_rs_momentum = safe_percentile_rank(rs_momentum_arr)

    pullback_penalty = 100 - safe_percentile_rank(pullbacks)

    for i, r in enumerate(results):
        entry = {"stage": "factors", "symbol": r['symbol'],
                 "scores": {
                     "momentum_price": round(float(p_momentum_price[i]), 2),
                     "momentum_vol": round(float(p_momentum_vol[i]), 2),
                     "rs_momentum": round(float(p_rs_momentum[i]), 2),
                     "trend_adx": round(float(p_trend_adx[i]), 2),
                     "ma_structure": round(float(p_ma_structure[i]), 2),
                     "pullback": round(float(pullback_penalty[i]), 2),
                     "rsi": round(float(p_rsi[i]), 2),
                     "liquidity": round(float(p_liquidity[i]), 2),
                     "volatility": round(float(p_volatility[i]), 2)
                 }, "ts": datetime.now().isoformat()}
        log(entry)

    c.execute("DELETE FROM factor_scores WHERE date = ?", (today,))
    for i, r in enumerate(results):
        c.execute('''
            INSERT INTO factor_scores (symbol, date, momentum_price, momentum_vol,
                rs_momentum, trend_adx, ma_structure, pullback, rsi, liquidity, volatility)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (r['symbol'], today,
              round(float(p_momentum_price[i]), 2), round(float(p_momentum_vol[i]), 2),
              round(float(p_rs_momentum[i]), 2), round(float(p_trend_adx[i]), 2),
              round(float(p_ma_structure[i]), 2), round(float(pullback_penalty[i]), 2),
              round(float(p_rsi[i]), 2), round(float(p_liquidity[i]), 2),
              round(float(p_volatility[i]), 2)))
    regime = compute_regime(conn, today, as_of_date=as_of_date)
    entry = {"stage": "factors", "regime": regime, "ts": datetime.now().isoformat()}
    log(entry)

    conn.commit()

    entry = {"stage": "factors", "status": "complete", "computed": len(results),
             "filtered_out": len(filtered_out),
             "filter_reasons": filtered_out,
             "ts": datetime.now().isoformat()}
    log(entry)

    conn.close()
    return {"computed": len(results), "filtered_out": len(filtered_out),
            "filter_reasons": filtered_out, "regime": regime}


if __name__ == '__main__':
    result = run()
    print(f"\nFactors complete: {result['computed']} scored, {result['filtered_out']} filtered")
