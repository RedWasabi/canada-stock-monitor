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
from fetch_tickers import fetch_active_tickers
from analyze_market import analyze_stocks
from generate_commentary import generate_report, generate_weekly_summary
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
        tickers = fetch_active_tickers()

        if args.test_run:
            tickers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]

        processed_stocks, anomalies, insufficient_stocks = analyze_stocks(tickers)
        processed_stocks = sorted(processed_stocks, key=lambda x: x["vol_ratio"], reverse=True)

        if processed_stocks:
            if is_friday():
                print("It's Friday — generating weekly summary...")
                report_text = generate_weekly_summary(processed_stocks)
            else:
                print("Generating market close summary...")
                report_text = generate_report(processed_stocks[:20], anomalies, insufficient_stocks)
        else:
            report_text = "<b>🔔 Market Close</b>\n\nNo active signals detected today.\n\n<b>💤</b> The market is now closed."

        success = send_telegram_message(report_text)
        if success:
            state["last_close_summary_date"] = today
            print("Close summary sent and date recorded.")
        else:
            print("Failed to send close summary — will retry on next run.")

        save_state(state, gist_id, pat)
        print("--------------------------------------------------")
        sys.exit(0)

    # ── 4. Market is OPEN (or --force-report) — run normal hourly analysis ────
    print("Market is open. Running analysis...")

    # 4a. Fetch active signal stocks from TradingView (300 max)
    tickers = fetch_active_tickers()

    if args.test_run:
        tickers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
        print(f"TEST MODE — using tickers: {tickers}")

    # 4b. Download price history and compute indicators
    processed_stocks, anomalies, insufficient_stocks = analyze_stocks(tickers)
    print(f"Analysis complete. {len(processed_stocks)} stocks passed the liquidity filter.")

    # Sort by pct_change descending to surface top movers for the report
    processed_stocks_by_change = sorted(processed_stocks, key=lambda x: x["pct_change"], reverse=True)
    top_20 = processed_stocks_by_change[:20]

    # 4c. Save current snapshot to state
    current_timestamp = time.time()
    state["snapshots"] = {
        "timestamp": current_timestamp,
        "stocks":    {s["Ticker"]: s for s in processed_stocks},
        "anomalies": anomalies,
        "insufficient": insufficient_stocks
    }

    # 4d. Time gate: only send a Telegram report once per ~hour
    last_report_time    = state.get("last_report_time", 0)
    time_since_report   = current_timestamp - last_report_time
    # 3300 seconds = 55 minutes (accounts for cron timing variance)
    is_report_time = time_since_report >= 3300 or args.force_report

    print(f"Time since last report: {time_since_report / 60:.1f} minutes.")

    if is_report_time:
        print("Time to report. Generating Groq commentary...")

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
            print("Telegram report sent. Timer reset.")
        else:
            print("Failed to send report — will retry on next run.")
    else:
        print("Not yet time to report. Skipping Telegram notification.")

    # 4e. Persist updated state
    save_state(state, gist_id, pat)
    print("Bot workflow complete.")
    print("--------------------------------------------------")


if __name__ == "__main__":
    main()
