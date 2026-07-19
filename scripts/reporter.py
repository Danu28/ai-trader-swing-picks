import sqlite3
import os
import json
import sys
from datetime import datetime, date

import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')


def log(entry):
    print(json.dumps(entry))
    sys.stdout.flush()


def generate_html_report(ranked, market_regime, run_metadata, today, report_path):
    picks_html = ""
    for s in ranked:
        fb = s.get("factor_breakdown", {})
        fd = s.get("factor_detail", {})
        top_drivers = sorted(fd.items(), key=lambda x: x[1], reverse=True)[:2]
        drivers_str = ", ".join(f"{k}: {v:.0f}" for k, v in top_drivers)
        picks_html += f'''
    <tr>
      <td class="rank">#{s["rank"]}</td>
      <td><strong>{s["symbol"]}</strong><br><small>{s["sector"]}</small></td>
      <td class="score">{s["composite"]:.1f}</td>
      <td class="price">₹{s["entry_price"]:,.2f}</td>
      <td class="price target">₹{s["target_price"]:,.2f}</td>
      <td class="price stoploss">₹{s["stoploss"]:,.2f}</td>
      <td><small>{drivers_str}</small></td>
    </tr>'''

    regime_str = market_regime.get("regime", "unknown").replace("_", " ").title() if market_regime else "N/A"
    regime_emoji = {"risk_on": "[ON]", "risk_off": "[OFF]", "neutral": "[--]"}.get(
        market_regime.get("regime", ""), "[--]") if market_regime else "[--]"

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Swing Picks — {today}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; font-size: 1.8em; margin-bottom: 4px; }}
  .subtitle {{ color: #8b949e; margin-bottom: 24px; }}
  .meta {{ display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 20px; }}
  .meta-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; flex: 1; min-width: 150px; }}
  .meta-card .label {{ color: #8b949e; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.05em; }}
  .meta-card .value {{ color: #c9d1d9; font-size: 1.2em; font-weight: 600; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }}
  th {{ background: #21262d; color: #8b949e; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 12px; text-align: left; }}
  td {{ padding: 12px; border-top: 1px solid #21262d; }}
  .rank {{ color: #58a6ff; font-weight: 700; font-size: 1.1em; }}
  .score {{ color: #3fb950; font-weight: 600; font-size: 1.1em; }}
  .price {{ font-family: 'JetBrains Mono', monospace; }}
  .target {{ color: #3fb950; }}
  .stoploss {{ color: #f85149; }}
  .warnings {{ background: #1a1a0a; border: 1px solid #d29922; border-radius: 8px; padding: 16px; margin-top: 20px; }}
  .warnings h3 {{ color: #d29922; margin-top: 0; }}
  .warnings ul {{ margin: 0; padding-left: 20px; color: #e3b341; }}
  .footer {{ color: #484f58; font-size: 0.75em; text-align: center; margin-top: 30px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Swing Trade Picks</h1>
  <p class="subtitle">{today} &nbsp;|&nbsp; Regime: {regime_emoji} {regime_str} &nbsp;|&nbsp; Universe: Nifty 50 + Midcap 150</p>

  <div class="meta">
    <div class="meta-card"><div class="label">Regime</div><div class="value">{regime_emoji} {regime_str}</div></div>
    <div class="meta-card"><div class="label">Stocks Scored</div><div class="value">{run_metadata.get("symbols_scored", "N/A")}</div></div>
    <div class="meta-card"><div class="label">Data Freshness</div><div class="value">{run_metadata.get("data_freshness_pct", "N/A")}%</div></div>
    <div class="meta-card"><div class="label">Nifty Trend</div><div class="value">{market_regime.get("nifty_trend", "N/A").title() if market_regime else "N/A"}</div></div>
  </div>

  <table>
    <thead>
      <tr><th>Rank</th><th>Symbol / Sector</th><th>Score</th><th>Entry</th><th>Target</th><th>Stoploss</th><th>Key Drivers</th></tr>
    </thead>
    <tbody>{picks_html}
    </tbody>
  </table>

  <div class="warnings">
    <h3>Notes & Warnings</h3>
    <ul>
      <li>All prices in INR. Entry/Target/Stoploss are algorithmic suggestions — use judgment.</li>
      <li>Factor weights: Momentum {run_metadata.get("weights_used", {}).get("momentum", "N/A")}, Trend Quality {run_metadata.get("weights_used", {}).get("trend_quality", "N/A")}, Mean Reversion {run_metadata.get("weights_used", {}).get("mean_reversion", "N/A")}, Quality {run_metadata.get("weights_used", {}).get("quality", "N/A")}</li>
      <li>Max 2 stocks per sector enforced. Stocks filtered: liquidity &lt; 25th percentile excluded.</li>
      <li>This is not investment advice. Always verify with your own analysis.</li>
    </ul>
  </div>

  <div class="footer">AI-Trader Swing Picks &bull; Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} &bull; Pipeline v1.0</div>
</div>
</body>
</html>'''

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)


def get_market_regime(conn):
    row = conn.execute(
        "SELECT regime, nifty_trend, breadth_ratio, vix_proxy FROM market_regime ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if row:
        return {"regime": row[0], "nifty_trend": row[1],
                "breadth_ratio": row[2], "vix_proxy": row[3]}
    return None


def get_data_freshness(conn):
    total = conn.execute("SELECT COUNT(DISTINCT symbol) FROM stocks").fetchone()[0]
    today = date.today().isoformat()
    fresh = conn.execute(
        "SELECT COUNT(DISTINCT symbol) FROM daily_ohlcv WHERE date = ?", (today,)
    ).fetchone()[0]
    pct = round(fresh / total * 100, 1) if total > 0 else 0
    return pct, fresh, total


def get_update_summary(conn):
    total = conn.execute("SELECT COUNT(DISTINCT symbol) FROM stocks").fetchone()[0]
    row = conn.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()
    through_date = row[0] if row else "unknown"
    return {"symbols_total": total, "data_through_date": through_date}


def run(ranked, rejected, run_ts, weights):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)

    market_regime = get_market_regime(conn)
    freshness_pct, fresh_count, total = get_data_freshness(conn)
    update_summary = get_update_summary(conn)
    conn.close()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    warnings = []
    if ranked and ranked[0]["composite"] < 60:
        warnings.append(f"Low conviction: top pick score only {ranked[0]['composite']:.1f}/100")
    sector_counts = {}
    for s in ranked:
        sec = s["sector"]
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    for sec, count in sector_counts.items():
        if count > 2:
            warnings.append(f"Sector concentration: {count} picks from {sec}")

    context = {
        "run_metadata": {
            "run_date": today,
            "pipeline_version": "1.0",
            "data_freshness_pct": freshness_pct,
            "symbols_total": total,
            "symbols_scored": len(ranked) + len(rejected),
            "symbols_filtered": len(rejected),
            "top_n": len(ranked),
            "weights_used": weights
        },
        "market_regime": market_regime,
        "top_picks": ranked,
        "filters_applied": {
            "min_liquidity_percentile": 25,
            "sector_cap": 2,
            "rejected": rejected
        },
        "factor_distribution": {},
        "update_summary": update_summary,
        "warnings": warnings
    }

    context_path = os.path.join(OUTPUT_DIR, f'context_{today}.json')
    with open(context_path, 'w') as f:
        json.dump(context, f, indent=2)

    html_path = os.path.join(OUTPUT_DIR, f'swing_report_{today}.html')
    generate_html_report(ranked, market_regime, context["run_metadata"], today, html_path)

    entry = {"stage": "report", "file": f"output/context_{today}.json",
             "size_kb": round(os.path.getsize(context_path) / 1024, 1),
             "ts": datetime.now().isoformat()}
    log(entry)
    entry = {"stage": "report", "file": f"output/swing_report_{today}.html",
             "size_kb": round(os.path.getsize(html_path) / 1024, 1),
             "ts": datetime.now().isoformat()}
    log(entry)
    entry = {"stage": "report", "status": "complete", "ts": datetime.now().isoformat()}
    log(entry)

    separator = "=" * 70
    regime_str = market_regime["regime"].replace("_", " ").title() if market_regime else "N/A"
    print()
    print(separator)
    print(f"  SWING PICKS -- {today} | Regime: {regime_str}")
    print(separator)
    print(f"  {'Rank':<5} {'Symbol':<18} {'Score':<8} {'Entry':<12} {'Target':<12} {'Stoploss':<12}")
    print(f"  {'-'*5} {'-'*18} {'-'*8} {'-'*12} {'-'*12} {'-'*12}")
    for s in ranked:
        print(f"  #{s['rank']:<4} {s['symbol']:<18} {s['composite']:<8.1f} Rs{s['entry_price']:<11,.2f} Rs{s['target_price']:<11,.2f} Rs{s['stoploss']:<11,.2f}")

    if warnings:
        print()
        print("  WARNINGS:")
        for w in warnings:
            print(f"  ! {w}")

    print()
    print(f"  Report: {html_path}")
    print(f"  Context: {context_path}")
    print(separator)

    return {"context_path": context_path, "html_path": html_path, "warnings": warnings}


if __name__ == '__main__':
    print("reporter.py is called via pipeline.py with ranked data. Use pipeline.py --full instead.")
