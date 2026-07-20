import sys
import os
import sqlite3
import json
import statistics
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factors import run as run_factors
from screener import run as run_screener, auto_weights, DEFAULT_WEIGHTS

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')

SECTOR_ABBR = {
    "Financial Services": "Fin Svc",
    "Metals & Mining": "Metals",
    "Consumer Durables": "Cons Dur",
    "Information Technology": "IT",
    "Pharmaceuticals": "Pharma",
    "Telecommunication": "Telecom",
    "Construction": "Constr",
    "Automobile": "Auto",
    "Healthcare": "Health",
    "Consumer Services": "Cons Svc",
    "Capital Goods": "Cap Good",
    "Services": "Service",
    "Chemicals": "Chem",
    "Fertilisers & Pesticides": "FertChem",
    "Media & Entertainment": "Media",
    "Oil & Gas": "Oil&Gas",
}


def check_forward(conn, symbol, as_of_date, entry_price, target_price, stoploss):
    # Verify entry was fillable on last trading day <= signal date
    entry_row = conn.execute(
        "SELECT date, high, low, close FROM daily_ohlcv WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (symbol, as_of_date)
    ).fetchone()

    entry_filled = False
    entry_actual_date = as_of_date
    if entry_row:
        entry_actual_date, day_high, day_low, day_close = entry_row[0], float(entry_row[1]), float(entry_row[2]), float(entry_row[3])
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
        "entry_filled": entry_filled,
        "entry_actual_date": entry_actual_date
    }


def generate_backtest_html(as_of_date, regime_label, breadth, vix_proxy, vix_20d_avg,
                           spike_label, spike_ratio, spike_blocked, rows, summary,
                           below_threshold_count=0, above_max_count=0,
                           starting_capital=500000, cost_model=0.25, rr_ratio=1.5):
    """Generate standalone HTML backtest report with beautiful-reports design system."""
    vix_proxy_str = f"{vix_proxy:.2f}" if vix_proxy is not None else "N/A"
    vix_20d_str = f"{vix_20d_avg:.2f}" if vix_20d_avg is not None else "N/A"
    regime_display = regime_label.replace("_", " ").upper()
    regime_emoji = {"risk_on": "[ON]", "risk_off": "[OFF]", "neutral": "[--]"}.get(regime_label, "[--]")

    # KPI values
    win_rate_str = f"{summary['win_rate']:.0f}%" if summary else "N/A"
    total_return_str = f"{summary['total_return']:+.2f}%" if summary else "N/A"
    net_return_str = f"{summary['total_return_pct']:+.2f}%" if summary and 'total_return_pct' in summary else total_return_str
    final_capital_str = f"₹{summary['final_capital']:,.0f}" if summary and 'final_capital' in summary else "N/A"
    sharpe_str = f"{summary['sharpe']:.2f}" if summary and 'sharpe' in summary else "N/A"
    max_dd_str = f"{summary['max_drawdown']:.1f}%" if summary and 'max_drawdown' in summary else "N/A"
    avg_return_str = f"{summary['avg_return']:+.2f}%" if summary else "N/A"
    avg_hold_str = f"{summary['avg_hold']:.1f}" if summary else "N/A"
    wins = summary['wins'] if summary else 0
    losses = summary['losses'] if summary else 0
    draws = summary['draws'] if summary else 0
    total_trades = wins + losses + draws
    wins_pct = round(wins / total_trades * 100) if total_trades > 0 else 0
    losses_pct = round(losses / total_trades * 100) if total_trades > 0 else 0
    draws_pct = max(100 - wins_pct - losses_pct, 0) if total_trades > 0 else 0

    # Filter info
    filter_parts = []
    if below_threshold_count > 0:
        filter_parts.append(f"{below_threshold_count} below min")
    if above_max_count > 0:
        filter_parts.append(f"{above_max_count} above max")
    filtered_str = ", ".join(filter_parts)
    score_filter_info = f"Score range: 60–75" + (f" ({filtered_str} filtered)" if filtered_str else "")

    # Build table rows
    table_rows_html = ""
    if rows:
        for r in rows:
            sec = SECTOR_ABBR.get(r["sector"], r["sector"][:8])
            fill_char = "Y" if r["entry_filled"] else "N"
            tgt_date_str = str(r["target_date"]) if r["target_date"] else "--"
            sl_date_str = str(r["sl_date"]) if r["sl_date"] else "--"

            result_lower = r["result"].lower()
            score = r["score"]
            # Score bar color gradient: amber < 65, blue 65-69, green >= 70
            bar_color = "#FBBF24" if score < 65 else "#38BDF8" if score < 70 else "#4ADE80"

            table_rows_html += f'''
        <tr class="result-{result_lower}">
          <td class="rank">#{r["rank"]}</td>
          <td class="symbol-cell"><strong>{r["symbol"]}</strong><br><span class="sector-label">{sec}</span></td>
          <td class="score-cell">
            <div class="score-bar-wrap">
              <div class="score-bar"><div class="score-fill" style="width:{score}%;background:{bar_color};"></div></div>
              <span class="score-num">{score:.1f}</span>
            </div>
          </td>
          <td class="date-cell">{r["entry_date"]}</td>
          <td class="price-cell">₹{r["entry"]:,.2f}</td>
          <td class="td-numeric">{r["shares"]}</td>
          <td class="price-cell target">₹{r["target"]:,.2f}</td>
          <td class="price-cell stoploss">₹{r["sl"]:,.2f}</td>
          <td class="td-centered">{fill_char}</td>
          <td class="td-centered"><span class="result-badge {r["result"]}">{r["result"]}</span></td>
          <td class="td-numeric return-cell {result_lower}">{r["return_pct"]:+.2f}%</td>
          <td class="td-numeric">{r["hold_days"]}</td>
          <td class="date-cell">{tgt_date_str}</td>
          <td class="date-cell">{sl_date_str}</td>
        </tr>'''

    # Summary row
    summary_html = ""
    if summary:
        net_ret = summary.get("total_return_pct", summary["total_return"])
        fin_cap = summary.get("final_capital", 0)
        shrp = summary.get("sharpe", 0)
        mdd = summary.get("max_drawdown", 0)
        costs_total = summary.get("total_costs", 0)
        summary_html = f'''
      <tr class="summary-row">
        <td colspan="14">
          <strong>Net Return: {net_ret:+.2f}%</strong> &nbsp;|&nbsp;
          Final Capital: ₹{fin_cap:,.0f} &nbsp;|&nbsp;
          Sharpe: {shrp:.2f} &nbsp;|&nbsp;
          Max DD: {mdd:.1f}% &nbsp;|&nbsp;
          Win Rate: {summary["win_rate"]:.0f}% &nbsp;|&nbsp;
          Avg Hold: {summary["avg_hold"]:.1f}d &nbsp;|&nbsp;
          Costs: ₹{costs_total:,.0f} &nbsp;|&nbsp;
          W:{summary["wins"]} L:{summary["losses"]} D:{summary["draws"]}
        </td>
      </tr>'''

    # Warning for spike-blocked case
    warning_html = ""
    if spike_blocked:
        warning_html = f'''
    <div class="warning-box">
      <h3>⚠ Volatility Spike Detected — No Trades Executed</h3>
      <ul>
        <li>VIX proxy: {vix_proxy_str} | 20-day avg: {vix_20d_str} | Spike ratio: {spike_ratio:.2f}x</li>
        <li>Skipping picks — high risk of stop-outs during regime transition.</li>
        <li>No trades on {as_of_date}.</li>
      </ul>
    </div>'''

    table_section = "" if spike_blocked else f'''
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="width:36px">#</th>
          <th>Symbol</th>
          <th style="width:130px">Score</th>
          <th>Date</th>
          <th style="width:92px" class="th-right">Entry</th>
          <th style="width:60px" class="th-right">Shares</th>
          <th style="width:92px" class="th-right">Target</th>
          <th style="width:92px" class="th-right">SL</th>
          <th style="width:28px" class="th-center">F</th>
          <th style="width:60px" class="th-center">Result</th>
          <th style="width:78px" class="th-right">Ret%</th>
          <th style="width:46px" class="th-right">Days</th>
          <th>Tgt Hit</th>
          <th>SL Hit</th>
        </tr>
      </thead>
      <tbody>{table_rows_html}
{summary_html}
      </tbody>
    </table>
  </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest Report — {as_of_date}</title>
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
    --accent-win-bg: rgba(74,222,128,0.10);
    --accent-loss-bg: rgba(239,68,68,0.10);
    --accent-draw-bg: rgba(251,191,36,0.10);
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
  .container {{ max-width: 1280px; margin: 0 auto; }}
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
  .sub-header .filter-note {{ color: var(--text-muted); font-size: 0.8rem; }}

  /* Warning box */
  .warning-box {{
    background: rgba(251,191,36,0.08);
    border: 1px solid rgba(251,191,36,0.25);
    border-radius: var(--radius);
    padding: 16px 20px;
    margin-bottom: 24px;
  }}
  .warning-box h3 {{
    color: var(--accent-amber);
    font-family: var(--font-sans);
    margin: 0 0 8px;
    font-size: 0.95rem;
    font-weight: 600;
  }}
  .warning-box ul {{ margin: 0; padding-left: 20px; color: var(--text-secondary); font-size: 0.85rem; }}

  /* Executive summary grid — asymmetric */
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

  /* KPI grid — 2x2 */
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

  /* Trade stats bar */
  .trade-stats-bar {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 18px;
    box-shadow: var(--shadow);
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    font-size: 0.85rem;
    margin-bottom: 24px;
  }}
  .trade-stat-item {{
    display: flex;
    align-items: center;
    gap: 5px;
  }}
  .trade-stat-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
  }}
  .trade-stat-label {{ color: var(--text-secondary); }}
  .trade-stat-count {{ font-weight: 700; }}
  .dist-bar-wrap {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
  }}
  .dist-bar {{
    display: flex;
    height: 14px;
    border-radius: 7px;
    overflow: hidden;
    min-width: 100px;
    background: var(--border);
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
    padding: 10px 8px;
    text-align: left;
    font-weight: 600;
    white-space: nowrap;
    border-bottom: 1px solid var(--border);
  }}
  thead th.th-right {{ text-align: right; }}
  thead th.th-center {{ text-align: center; }}
  tbody tr {{ border-bottom: 1px solid var(--border); }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr.result-win {{ background: rgba(74,222,128,0.03); }}
  tbody tr.result-loss {{ background: rgba(239,68,68,0.03); }}
  tbody tr.result-draw {{ background: rgba(251,191,36,0.03); }}
  tbody tr:hover {{ background: var(--bg-card-hover); }}
  td {{
    padding: 8px;
    font-size: 0.83rem;
    vertical-align: middle;
  }}
  td.td-numeric {{
    text-align: right;
    font-family: var(--font-mono);
    font-size: 0.8rem;
  }}
  td.td-centered {{ text-align: center; }}

  .rank {{ color: var(--accent-blue); font-weight: 700; }}
  .symbol-cell strong {{ font-weight: 600; }}
  .sector-label {{ color: var(--text-muted); font-size: 0.72rem; }}

  .score-cell {{ width: 120px; }}
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
    min-width: 36px;
  }}
  .score-fill {{
    height: 100%;
    border-radius: 3px;
    transition: width 0.6s ease;
  }}
  .score-num {{
    font-family: var(--font-mono);
    font-size: 0.78rem;
    min-width: 2.2em;
    text-align: right;
    font-weight: 600;
  }}

  .price-cell {{
    font-family: var(--font-mono);
    text-align: right;
    font-size: 0.78rem;
  }}
  .price-cell.target {{ color: var(--accent-green); }}
  .price-cell.stoploss {{ color: var(--accent-red); }}
  .date-cell {{ font-size: 0.78rem; color: var(--text-secondary); }}

  .result-badge {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .result-badge.WIN {{ background: rgba(74,222,128,0.15); color: var(--accent-green); }}
  .result-badge.LOSS {{ background: rgba(239,68,68,0.15); color: var(--accent-red); }}
  .result-badge.DRAW {{ background: rgba(251,191,36,0.15); color: var(--accent-amber); }}
  .return-cell.win {{ color: var(--accent-green); }}
  .return-cell.loss {{ color: var(--accent-red); }}
  .return-cell.draw {{ color: var(--accent-amber); }}

  .summary-row td {{
    background: var(--bg-header);
    border-top: 2px solid var(--border);
    padding: 12px 16px;
    text-align: center;
    font-size: 0.85rem;
  }}

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
    .dist-bar-wrap {{ margin-left: 0; }}
  }}
  @media print {{
    body {{ background: #fff; color: #000; padding: 0; }}
    .theme-toggle {{ display: none; }}
    .table-wrap, .kpi-card, .summary-main, .trade-stats-bar, .warning-box {{ box-shadow: none; border: 1px solid #ccc; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header-row">
    <div>
      <h1>Backtest Report</h1>
      <p class="subtitle">{as_of_date}</p>
    </div>
    <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme">🌙</button>
  </div>

  <div class="sub-header">
    <span class="regime-badge badge-{regime_label}">{regime_emoji} {regime_display}</span>
    <span>Breadth: <strong>{breadth}</strong></span>
    <span>VIX: <strong>{vix_proxy_str}</strong> | 20d Avg: <strong>{vix_20d_str}</strong></span>
    <span>{spike_label}</span>
    <span>R:R {rr_ratio}:1 | Capital: ₹{starting_capital:,.0f} | Cost: {cost_model}%</span>
    <span class="filter-note">{score_filter_info}</span>
  </div>

  {warning_html}

  <div class="exec-summary">
    <div class="summary-main">
      <div class="regime-row">
        <span class="regime-badge badge-{regime_label}" style="font-size:0.9rem;">{regime_emoji} {regime_display}</span>
      </div>
      <div class="market-details">
        <div class="detail-item">
          <span class="detail-label">Breadth Ratio</span>
          <span class="detail-value">{breadth}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">VIX Proxy</span>
          <span class="detail-value">{vix_proxy_str}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">VIX 20d Avg</span>
          <span class="detail-value">{vix_20d_str}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">Spike Status</span>
          <span class="detail-value">{spike_label}</span>
        </div>
      </div>
    </div>
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-value" style="color:{'var(--accent-green)' if summary and summary['win_rate'] >= 50 else 'var(--accent-red)' if summary else 'var(--text-primary)'}">{win_rate_str}</div>
        <div class="kpi-label">Win Rate</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:{'var(--accent-green)' if summary and summary.get('total_return_pct', summary.get('total_return', 0)) >= 0 else 'var(--accent-red)' if summary else 'var(--text-primary)'}">{net_return_str}</div>
        <div class="kpi-label">Net Return (after costs)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="font-size:1.5rem;">{final_capital_str}</div>
        <div class="kpi-label">Final Capital</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{sharpe_str}</div>
        <div class="kpi-label">Sharpe Ratio</div>
      </div>
    </div>
  </div>

  {f'''
  <div class="trade-stats-bar">
    <div class="trade-stat-item">
      <span class="trade-stat-dot" style="background:var(--accent-green);"></span>
      <span class="trade-stat-label">Wins:</span>
      <span class="trade-stat-count" style="color:var(--accent-green);">{wins}</span>
    </div>
    <div class="trade-stat-item">
      <span class="trade-stat-dot" style="background:var(--accent-red);"></span>
      <span class="trade-stat-label">Losses:</span>
      <span class="trade-stat-count" style="color:var(--accent-red);">{losses}</span>
    </div>
    <div class="trade-stat-item">
      <span class="trade-stat-dot" style="background:var(--accent-amber);"></span>
      <span class="trade-stat-label">Draws:</span>
      <span class="trade-stat-count" style="color:var(--accent-amber);">{draws}</span>
    </div>
    <div class="dist-bar-wrap">
      <span style="font-size:0.73rem;color:var(--text-muted);">W/L/D</span>
      <div class="dist-bar">
        <div style="flex:{max(wins_pct,1)};background:var(--accent-green);"></div>
        <div style="flex:{max(losses_pct,1)};background:var(--accent-red);"></div>
        <div style="flex:{max(draws_pct,1)};background:var(--accent-amber);"></div>
      </div>
    </div>
  </div>''' if summary else ''}

  {table_section}

  <div class="footer">AI-Trader Swing Picks — Backtest • Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} • Pipeline v1.0</div>
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

    report_path = os.path.join(OUTPUT_DIR, f'backtest_{as_of_date}.html')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return report_path


RR_REGIME_MAP = {
    "risk_on": 1.5,
    "neutral": 1.5,
    "risk_off": 1.0,
}


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
    return shares, position_value


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', type=str, required=True, help='Backtest date YYYY-MM-DD')
    parser.add_argument('--top', type=int, default=5)
    parser.add_argument('--weights', type=str, default=None)
    parser.add_argument('--no-regime-gate', action='store_true',
                        help='Skip regime-based weight override; use default weights')
    parser.add_argument('--capital', type=float, default=500000,
                        help='Starting capital in INR (default: 500000)')
    parser.add_argument('--risk-per-trade', type=float, default=1.0,
                        help='Risk per trade as %% of capital (default: 1.0)')
    parser.add_argument('--cost-model', type=float, default=0.25,
                        help='Round-trip cost as %% of trade value (default: 0.25)')
    parser.add_argument('--rr-ratio', type=float, default=None,
                        help='Risk-reward ratio. If not set, uses regime-dependent defaults')
    args = parser.parse_args()

    as_of_date = args.as_of
    top_n = args.top
    starting_capital = args.capital
    risk_per_trade = args.risk_per_trade
    cost_model = args.cost_model

    print(f"\n[1/3] Computing factors as of {as_of_date}...")
    factor_result = run_factors(as_of_date=as_of_date)
    regime = factor_result.get("regime", {})
    regime_label = regime.get("regime", "unknown")

    breadth = regime.get('breadth_ratio', '?') if regime else '?'
    vix_proxy = regime.get('vix_proxy') if regime else None
    vix_20d_avg = regime.get('vix_20d_avg') if regime else None

    # Determine effective R:R ratio
    if args.rr_ratio is not None:
        rr_ratio = args.rr_ratio
    else:
        rr_ratio = RR_REGIME_MAP.get(regime_label, 1.5)

    # Compute spike ratio before header
    spike_ratio = None
    spike_label = "No spike"
    if vix_proxy is not None and vix_20d_avg is not None and vix_20d_avg > 0:
        spike_ratio = round(vix_proxy / vix_20d_avg, 2)
        if spike_ratio > 1.5:
            spike_label = "!! SPIKE BLOCKED"

    header = f"  BACKTEST -- As-of: {as_of_date} | Regime: {regime_label.replace('_',' ').upper()} | VIX: {vix_proxy}/{vix_20d_avg} | {spike_label} | R:R {rr_ratio}:1"
    sep = "=" * len(header)
    print(sep)
    print(header)
    print(sep)

    # VIX spike safety check
    if spike_ratio is not None and spike_ratio > 1.5:
        print(f"\n*** VOLATILITY SPIKE DETECTED ***")
        print(f"    VIX proxy: {vix_proxy} | 20-day avg: {vix_20d_avg} | Spike ratio: {spike_ratio:.2f}x")
        print(f"    Skipping picks -- high risk of stop-outs during regime transition.")
        print(f"    No trades on {as_of_date}.\n")
        print(json.dumps({"stage": "backtest", "status": "volatility_spike_skipped",
                            "as_of_date": as_of_date, "vix_proxy": vix_proxy,
                            "vix_20d_avg": vix_20d_avg,
                            "spike_ratio": spike_ratio,
                            "ts": datetime.now().isoformat()}))
        report_path = generate_backtest_html(
            as_of_date, regime_label, breadth, vix_proxy, vix_20d_avg,
            spike_label, spike_ratio, spike_blocked=True, rows=[], summary=None,
            below_threshold_count=0, above_max_count=0,
            starting_capital=starting_capital, cost_model=cost_model, rr_ratio=rr_ratio
        )
        print(f"\n  HTML Report: {report_path}")
        return

    if args.weights:
        weights = dict(DEFAULT_WEIGHTS)
        for pair in args.weights.split(','):
            k, v = pair.split('=')
            weights[k.strip()] = float(v.strip())
    elif args.no_regime_gate:
        weights = dict(DEFAULT_WEIGHTS)
    else:
        weights = auto_weights(regime_label)

    screen_result = run_screener(top_n=top_n, weights=weights, as_of_date=as_of_date, rr_ratio=rr_ratio)
    ranked = screen_result["ranked"]

    if not ranked:
        below_threshold_count = len(screen_result.get("below_threshold", []))
        above_max_count = len(screen_result.get("above_max", []))
        if below_threshold_count > 0 or above_max_count > 0:
            parts = []
            if below_threshold_count > 0:
                parts.append(f"{below_threshold_count} below min")
            if above_max_count > 0:
                parts.append(f"{above_max_count} above max")
            print(f"  Score range: 60-75 | {', '.join(parts)} filtered")
        print("      No picks found.")
        return

    below_threshold_count = len(screen_result.get("below_threshold", []))
    above_max_count = len(screen_result.get("above_max", []))
    if below_threshold_count > 0 or above_max_count > 0:
        parts = []
        if below_threshold_count > 0:
            parts.append(f"{below_threshold_count} below min")
        if above_max_count > 0:
            parts.append(f"{above_max_count} above max")
        print(f"  Score range: 60-75 | {', '.join(parts)} filtered")

    conn = sqlite3.connect(DB_PATH)

    capital = starting_capital
    equity_curve = [capital]

    rows = []
    for s in ranked:
        result, detail, stats = check_forward(
            conn, s["symbol"], as_of_date,
            s["entry_price"], s["target_price"], s["stoploss"]
        )

        # Compute position size — skip if can't afford even 1 share
        shares, position_value = compute_position(capital, risk_per_trade, s["entry_price"], s["stoploss"])
        if shares == 0:
            entry_skip = {"stage": "backtest", "symbol": s["symbol"], "action": "skipped",
                          "reason": "affordability", "entry_price": s["entry_price"],
                          "capital": round(capital, 2), "ts": datetime.now().isoformat()}
            print(json.dumps(entry_skip))
            continue

        # Determine exit price and compute P&L
        if result == "WIN":
            exit_price = s["target_price"]
            return_pct = round((s["target_price"] - s["entry_price"]) / s["entry_price"] * 100, 2)
        elif result == "LOSS":
            exit_price = s["stoploss"]
            return_pct = round((s["stoploss"] - s["entry_price"]) / s["entry_price"] * 100, 2)
        else:
            exit_price = stats["end_close"]
            return_pct = round((stats["end_close"] - s["entry_price"]) / s["entry_price"] * 100, 2)

        # Compute P&L and costs
        pnl_gross = shares * (exit_price - s["entry_price"])
        costs = (s["entry_price"] * shares + exit_price * shares) * (cost_model / 200)
        pnl_net = pnl_gross - costs

        capital += pnl_net
        equity_curve.append(capital)

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

        rows.append({
            "rank": s["rank"],
            "symbol": s["symbol"].replace(".NS", ""),
            "score": round(s["composite"], 1),
            "sector": s["sector"],
            "entry_date": str(stats["entry_actual_date"]),
            "entry": s["entry_price"],
            "entry_filled": stats["entry_filled"],
            "target_date": stats["hit_target_date"] or None,
            "target": s["target_price"],
            "sl_date": stats["hit_sl_date"] or None,
            "sl": s["stoploss"],
            "result": result,
            "return_pct": return_pct,
            "hold_days": hold_days,
            "shares": shares,
            "position_value": round(position_value, 2),
            "pnl_gross": round(pnl_gross, 2),
            "pnl_net": round(pnl_net, 2),
            "costs": round(costs, 2),
            "capital_after": round(capital, 2),
        })

    conn.close()

    # ANSI colors
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

    # Build table
    hdr = (f"{'#':<3}  {'Symbol':<14}  {'Score':>5}  {'Sector':<8}  {'Date':<10}  "
           f"{'Entry':>8}  {'Shrs':>5}  {'Target':>8}  {'SL':>8}  {'F':1}  {'Res':5}  "
           f"{'Ret%':>7}  {'Days':>5}  {'Tgt Hit':<10}  {'SL Hit':<10}")
    sep = "-" * len(hdr)
    print(f"\n{sep}")
    print(hdr)
    print(sep)

    wins = losses = draws = 0
    for r in rows:
        sec = SECTOR_ABBR.get(r["sector"], r["sector"][:8])
        fill_char = "Y" if r["entry_filled"] else "N"
        tgt_date_str = str(r["target_date"]) if r["target_date"] else "--"
        sl_date_str = str(r["sl_date"]) if r["sl_date"] else "--"

        row_str = (f"{r['rank']:<3}  {r['symbol']:<14}  {r['score']:>5.1f}  {sec:<8}  "
                   f"{r['entry_date']:<10}  {r['entry']:>8.2f}  {r['shares']:>5}  {r['target']:>8.2f}  "
                   f"{r['sl']:>8.2f}  {fill_char:1}  {r['result']:5}  "
                   f"{r['return_pct']:>+6.2f}%  {r['hold_days']:>5}  "
                   f"{tgt_date_str:<10}  {sl_date_str:<10}")

        if r["result"] == "WIN":
            color = GREEN
            wins += 1
        elif r["result"] == "LOSS":
            color = RED
            losses += 1
        else:
            color = YELLOW
            draws += 1
        print(f"{color}{row_str}{RESET}")

    print(sep)

    # Summary
    hit_rate = wins / len(ranked) * 100 if len(ranked) > 0 else 0
    total_return = sum(r["return_pct"] for r in rows)
    avg_return = total_return / len(rows) if rows else 0
    avg_hold = sum(r["hold_days"] for r in rows) / len(rows) if rows else 0
    total_costs = sum(r["costs"] for r in rows)
    final_capital = equity_curve[-1] if equity_curve else starting_capital
    total_return_pct = (final_capital - starting_capital) / starting_capital * 100

    # Sharpe: annualized from trade returns
    trade_returns = [r["return_pct"] for r in rows if r["return_pct"] != 0] if rows else [0]
    sharpe = 0.0
    if len(trade_returns) > 1 and statistics.stdev(trade_returns) > 0:
        sharpe = round((252 ** 0.5) * statistics.mean(trade_returns) / statistics.stdev(trade_returns), 2)

    # Max drawdown from equity curve
    max_dd = 0.0
    peak = equity_curve[0]
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd

    summary = (f"Total Return: {total_return:+.2f}% | Net Return: {total_return_pct:+.2f}% | "
               f"Final Capital: Rs{final_capital:,.2f} | "
               f"Sharpe: {sharpe:.2f} | Max DD: {max_dd:.1f}% | "
               f"Win Rate: {hit_rate:.0f}% | Costs: Rs{total_costs:,.2f}")
    print(f"{BOLD}{summary}{RESET}")

    summary_dict = {
        "total_return": total_return, "avg_return": avg_return,
        "win_rate": hit_rate, "avg_hold": avg_hold,
        "wins": wins, "losses": losses, "draws": draws,
        "total_return_pct": round(total_return_pct, 2),
        "final_capital": round(final_capital, 2),
        "total_costs": round(total_costs, 2),
        "sharpe": sharpe,
        "max_drawdown": round(max_dd, 2),
    }
    report_path = generate_backtest_html(
        as_of_date, regime_label, breadth, vix_proxy, vix_20d_avg,
        spike_label, spike_ratio, spike_blocked=False, rows=rows, summary=summary_dict,
        below_threshold_count=below_threshold_count, above_max_count=above_max_count,
        starting_capital=starting_capital, cost_model=cost_model, rr_ratio=rr_ratio
    )
    print(f"\n  HTML Report: {report_path}")


if __name__ == '__main__':
    main()
