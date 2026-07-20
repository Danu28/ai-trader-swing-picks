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


def compute_position(capital, risk_pct, entry_price, stoploss):
    risk_amount = capital * (risk_pct / 100)
    risk_per_share = abs(entry_price - stoploss)
    if risk_per_share <= 0:
        return 0, 0
    shares = int(risk_amount / risk_per_share)
    position_value = shares * entry_price
    max_allowed = capital * 0.25
    if position_value > max_allowed:
        shares = int(max_allowed / entry_price)
        position_value = shares * entry_price
    if shares < 1:
        return 0, 0
    return shares, round(position_value, 2)


def generate_html_report(ranked, market_regime, run_metadata, today, report_path, capital=500000, risk_per_trade=1.0):
    picks_html = ""
    for s in ranked:
        fb = s.get("factor_breakdown", {})
        fd = s.get("factor_detail", {})
        top_drivers = sorted(fd.items(), key=lambda x: x[1], reverse=True)[:2]
        drivers_str = ", ".join(f"{k}: {v:.0f}" for k, v in top_drivers)
        score = s["composite"]
        bar_color = "#FBBF24" if score < 65 else "#38BDF8" if score < 70 else "#4ADE80"
        shares = compute_position(capital, risk_per_trade, s["entry_price"], s["stoploss"])[0]
        picks_html += f'''
    <tr>
      <td class="rank">#{s["rank"]}</td>
      <td class="symbol-cell"><strong>{s["symbol"]}</strong><br><span class="sector-label">{s["sector"]}</span></td>
      <td class="score-cell">
        <div class="score-bar-wrap">
          <div class="score-bar"><div class="score-fill" style="width:{score}%;background:{bar_color};"></div></div>
          <span class="score-num">{score:.1f}</span>
        </div>
      </td>
      <td class="price-cell">₹{s["entry_price"]:,.2f}</td>
      <td class="price-cell">{shares if shares > 0 else '—'}</td>
      <td class="price-cell target">₹{s["target_price"]:,.2f}</td>
      <td class="price-cell stoploss">₹{s["stoploss"]:,.2f}</td>
      <td class="drivers-cell"><span class="drivers-text">{drivers_str}</span></td>
    </tr>'''

    regime_str = market_regime.get("regime", "unknown").replace("_", " ").title() if market_regime else "N/A"
    regime_label = market_regime.get("regime", "unknown") if market_regime else "unknown"
    regime_emoji = {"risk_on": "[ON]", "risk_off": "[OFF]", "neutral": "[--]"}.get(
        regime_label, "[--]")

    nifty_trend = market_regime.get("nifty_trend", "N/A").title() if market_regime else "N/A"
    scored = run_metadata.get("symbols_scored", "N/A")
    freshness = run_metadata.get("data_freshness_pct", "N/A")
    weights = run_metadata.get("weights_used", {})
    picks_count = len(ranked)

    html = f'''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Swing Picks — {today}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #121314;
    --bg-card: #1A1B1E;
    --bg-card-hover: #1E1F22;
    --bg-table: #1A1B1E;
    --bg-table-alt: #1E1F22;
    --bg-header: #222327;
    --text-primary: #E2E8F0;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
    --border: #2A2B2D;
    --accent-green: #4ADE80;
    --accent-blue: #38BDF8;
    --accent-amber: #FBBF24;
    --accent-red: #EF4444;
    --shadow: 0 4px 20px -2px rgba(0,0,0,0.4);
    --radius: 12px;
    --radius-sm: 8px;
    --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
    --font-heading: 'Playfair Display', Georgia, serif;
    --font-mono: 'JetBrains Mono', 'Consolas', monospace;
    --transition: 0.2s ease;
  }}
  [data-theme="light"] {{
    --bg: #F8FAFC;
    --bg-card: #FFFFFF;
    --bg-card-hover: #F1F5F9;
    --bg-table: #FFFFFF;
    --bg-table-alt: #F8FAFC;
    --bg-header: #F1F5F9;
    --text-primary: #0F172A;
    --text-secondary: #475569;
    --text-muted: #94A3B8;
    --border: #E2E8F0;
    --shadow: 0 4px 20px -2px rgba(0,0,0,0.08);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: var(--font-sans);
    background: var(--bg);
    color: var(--text-primary);
    margin: 0;
    padding: 24px;
    line-height: 1.6;
    transition: background var(--transition), color var(--transition);
  }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{
    font-family: var(--font-heading);
    font-weight: 700;
    font-size: 2rem;
    margin: 0 0 2px;
    letter-spacing: -0.02em;
  }}
  .subtitle {{ color: var(--text-secondary); margin: 0 0 4px; font-size: 0.9rem; }}

  .header-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 16px;
  }}
  .theme-toggle {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 50%;
    width: 40px; height: 40px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; font-size: 1.1rem;
    transition: all var(--transition);
    flex-shrink: 0;
  }}
  .theme-toggle:hover {{ border-color: var(--text-muted); }}

  .sub-header {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 16px;
    margin-bottom: 20px;
    padding: 10px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: 0.85rem;
    color: var(--text-secondary);
  }}

  /* Executive summary grid */
  .exec-summary {{
    display: grid;
    grid-template-columns: 1.25fr 1fr;
    gap: 14px;
    margin-bottom: 14px;
  }}
  .summary-main {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
    justify-content: center;
  }}
  .summary-main .regime-row {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 14px;
  }}
  .market-details {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px 20px;
  }}
  .market-details .detail-item {{
    display: flex;
    flex-direction: column;
  }}
  .market-details .detail-label {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    font-weight: 600;
  }}
  .market-details .detail-value {{
    font-size: 1.05rem;
    font-weight: 600;
    font-family: var(--font-mono);
  }}

  .kpi-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }}
  .kpi-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
    justify-content: center;
  }}
  .kpi-value {{
    font-family: var(--font-heading);
    font-size: 1.9rem;
    font-weight: 700;
    line-height: 1.2;
    letter-spacing: -0.02em;
  }}
  .kpi-label {{
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    font-weight: 600;
    margin-top: 2px;
  }}

  /* Regime badges */
  .regime-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .badge-risk_on {{
    background: rgba(74,222,128,0.12);
    color: var(--accent-green);
    border: 1px solid rgba(74,222,128,0.3);
  }}
  .badge-risk_off {{
    background: rgba(239,68,68,0.12);
    color: var(--accent-red);
    border: 1px solid rgba(239,68,68,0.3);
  }}
  .badge-neutral, .badge-unknown {{
    background: rgba(251,191,36,0.12);
    color: var(--accent-amber);
    border: 1px solid rgba(251,191,36,0.3);
  }}

  /* Table */
  .table-wrap {{
    background: var(--bg-table);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow);
    margin-bottom: 24px;
  }}
  table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
  thead th {{
    background: var(--bg-header);
    color: var(--text-muted);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 10px 10px;
    text-align: left;
    font-weight: 600;
    white-space: nowrap;
    border-bottom: 1px solid var(--border);
  }}
  thead th.th-right {{ text-align: right; }}
  thead th.th-center {{ text-align: center; }}
  tbody tr {{ border-bottom: 1px solid var(--border); transition: background var(--transition); }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: var(--bg-card-hover); }}
  td {{
    padding: 10px;
    font-size: 0.85rem;
    vertical-align: middle;
  }}
  td.td-numeric {{
    text-align: right;
    font-family: var(--font-mono);
    font-size: 0.8rem;
  }}
  td.td-centered {{ text-align: center; }}

  .rank {{ color: var(--accent-blue); font-weight: 700; font-size: 1rem; }}
  .symbol-cell strong {{ font-weight: 600; }}
  .sector-label {{ color: var(--text-muted); font-size: 0.72rem; }}

  .score-cell {{ width: 130px; }}
  .score-bar-wrap {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .score-bar {{
    flex: 1;
    height: 5px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    min-width: 40px;
  }}
  .score-fill {{
    height: 100%;
    border-radius: 3px;
    transition: width 0.6s ease;
  }}
  .score-num {{
    font-family: var(--font-mono);
    font-size: 0.8rem;
    min-width: 2.2em;
    text-align: right;
    font-weight: 600;
  }}

  .price-cell {{
    font-family: var(--font-mono);
    text-align: right;
    font-size: 0.8rem;
  }}
  .price-cell.target {{ color: var(--accent-green); }}
  .price-cell.stoploss {{ color: var(--accent-red); }}

  .drivers-cell {{ font-size: 0.78rem; }}
  .drivers-text {{ color: var(--text-secondary); }}

  /* Notes box */
  .notes-box {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 22px;
    margin-bottom: 24px;
    box-shadow: var(--shadow);
  }}
  .notes-box h3 {{
    font-family: var(--font-sans);
    font-size: 0.95rem;
    font-weight: 600;
    margin: 0 0 10px;
    color: var(--text-primary);
  }}
  .notes-box ul {{
    margin: 0;
    padding-left: 20px;
    color: var(--text-secondary);
    font-size: 0.83rem;
    line-height: 1.7;
  }}
  .notes-box ul li {{ margin-bottom: 2px; }}

  .footer {{
    color: var(--text-muted);
    font-size: 0.7rem;
    text-align: center;
    padding: 16px 0 8px;
    border-top: 1px solid var(--border);
  }}

  @media (max-width: 768px) {{
    body {{ padding: 12px; }}
    h1 {{ font-size: 1.5rem; }}
    .exec-summary {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: 1fr 1fr; }}
    .table-wrap {{ overflow-x: auto; }}
  }}
  @media print {{
    body {{ background: #fff; color: #000; padding: 0; }}
    .theme-toggle {{ display: none; }}
    .table-wrap, .kpi-card, .summary-main, .notes-box {{ box-shadow: none; border: 1px solid #ccc; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header-row">
    <div>
      <h1>Swing Trade Picks</h1>
      <p class="subtitle">{today} — Universe: Nifty 50 + Midcap 150</p>
    </div>
    <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme">🌙</button>
  </div>

  <div class="sub-header">
    <span class="regime-badge badge-{regime_label}">{regime_emoji} {regime_str}</span>
    <span>Nifty Trend: <strong>{nifty_trend}</strong></span>
    <span>Stocks Scored: <strong>{scored}</strong></span>
    <span>Data Freshness: <strong>{freshness}%</strong></span>
    <span>Top Picks: <strong>{picks_count}</strong></span>
    <span class="sep">|</span> Position: ₹{capital:,.0f} × {risk_per_trade}% risk
  </div>

  <div class="exec-summary">
    <div class="summary-main">
      <div class="regime-row">
        <span class="regime-badge badge-{regime_label}" style="font-size:0.9rem;">{regime_emoji} {regime_str}</span>
      </div>
      <div class="market-details">
        <div class="detail-item">
          <span class="detail-label">Nifty Trend</span>
          <span class="detail-value">{nifty_trend}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Stocks Scored</span>
          <span class="detail-value">{scored}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Data Freshness</span>
          <span class="detail-value">{freshness}%</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Top Picks</span>
          <span class="detail-value">{picks_count}</span>
        </div>
      </div>
    </div>
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-value" style="color:var(--accent-green);">{scored}</div>
        <div class="kpi-label">Stocks Scored</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:{'var(--accent-green)' if isinstance(freshness, (int, float)) and freshness >= 80 else 'var(--accent-amber)'}">{freshness}%</div>
        <div class="kpi-label">Data Freshness</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:var(--accent-blue);">{picks_count}</div>
        <div class="kpi-label">Top Picks</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{nifty_trend}</div>
        <div class="kpi-label">Nifty Trend</div>
      </div>
    </div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="width:40px">Rank</th>
          <th>Symbol / Sector</th>
          <th style="width:140px">Score</th>
          <th style="width:95px" class="th-right">Entry</th>
          <th style="width:70px" class="th-right">Shares</th>
          <th style="width:95px" class="th-right">Target</th>
          <th style="width:95px" class="th-right">Stoploss</th>
          <th>Key Drivers</th>
        </tr>
      </thead>
      <tbody>{picks_html}
      </tbody>
    </table>
  </div>

  <div class="notes-box">
    <h3>Notes &amp; Warnings</h3>
    <ul>
      <li>All prices in INR. Entry/Target/Stoploss are algorithmic suggestions — use judgment.</li>
      <li>Factor weights: Momentum {weights.get("momentum", "N/A")}, Trend Quality {weights.get("trend_quality", "N/A")}, Mean Reversion {weights.get("mean_reversion", "N/A")}, Quality {weights.get("quality", "N/A")}</li>
      <li>Max 2 stocks per sector enforced. Stocks filtered: liquidity &lt; 25th percentile excluded.</li>
      <li>This is not investment advice. Always verify with your own analysis.</li>
    </ul>
  </div>

  <div class="footer">AI-Trader Swing Picks • Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} • Pipeline v1.0</div>
</div>
<script>
(function() {{
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', function() {{
    var html = document.documentElement;
    var isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    btn.textContent = isDark ? '\\u2600\\uFE0F' : '\\uD83C\\uDF19';
  }});
}})();
</script>
</body>
</html>'''

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)


def get_market_regime(conn):
    row = conn.execute(
        "SELECT regime, nifty_trend, breadth_ratio, vix_proxy, vix_20d_avg FROM market_regime ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if row:
        return {"regime": row[0], "nifty_trend": row[1],
                "breadth_ratio": row[2], "vix_proxy": row[3],
                "vix_20d_avg": row[4]}
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


def run(ranked, rejected, run_ts, weights, capital=100000, risk_per_trade=1.0):
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
    generate_html_report(ranked, market_regime, context["run_metadata"], today, html_path, capital=capital, risk_per_trade=risk_per_trade)

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

    # --- build header with VIX / spike info (matching backtest.py format) ---
    regime_label = market_regime["regime"] if market_regime else "unknown"
    regime_str = regime_label.replace("_", " ").upper()
    vix_proxy = market_regime.get("vix_proxy") if market_regime else None
    vix_20d_avg = market_regime.get("vix_20d_avg") if market_regime else None
    vix_proxy_str = f"{vix_proxy:.2f}" if vix_proxy is not None else "N/A"
    vix_20d_str = f"{vix_20d_avg:.2f}" if vix_20d_avg is not None else "N/A"

    spike_label = "No spike"
    if vix_proxy is not None and vix_20d_avg is not None and vix_20d_avg > 0:
        spike_ratio = vix_proxy / vix_20d_avg
        if spike_ratio > 1.5:
            spike_label = "!! SPIKE BLOCKED"

    header = f"  SWING PICKS -- {today} | Regime: {regime_str} | VIX: {vix_proxy_str}/{vix_20d_str} | {spike_label} | R:R 1:1"
    separator = "=" * len(header)
    print()
    print(separator)
    print(header)
    print(separator)
    print(f"  {'Rank':<5} {'Symbol':<18} {'Score':<8} {'Entry':<12} {'Shrs':<6} {'Target':<12} {'Stoploss':<12}")
    print(f"  {'-'*5} {'-'*18} {'-'*8} {'-'*12} {'-'*6} {'-'*12} {'-'*12}")
    for s in ranked:
        shares = compute_position(capital, risk_per_trade, s["entry_price"], s["stoploss"])[0]
        shares_str = str(shares) if shares > 0 else '—'
        print(f"  #{s['rank']:<4} {s['symbol']:<18} {s['composite']:<8.1f} Rs{s['entry_price']:<11,.2f} {shares_str:<6} Rs{s['target_price']:<11,.2f} Rs{s['stoploss']:<11,.2f}")

    print(f"  Position sizing: Rs{capital:,.0f} capital x {risk_per_trade}% risk per trade")

    if warnings:
        print()
        print("  WARNINGS:")
        for w in warnings:
            print(f"  ! {w}")

    print()
    print(f"  HTML Report: {html_path}")
    print(f"  Context: {context_path}")
    print(separator)

    return {"context_path": context_path, "html_path": html_path, "warnings": warnings}


if __name__ == '__main__':
    print("reporter.py is called via pipeline.py with ranked data. Use pipeline.py --full instead.")
