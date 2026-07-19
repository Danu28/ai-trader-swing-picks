import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS factor_scores (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            momentum_price REAL,
            momentum_vol REAL,
            rs_momentum REAL,
            trend_adx REAL,
            ma_structure REAL,
            pullback REAL,
            rsi REAL,
            liquidity REAL,
            volatility REAL,
            composite REAL,
            PRIMARY KEY (symbol, date)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS screener_results (
            run_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            composite REAL,
            factor_breakdown TEXT,
            factor_detail TEXT,
            entry_price REAL,
            target_price REAL,
            stoploss REAL,
            sector TEXT,
            universe TEXT,
            PRIMARY KEY (run_date, rank)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS market_regime (
            date TEXT PRIMARY KEY,
            regime TEXT,
            nifty_trend TEXT,
            breadth_ratio REAL,
            vix_proxy REAL
        )
    ''')

    try:
        c.execute("ALTER TABLE market_regime ADD COLUMN vix_20d_avg REAL")
        print("  Added vix_20d_avg column to market_regime.")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("Migration complete: factor_scores, screener_results, market_regime tables ready.")

if __name__ == '__main__':
    migrate()
