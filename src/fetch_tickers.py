import os
import json
import requests

# Fallback: top 100 S&P 500 blue-chip tickers if TradingView returns < 50 signals
FALLBACK_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "LLY", "AVGO",
    "JPM", "TSLA", "UNH", "V", "XOM", "MA", "COST", "HD", "PG", "JNJ",
    "ABBV", "BAC", "NFLX", "CRM", "CVX", "MRK", "KO", "AMD", "PEP", "TMO",
    "ACN", "LIN", "ADBE", "MCD", "WMT", "CSCO", "ABT", "TXN", "NEE", "PM",
    "IBM", "GE", "ISRG", "DHR", "CAT", "INTU", "SPGI", "RTX", "BKNG", "AMGN",
    "HON", "GS", "VRTX", "PLD", "AMAT", "MS", "PANW", "QCOM", "T", "ELV",
    "BX", "SYK", "AXP", "LRCX", "BSX", "GILD", "MDT", "ADI", "BLK", "TMUS",
    "SBUX", "DE", "MMC", "PGR", "CI", "ETN", "NOW", "REGN", "MDLZ", "ZTS",
    "TJX", "CME", "MO", "ADP", "SO", "DUK", "PH", "CL", "HUM", "MCK",
    "WM", "FI", "AON", "EMR", "ITW", "CTAS", "GD", "KLAC", "COF", "NOC"
]


def fetch_active_tickers():
    """
    Fetches a live list of ~300 US stocks that are showing active signals RIGHT NOW.

    Uses TradingView Scanner API to pre-filter by:
      Base filters (AND):
        - NYSE / NASDAQ / AMEX exchanges only
        - Common stocks only (no ETFs, preferred shares, warrants)
        - 30-day average volume > 1,000,000 (liquid stocks only)
        - Price > $1.00 (no sub-penny stocks)

      Signal filters (OR — stock must match at least ONE):
        - Relative Volume (10-day) > 1.5x  (unusual trading activity)
        - Today's price change > +2.0%     (strong up move)
        - Today's price change < -2.0%     (strong down move)
        - RSI (14-day) > 65               (approaching overbought)
        - RSI (14-day) < 35               (approaching oversold)

    Returns the top 300 by relative volume (most active first).
    Falls back to FALLBACK_TICKERS (top 100 S&P 500 blue-chips) if < 50 signals found.
    """
    print("Fetching active signal stocks from TradingView Scanner...")
    try:
        url = "https://scanner.tradingview.com/america/scan"
        payload = {
            # Base filters — ALL must be true (AND logic)
            "filter": [
                {"left": "exchange",               "operation": "in_range",  "right": ["NYSE", "NASDAQ", "AMEX"]},
                {"left": "average_volume_30d_calc", "operation": "greater",   "right": 1000000},
                {"left": "close",                  "operation": "greater",   "right": 1.0},
            ],
            # Signal filters — at least ONE must match (OR logic via filter2)
            "filter2": {
                "operator": "or",
                "operands": [
                    {"operation": {"operator": "and", "operands": [
                        {"expression": {"left": "relative_volume_10d_calc", "operation": "greater", "right": 1.5}}
                    ]}},
                    {"operation": {"operator": "and", "operands": [
                        {"expression": {"left": "change", "operation": "greater", "right": 2.0}}
                    ]}},
                    {"operation": {"operator": "and", "operands": [
                        {"expression": {"left": "change", "operation": "less", "right": -2.0}}
                    ]}},
                    {"operation": {"operator": "and", "operands": [
                        {"expression": {"left": "RSI", "operation": "greater", "right": 65}}
                    ]}},
                    {"operation": {"operator": "and", "operands": [
                        {"expression": {"left": "RSI", "operation": "less", "right": 35}}
                    ]}},
                ]
            },
            "options": {"active_symbols_only": True},
            "markets": ["america"],
            # Common stocks only — excludes ETFs, mutual funds, warrants, preferred shares
            "symbols": {"query": {"types": ["stock"]}, "tickers": []},
            # Columns returned — used for sorting only; we discard metadata after extracting tickers
            "columns": ["name", "relative_volume_10d_calc", "change", "RSI", "market_cap_basic"],
            # Sort by relative volume descending — most actively traded stocks first
            "sort": {"sortBy": "relative_volume_10d_calc", "sortOrder": "desc"},
            # Get top 300 — hard cap to keep runtime fast
            "range": [0, 300]
        }

        response = requests.post(
            url,
            json=payload,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            tickers = []
            for item in data.get("data", []):
                sym = item.get("d", [None])[0]
                if not sym:
                    continue
                sym = str(sym).strip()

                # Skip preferred stocks / warrants that slipped through (contain "/" or spaces)
                if "/" in sym or " " in sym:
                    continue

                # Replace dots with hyphens for Yahoo Finance (e.g. BRK.B → BRK-B)
                sym_clean = sym.replace(".", "-")
                tickers.append(sym_clean)

            if len(tickers) >= 50:
                print(f"TradingView returned {len(tickers)} active signal stocks.")
                return tickers
            else:
                print(f"TradingView returned only {len(tickers)} stocks (market may be closed/quiet). Using fallback blue-chip list.")
                return FALLBACK_TICKERS

        else:
            print(f"TradingView scanner failed (HTTP {response.status_code}). Using fallback list.")
            return FALLBACK_TICKERS

    except Exception as e:
        print(f"Error fetching tickers from TradingView: {e}. Using fallback list.")
        return FALLBACK_TICKERS
