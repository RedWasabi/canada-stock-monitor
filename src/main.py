import os
import sys
import time
import argparse
import pytz
from datetime import datetime
from dotenv import load_dotenv

# Load local .env if it exists (for local testing)
load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gist_store import load_state, save_state
from fetch_tickers import fetch_live_signals
from analyze_market import analyze_stocks
from generate_commentary import generate_report, generate_weekly_summary, generate_daily_close_summary
from send_telegram import send_telegram_message

# US Eastern Time zone
ET = pytz.timezone("America/New_York")


def get_market_state():
    """
    Returns the current US market state based on Eastern Time:
      "open"        — Mon–Fri, 09:30–16:00 ET (regular market hours)
      "pre_market"  — Mon–Fri, before 09:30 ET
      "after_hours" — Mon–Fri, after 16:00 ET
      "weekend"     — Saturday or Sunday
    """
    now_et = datetime.now(ET)
    weekday = now_et.weekday()  # 0=Monday … 6=Sunday

    if weekday >= 5:  # Saturday=5, Sunday=6
        return "weekend"

    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)

    if now_et < market_open:
        return "pre_market"
    elif now_et >= market_close:
        return "after_hours"
    else:
        return "open"


def is_friday():
    """Returns True if today is Friday in US Eastern Time."""
    return datetime.now(ET).weekday() == 4


def today_et_str():
    """Returns today's date string in ET as YYYY-MM-DD."""
    return datetime.now(ET).strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="US Stock Market Telegram Bot")
    parser.add_argument("--force-report",   action="store_true", help="Force send report immediately (skips time gate and market hours check)")
    parser.add_argument("--test-run",       action="store_true", help="Use a small 5-stock subset instead of full screener")
    args = parser.parse_args()

    gist_id = os.environ.get("GIST_ID")
    pat     = os.environ.get("GH_PAT")

    print("--------------------------------------------------")
    print(f"Bot triggered at: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S ET')}")

    # ── 1. Market Hours State Machine ─────────────────────────────────────────
    market_state = get_market_state()
    print(f"Market state: {market_state.upper()}")

    if not args.force_report:
        # WEEKEND: exit immediately — no processing, no messages
        if market_state == "weekend":
            print("Weekend detected — bot is idle. Exiting.")
            print("--------------------------------------------------")
            sys.exit(0)

        # PRE-MARKET: exit silently — no pre-market reporting
        if market_state == "pre_market":
            print("Pre-market hours — nothing to report yet. Exiting.")
            print("--------------------------------------------------")
            sys.exit(0)

    # ── 2. Load persistent state from Gist ────────────────────────────────────
    state = load_state(gist_id, pat)

    # Initialize snapshot history if not present
    if "snapshot_history" not in state:
        state["snapshot_history"] = []

    # ── 3. After-hours / market close handling ────────────────────────────────
    if not args.force_report and market_state == "after_hours":
        last_close_date = state.get("last_close_summary_date", "")
        today = today_et_str()

        if last_close_date == today:
            print("Close summary already sent today. Bot is idle until next market open. Exiting.")
            print("--------------------------------------------------")
            sys.exit(0)

        # First run after market close today — send close summary
        print("Market just closed. Sending close/weekly summary...")
        live_signals = fetch_live_signals()
        tickers = list(live_signals.keys())

        if args.test_run:
            tickers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]

        # Pass snapshot history to include trend metrics in close report
        processed_stocks, anomalies, insufficient_stocks = analyze_stocks(
            tickers, 
            snapshot_history=state.get("snapshot_history", [])
        )
        processed_stocks = sorted(processed_stocks, key=lambda x: x["vol_ratio"], reverse=True)

        if processed_stocks:
            if is_friday():
                print("It's Friday — generating weekly summary...")
                report_text = generate_weekly_summary(processed_stocks)
            else:
                print("Generating daily market close summary & next-day forecast...")
                report_text = generate_daily_close_summary(processed_stocks, anomalies, insufficient_stocks)
        else:
            report_text = "<b>🔔 Market Close</b>\n\nNo active signals detected today.\n\n<b>💤</b> The market is now closed."

        success = send_telegram_message(report_text)
        if success:
            state["last_close_summary_date"] = today
            # Clear history after sending close report
            state["snapshot_history"] = []
            print("Close summary sent and date recorded. History cleared.")
        else:
            print("Failed to send close summary — will retry on next run.")

        save_state(state, gist_id, pat)
        print("--------------------------------------------------")
        sys.exit(0)

    # ── 4. Market is OPEN (or --force-report) — run accumulation ──────────────
    print("Market is open. Fetching live signals from TradingView...")
    live_signals = fetch_live_signals()
    
    current_timestamp = time.time()
    
    # Save current live signals to snapshot history
    new_snapshot = {
        "timestamp": current_timestamp,
        "data": live_signals
    }
    
    # Add to rolling history (max 5 snapshots, covering ~1 hour)
    history = state.get("snapshot_history", [])
    history.append(new_snapshot)
    state["snapshot_history"] = history[-5:]
    
    # Check if it's time to send the hourly Telegram report
    last_report_time    = state.get("last_report_time", 0)
    time_since_report   = current_timestamp - last_report_time
    # 3300 seconds = 55 minutes
    is_report_time = time_since_report >= 3300 or args.force_report

    print(f"Accumulated {len(state['snapshot_history'])} snapshots. Time since last report: {time_since_report / 60:.1f} minutes.")

    if not is_report_time:
        print("Not yet time to report. Snapshot accumulated. Saving state and exiting fast.")
        save_state(state, gist_id, pat)
        print("--------------------------------------------------")
        sys.exit(0)

    # ── 5. Hourly Report Generation ───────────────────────────────────────────
    print("Time to report. Downloading price history and analyzing accumulated signals...")

    # Get the union of all tickers that appeared in any snapshot in the last hour
    union_tickers = set()
    for snap in state["snapshot_history"]:
        union_tickers.update(snap.get("data", {}).keys())
    union_tickers = list(union_tickers)

    if args.test_run:
        union_tickers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
        print(f"TEST MODE — using tickers: {union_tickers}")

    print(f"Analyzing a total of {len(union_tickers)} unique tickers from history...")

    # Run yfinance analysis using accumulated snapshot history for trend metrics
    processed_stocks, anomalies, insufficient_stocks = analyze_stocks(
        union_tickers, 
        snapshot_history=state["snapshot_history"]
    )
    print(f"Analysis complete. {len(processed_stocks)} stocks passed the liquidity filter.")

    # Sort by pct_change descending to surface top movers for the report
    processed_stocks_by_change = sorted(processed_stocks, key=lambda x: x["pct_change"], reverse=True)
    top_20 = processed_stocks_by_change[:20]

    # Save current snapshot to state (for any direct dashboard references)
    state["snapshots"] = {
        "timestamp": current_timestamp,
        "stocks":    {s["Ticker"]: s for s in processed_stocks},
        "anomalies": anomalies,
        "insufficient": insufficient_stocks
    }

    print("Generating Groq commentary...")
    if not top_20:
        report_text = (
            "<b>📊 US MARKET SIGNAL REPORT</b>\n\n"
            "No stocks passed all filters this hour."
        )
    else:
        report_text = generate_report(top_20, anomalies, insufficient_stocks)

    print("Sending report to Telegram...")
    success = send_telegram_message(report_text)

    if success:
        state["last_report_time"] = current_timestamp
        # Clear snapshot history to start fresh for the next hour
        state["snapshot_history"] = []
        print("Telegram report sent. Timer reset. History cleared.")
    else:
        print("Failed to send report — will retry on next run.")

    # Persist updated state
    save_state(state, gist_id, pat)
    print("Bot workflow complete.")
    print("--------------------------------------------------")


if __name__ == "__main__":
    main()
