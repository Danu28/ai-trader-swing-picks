import sys
import os
import sqlite3
import json
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factors import run as run_factors
from screener import run as run_screener

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
                           below_threshold_count=0):
    """Generate standalone HTML backtest report matching reporter.py dark theme."""
    vix_proxy_str = f"{vix_proxy:.2f}" if vix_proxy is not None else "N/A"
    vix_20d_str = f"{vix_20d_avg:.2f}" if vix_20d_avg is not None else "N/A"

    # Build table rows
    table_rows_html = ""
    if rows:
        for r in rows:
            sec = SECTOR_ABBR.get(r["sector"], r["sector"][:8])
            fill_char = "Y" if r["entry_filled"] else "N"
            tgt_date_str = str(r["target_date"]) if r["target_date"] else "--"
            sl_date_str = str(r["sl_date"]) if r["sl_date"] else "--"

            if r["result"] == "WIN":
                row_class = "result-win"
                result_color = "#3fb950"
            elif r["result"] == "LOSS":
                row_class = "result-loss"
                result_color = "#f85149"
            else:
                row_class = "result-draw"
                result_color = "#d29922"

            score_color = "#3fb950" if r["score"] >= 70 else "#c9d1d9"
            table_rows_html += f'''
        <tr class="{row_class}">
          <td class="rank">#{r["rank"]}</td>
          <td><strong>{r["symbol"]}</strong><br><small>{sec}</small></td>
          <td style="text-align:right;color:{score_color};">{r["score"]:.1f}</td>
          <td>{r["entry_date"]}</td>
          <td class="price">₹{r["entry"]:,.2f}</td>
          <td class="price target">₹{r["target"]:,.2f}</td>
          <td class="price stoploss">₹{r["sl"]:,.2f}</td>
          <td>{fill_char}</td>
          <td style="color:{result_color};font-weight:600;">{r["result"]}</td>
          <td style="color:{result_color};">{r["return_pct"]:+.2f}%</td>
          <td>{r["hold_days"]}</td>
          <td>{tgt_date_str}</td>
          <td>{sl_date_str}</td>
        </tr>'''

    # Summary row
    summary_html = ""
    if summary:
        summary_html = f'''
      <tr class="summary-row">
        <td colspan="13">
          <strong>Total Return: {summary["total_return"]:+.2f}%</strong> &nbsp;|&nbsp;
          Avg Return: {summary["avg_return"]:+.2f}% &nbsp;|&nbsp;
          Win Rate: {summary["win_rate"]:.0f}% &nbsp;|&nbsp;
          Avg Hold Days: {summary["avg_hold"]:.1f} &nbsp;|&nbsp;
          Wins: {summary["wins"]} &nbsp;|&nbsp; Losses: {summary["losses"]} &nbsp;|&nbsp; Draws: {summary["draws"]}
        </td>
      </tr>'''

    # Warning banner for spike-blocked case
    warning_html = ""
    if spike_blocked:
        warning_html = f'''
    <div class="warnings">
      <h3>Volatility Spike Detected &mdash; No Trades Executed</h3>
      <ul>
        <li>VIX proxy: {vix_proxy_str} | 20-day avg: {vix_20d_str} | Spike ratio: {spike_ratio:.2f}x</li>
        <li>Skipping picks &mdash; high risk of stop-outs during regime transition.</li>
        <li>No trades on {as_of_date}.</li>
      </ul>
    </div>'''

    # Meta cards
    win_rate_str = f"{summary['win_rate']:.0f}%" if summary else "N/A"
    total_return_str = f"{summary['total_return']:+.2f}%" if summary else "N/A"
    regime_emoji = {"risk_on": "[ON]", "risk_off": "[OFF]", "neutral": "[--]"}.get(regime_label, "[--]")
    regime_display = regime_label.replace("_", " ").upper()

    filter_info = f" &nbsp;|&nbsp; Score filter: &ge;70 ({below_threshold_count} filtered)" if below_threshold_count > 0 else ""

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest Report &mdash; {as_of_date}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; font-size: 1.8em; margin-bottom: 4px; }}
  .subtitle {{ color: #8b949e; margin-bottom: 24px; }}
  .meta {{ display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 20px; }}
  .meta-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; flex: 1; min-width: 120px; }}
  .meta-card .label {{ color: #8b949e; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.05em; }}
  .meta-card .value {{ color: #c9d1d9; font-size: 1.2em; font-weight: 600; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }}
  th {{ background: #21262d; color: #8b949e; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 10px; text-align: left; }}
  td {{ padding: 10px; border-top: 1px solid #21262d; font-size: 0.9em; }}
  .rank {{ color: #58a6ff; font-weight: 700; }}
  .price {{ font-family: 'JetBrains Mono', 'Consolas', monospace; }}
  .target {{ color: #3fb950; }}
  .stoploss {{ color: #f85149; }}
  .result-win {{ background: rgba(63, 185, 80, 0.06); }}
  .result-loss {{ background: rgba(248, 81, 73, 0.06); }}
  .result-draw {{ background: rgba(210, 153, 34, 0.06); }}
  .summary-row td {{ background: #21262d; color: #c9d1d9; font-size: 0.9em; padding: 12px; border-top: 2px solid #30363d; text-align: center; }}
  .warnings {{ background: #1a1a0a; border: 1px solid #d29922; border-radius: 8px; padding: 16px; margin: 20px 0; }}
  .warnings h3 {{ color: #d29922; margin-top: 0; }}
  .warnings ul {{ margin: 0; padding-left: 20px; color: #e3b341; }}
  .footer {{ color: #484f58; font-size: 0.75em; text-align: center; margin-top: 30px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Backtest Report</h1>
  <p class="subtitle">{as_of_date} &nbsp;|&nbsp; Regime: {regime_emoji} {regime_display} &nbsp;|&nbsp; VIX: {vix_proxy_str}/{vix_20d_str} &nbsp;|&nbsp; {spike_label} &nbsp;|&nbsp; R:R 1:1{filter_info}</p>

  <div class="meta">
    <div class="meta-card"><div class="label">Regime</div><div class="value">{regime_emoji} {regime_display}</div></div>
    <div class="meta-card"><div class="label">Breadth</div><div class="value">{breadth}</div></div>
    <div class="meta-card"><div class="label">VIX Proxy</div><div class="value">{vix_proxy_str}</div></div>
    <div class="meta-card"><div class="label">VIX 20d Avg</div><div class="value">{vix_20d_str}</div></div>
    <div class="meta-card"><div class="label">Win Rate</div><div class="value">{win_rate_str}</div></div>
    <div class="meta-card"><div class="label">Total Return</div><div class="value">{total_return_str}</div></div>
    <div class="meta-card"><div class="label">R:R</div><div class="value">1:1</div></div>
  </div>
{warning_html}
{f'''  <table>
    <thead>
       <tr><th>#</th><th>Symbol</th><th>Score</th><th>Date</th><th>Entry</th><th>Target</th><th>SL</th><th>F</th><th>Result</th><th>Ret%</th><th>Days</th><th>Tgt Hit</th><th>SL Hit</th></tr>
    </thead>
    <tbody>{table_rows_html}
{summary_html}
    </tbody>
  </table>''' if not spike_blocked else ''}

  <div class="footer">AI-Trader Swing Picks &mdash; Backtest &bull; Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} &bull; Pipeline v1.0</div>
</div>
</body>
</html>'''

    report_path = os.path.join(OUTPUT_DIR, f'backtest_{as_of_date}.html')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return report_path


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', type=str, required=True, help='Backtest date YYYY-MM-DD')
    parser.add_argument('--top', type=int, default=5)
    parser.add_argument('--weights', type=str, default=None)
    parser.add_argument('--no-regime-gate', action='store_true',
                        help='Skip regime-based weight override; use default weights')
    args = parser.parse_args()

    as_of_date = args.as_of
    top_n = args.top

    print(f"\n[1/3] Computing factors as of {as_of_date}...")
    factor_result = run_factors(as_of_date=as_of_date)
    regime = factor_result.get("regime", {})
    regime_label = regime.get("regime", "unknown")

    breadth = regime.get('breadth_ratio', '?') if regime else '?'
    vix_proxy = regime.get('vix_proxy') if regime else None
    vix_20d_avg = regime.get('vix_20d_avg') if regime else None

    # Compute spike ratio before header
    spike_ratio = None
    spike_label = "No spike"
    if vix_proxy is not None and vix_20d_avg is not None and vix_20d_avg > 0:
        spike_ratio = round(vix_proxy / vix_20d_avg, 2)
        if spike_ratio > 1.5:
            spike_label = "!! SPIKE BLOCKED"

    header = f"  BACKTEST -- As-of: {as_of_date} | Regime: {regime_label.replace('_',' ').upper()} | VIX: {vix_proxy}/{vix_20d_avg} | {spike_label} | R:R 1:1"
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
            below_threshold_count=0
        )
        print(f"\n  HTML Report: {report_path}")
        return

    weights = {}
    if not args.weights:
        if args.no_regime_gate:
            weights.update({"momentum": 0.35, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.15})
        elif regime_label == "risk_off":
            weights.update({"momentum": 0.20, "trend_quality": 0.20, "mean_reversion": 0.25, "quality": 0.35})
        elif regime_label == "neutral":
            weights.update({"momentum": 0.30, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.20})
        else:
            weights.update({"momentum": 0.35, "trend_quality": 0.25, "mean_reversion": 0.25, "quality": 0.15})
    else:
        for pair in args.weights.split(','):
            k, v = pair.split('=')
            weights[k.strip()] = float(v.strip())

    screen_result = run_screener(top_n=top_n, weights=weights, as_of_date=as_of_date)
    ranked = screen_result["ranked"]

    if not ranked:
        below_threshold_count = len(screen_result.get("below_threshold", []))
        if below_threshold_count > 0:
            print(f"  Score filter: >=70 | {below_threshold_count} picks below threshold filtered")
        print("      No picks found.")
        return

    below_threshold_count = len(screen_result.get("below_threshold", []))
    if below_threshold_count > 0:
        print(f"  Score filter: >=70 | {below_threshold_count} picks below threshold filtered")

    conn = sqlite3.connect(DB_PATH)

    rows = []
    for s in ranked:
        result, detail, stats = check_forward(
            conn, s["symbol"], as_of_date,
            s["entry_price"], s["target_price"], s["stoploss"]
        )

        # Compute actual return %
        if result == "WIN":
            return_pct = round((s["target_price"] - s["entry_price"]) / s["entry_price"] * 100, 2)
        elif result == "LOSS":
            return_pct = round((s["stoploss"] - s["entry_price"]) / s["entry_price"] * 100, 2)
        else:
            return_pct = round((stats["end_close"] - s["entry_price"]) / s["entry_price"] * 100, 2)

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
            "hold_days": hold_days
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
           f"{'Entry':>8}  {'Target':>8}  {'SL':>8}  {'F':1}  {'Res':5}  "
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
                   f"{r['entry_date']:<10}  {r['entry']:>8.2f}  {r['target']:>8.2f}  "
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
    summary = (f"Total Return: {total_return:+.2f}% | Avg Return: {avg_return:+.2f}% | "
               f"Win Rate: {hit_rate:.0f}% | Avg Hold Days: {avg_hold:.1f} | "
               f"Wins: {wins} Losses: {losses}")
    print(f"{BOLD}{summary}{RESET}")

    summary_dict = {
        "total_return": total_return, "avg_return": avg_return,
        "win_rate": hit_rate, "avg_hold": avg_hold,
        "wins": wins, "losses": losses, "draws": draws
    }
    report_path = generate_backtest_html(
        as_of_date, regime_label, breadth, vix_proxy, vix_20d_avg,
        spike_label, spike_ratio, spike_blocked=False, rows=rows, summary=summary_dict,
        below_threshold_count=below_threshold_count
    )
    print(f"\n  HTML Report: {report_path}")


if __name__ == '__main__':
    main()
