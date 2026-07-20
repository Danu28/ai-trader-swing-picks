import sqlite3
import os
import json
import time
import sys
from datetime import datetime, date, timedelta

import yfinance as yf

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')


def log(entry):
    print(json.dumps(entry))
    sys.stdout.flush()


def run(max_retries=3, retry_delay=5):
    today = date.today().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    symbols = [r[0] for r in c.execute("SELECT symbol FROM stocks").fetchall()]
    log({"stage": "update", "status": "start", "symbols_total": len(symbols), "ts": datetime.now().isoformat()})

    updated = 0
    skipped = 0
    errors = 0
    errors_detail = []

    for i, symbol in enumerate(symbols):
        latest_row = c.execute(
            "SELECT MAX(date) FROM daily_ohlcv WHERE symbol = ?", (symbol,)
        ).fetchone()

        latest_date = latest_row[0] if latest_row and latest_row[0] else None
        if latest_date and latest_date >= today:
            entry = {"stage": "update", "symbol": symbol, "action": "no_new_data",
                     "reason": "already_current", "latest_date": latest_date,
                     "ts": datetime.now().isoformat()}
            log(entry)
            skipped += 1
            continue

        for attempt in range(1, max_retries + 1):
            try:
                ticker = yf.Ticker(symbol)
                if latest_date:
                    start = (datetime.strptime(latest_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                    end = today
                else:
                    start = "2016-01-01"
                    end = today

                df = ticker.history(start=start, end=end)
                if df.empty:
                    entry = {"stage": "update", "symbol": symbol, "action": "no_new_data",
                             "reason": "yfinance_empty_response", "ts": datetime.now().isoformat()}
                    log(entry)
                    skipped += 1
                    break

                rows_inserted = 0
                for idx, row in df.iterrows():
                    dt = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10]
                    c.execute('''
                        INSERT OR REPLACE INTO daily_ohlcv (symbol, date, open, high, low, close, volume, adj_close)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (symbol, dt, float(row['Open']), float(row['High']),
                          float(row['Low']), float(row['Close']),
                          int(row['Volume']), float(row['Close'])))
                    rows_inserted += 1

                conn.commit()
                date_range = [str(df.index[0])[:10], str(df.index[-1])[:10]] if len(df) > 0 else []
                entry = {"stage": "update", "symbol": symbol, "action": "insert",
                         "rows": rows_inserted, "date_range": date_range,
                         "ts": datetime.now().isoformat()}
                log(entry)
                updated += 1
                break

            except Exception as e:
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                entry = {"stage": "update", "symbol": symbol, "action": "error",
                         "error": str(e), "retries": attempt, "ts": datetime.now().isoformat()}
                log(entry)
                errors += 1
                errors_detail.append({"symbol": symbol, "error": str(e)})
                break

        if (i + 1) % 50 == 0:
            conn.commit()

    entry = {"stage": "update", "status": "complete", "updated": updated, "skipped": skipped,
             "errors": errors, "errors_detail": errors_detail, "ts": datetime.now().isoformat()}
    log(entry)

    conn.close()
    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "errors_detail": errors_detail,
    }


if __name__ == '__main__':
    result = run()
    print(f"\nUpdate complete: {result['updated']} updated, {result['skipped']} skipped, {result['errors']} errors")
