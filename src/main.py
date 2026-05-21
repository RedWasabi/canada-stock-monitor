import os
import sys
import time
import json
import argparse
from dotenv import load_dotenv

# Load local environment variables from .env if it exists (for local testing)
load_dotenv()

# Add src to python path to import sibling files
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gist_store import load_state, save_state
from analyze_market import analyze_stocks
from generate_commentary import generate_report
from send_telegram import send_telegram_message

def main():
    parser = argparse.ArgumentParser(description="Canadian Stock Market Telegram Bot")
    parser.add_argument("--force-report", action="store_true", help="Force sending a report immediately")
    parser.add_argument("--test-run", action="store_true", help="Run with a small subset of tickers for testing")
    args = parser.parse_args()

    # Load credentials from environment
    gist_id = os.environ.get("GIST_ID")
    pat = os.environ.get("GH_PAT")
    
    print("--------------------------------------------------")
    print(f"Bot Triggered at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Load current state from Gist (or local fallback)
    state = load_state(gist_id, pat)
    
    # 2. Load tickers list
    tickers_file = os.path.join("data", "tickers.json")
    if not os.path.exists(tickers_file):
        print(f"Error: Tickers file not found at {tickers_file}")
        sys.exit(1)
        
    with open(tickers_file, "r") as f:
        all_tickers = json.load(f)

    if args.test_run:
        # Use a small subset of highly active stocks for quick test
        all_tickers = ["SHOP.TO", "RY.TO", "TD.TO", "ENB.TO", "HUT.TO"]
        print(f"Running in TEST mode with tickers: {all_tickers}")

    # 3. Analyze stocks (fetches data, calculates MAs, applies filters)
    processed_stocks, anomalies, insufficient_stocks = analyze_stocks(all_tickers)
    print(f"Analysis complete. {len(processed_stocks)} stocks passed the liquidity filter.")
    
    # Sort stocks by pct_change descending to identify top movers
    processed_stocks = sorted(processed_stocks, key=lambda x: x["pct_change"], reverse=True)
    top_20 = processed_stocks[:20]

    # Save the current precision snapshot in state
    current_timestamp = time.time()
    state["snapshots"] = {
        "timestamp": current_timestamp,
        "stocks": {s["Ticker"]: s for s in processed_stocks},
        "anomalies": anomalies,
        "insufficient": insufficient_stocks
    }

    # 4. Determine if we should report to Telegram
    last_report_time = state.get("last_report_time", 0)
    time_since_last_report = current_timestamp - last_report_time
    
    # 3300 seconds is 55 minutes. This covers slight timing differences in 15-min cron triggers
    is_report_time = time_since_last_report >= 3300 or args.force_report
    
    print(f"Time since last report: {time_since_last_report / 60:.1f} minutes.")
    
    if is_report_time:
        print("Time to send report. Generating commentary via Groq...")
        
        # Call Groq API to compile the report and generate commentary
        # Note: If no stocks passed the filter, we handle it
        if not top_20:
            report_text = "<b>📊 CANADIAN STOCK MARKET DAILY AUDIT REPORT</b>\n\nNo stocks passed the liquidity requirement of 1,000,000 average volume today."
            if insufficient_stocks:
                report_text += "\n\nInsufficient data for volume trend analysis for: " + ", ".join(insufficient_stocks)
        else:
            report_text = generate_report(top_20, anomalies, insufficient_stocks)
        
        # Send the final report to Telegram
        print("Sending report to Telegram...")
        telegram_success = send_telegram_message(report_text)
        
        if telegram_success:
            state["last_report_time"] = current_timestamp
            print("Telegram report sent successfully. Timer reset.")
        else:
            print("Failed to send Telegram report. Will try again on next run.")
    else:
        print("Not time to report yet. Skipping Telegram notification.")

    # 5. Save updated state back to Gist (or local fallback)
    save_state(state, gist_id, pat)
    print("Bot workflow complete.")
    print("--------------------------------------------------")

if __name__ == "__main__":
    main()
