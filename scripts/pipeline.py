import argparse
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from updater import run as run_updater
from factors import run as run_factors
from screener import run as run_screener, auto_weights, DEFAULT_WEIGHTS
from reporter import run as run_reporter


def main():
    parser = argparse.ArgumentParser(description='AI-Trader Swing Picks Pipeline')
    parser.add_argument('--full', action='store_true', help='Run all 4 stages (default)')
    parser.add_argument('--skip-update', action='store_true', help='Skip data update stage')
    parser.add_argument('--top', type=int, default=5, help='Number of top picks (default: 5)')
    parser.add_argument('--weights', type=str, default=None,
                        help='Comma-separated factor weights: momentum=0.35,trend_quality=0.25,mean_reversion=0.25,quality=0.15')
    parser.add_argument('--sector-cap', type=int, default=2, help='Max stocks per sector (default: 2)')
    parser.add_argument('--capital', type=float, default=100000, help='Capital for position sizing (default: 100000)')
    parser.add_argument('--risk-per-trade', type=float, default=1.0, help='Risk per trade %% of capital (default: 1.0)')

    args = parser.parse_args()

    skip_update = args.skip_update
    top_n = args.top
    sector_cap = args.sector_cap

    all_warnings = []

    if not skip_update:
        print("[1/4] Updating market data...")
        result = run_updater()
        if result["errors"] > 0:
            all_warnings.append(f"Update: {result['errors']} symbols failed to update")
        else:
            print(f"      {result['updated']} updated, {result['skipped']} skipped, {result['errors']} errors")
    else:
        print("[1/4] Skipping data update (--skip-update)")

    print("[2/4] Computing factors...")
    factor_result = run_factors()
    if factor_result["filtered_out"] > 0:
        reasons = factor_result.get("filter_reasons", {})
        detail = ", ".join(f"{k} ({v})" for k, v in reasons.items())
        all_warnings.append(f"Factors: {factor_result['filtered_out']} symbols filtered -- {detail}")
    print(f"      {factor_result['computed']} scored, {factor_result['filtered_out']} filtered")
    if factor_result.get("regime"):
        r = factor_result["regime"]
        regime_label = r.get("regime", "unknown")
        print(f"      Regime: {regime_label.replace('_',' ').upper()} | Nifty: {r['nifty_trend']} | Breadth: {r['breadth_ratio']} | VIX proxy: {r['vix_proxy']} | VIX 20d avg: {r.get('vix_20d_avg', 'N/A')}")
    else:
        regime_label = "unknown"

    # VIX spike safety check
    regime = factor_result.get("regime", {})
    vix_proxy = regime.get("vix_proxy")
    vix_20d_avg = regime.get("vix_20d_avg")
    if vix_proxy is not None and vix_20d_avg is not None and vix_20d_avg > 0:
        spike_ratio = vix_proxy / vix_20d_avg
        if spike_ratio > 1.5:
            print(f"\n*** VOLATILITY SPIKE DETECTED ***")
            print(f"    VIX proxy: {vix_proxy} | 20-day avg: {vix_20d_avg} | Spike ratio: {spike_ratio:.2f}x")
            print(f"    Skipping picks -- high risk of stop-outs during regime transition.\n")
            print(json.dumps({"stage": "pipeline", "status": "volatility_spike_skipped",
                               "vix_proxy": vix_proxy, "vix_20d_avg": vix_20d_avg,
                               "spike_ratio": round(spike_ratio, 2),
                               "ts": datetime.now().isoformat()}))
            sys.exit(0)

    if args.weights:
        weights = dict(DEFAULT_WEIGHTS)
        for pair in args.weights.split(','):
            k, v = pair.split('=')
            weights[k.strip()] = float(v.strip())
    else:
        weights = auto_weights(regime_label)

    print("[3/4] Screening and ranking...")
    screen_result = run_screener(top_n=top_n, weights=weights, sector_cap=sector_cap)
    if "error" in screen_result:
        print(f"      ERROR: {screen_result['error']}")
        sys.exit(1)
    ranked = screen_result["ranked"]
    rejected = screen_result["rejected"]
    run_ts = screen_result["run_ts"]
    if rejected:
        all_warnings.append(f"Screen: {len(rejected)} stocks rejected (sector cap, etc.)")

    if not ranked:
        below = screen_result.get("below_threshold", [])
        if below:
            top_available = sorted(below, key=lambda x: x["composite"], reverse=True)[:5]
            scores_str = ", ".join(f"{s['symbol']}={s['composite']:.1f}" for s in top_available)
            print(f"      No picks within score range (60-75). Top available: {scores_str}")
        else:
            print(f"      No picks within score range (60-75).")

    print("[4/4] Generating reports...")
    report_result = run_reporter(ranked, rejected, run_ts, weights, capital=args.capital, risk_per_trade=args.risk_per_trade)
    all_warnings.extend(report_result.get("warnings", []))

    if all_warnings:
        print("\n--- Pipeline Warnings ---")
        for w in all_warnings:
            print(f"  ! {w}")


if __name__ == '__main__':
    main()
