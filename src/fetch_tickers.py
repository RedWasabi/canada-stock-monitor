import os
import json
import requests
import re

def fetch_from_tradingview():
    """
    Fetches the complete, up-to-date list of active US tickers (NYSE, NASDAQ, AMEX)
    from TradingView. Filters to:
      - Common stocks only (types: ["stock"])
      - Average 30-day volume >= 1,000,000
    Sorted by market cap descending.
    """
    print("Attempting to fetch active, liquid US tickers from TradingView...")
    try:
        url = "https://scanner.tradingview.com/america/scan"
        payload = {
            "filter": [
                # Only NYSE, NASDAQ, AMEX exchanges
                {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                # Minimum 30-day average volume of 1,000,000 — filters out penny/illiquid stocks
                # NOTE: The correct operation for "greater than" is "greater" (not "egt" or "greater_or_equal")
                {"left": "average_volume_30d_calc", "operation": "greater", "right": 1000000}
            ],
            "options": {"active_symbols_only": True},
            "markets": ["america"],
            # types: ["stock"] filters to common stocks only — excludes ETFs, funds, warrants, preferred shares
            "symbols": {"query": {"types": ["stock"]}, "tickers": []},
            "columns": ["name"],
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            # Request up to 2000 — TradingView returns ~1973 matching stocks
            "range": [0, 2000]
        }
        response = requests.post(url, json=payload, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if response.status_code == 200:
            data = response.json()
            tickers = []
            for item in data.get('data', []):
                sym = item.get('d', [None])[0]
                if not sym:
                    continue
                sym = str(sym).strip()

                # Skip preferred stocks and warrants — they contain "/" or spaces
                # e.g. BAC/PK, WFC/PL, AXIA/P — Yahoo Finance cannot parse these
                if '/' in sym or ' ' in sym:
                    continue

                # Replace dots with hyphens for Yahoo Finance (e.g. BRK.B -> BRK-B)
                sym_clean = sym.replace('.', '-')
                tickers.append(sym_clean)

            # Remove duplicates and sort alphabetically
            tickers = sorted(list(set(tickers)))
            print(f"Successfully fetched {len(tickers)} liquid US common stock tickers from TradingView.")
            return tickers
        else:
            print(f"TradingView scanner API failed with status code: {response.status_code}. Response: {response.text[:200]}")
    except Exception as e:
        print(f"Error fetching US tickers from TradingView: {e}")
    return None


def fetch_from_wikipedia():
    """
    Falls back to scraping S&P 500 tickers from Wikipedia using regex.
    Used only when TradingView API fails.
    """
    print("Falling back to scraping S&P 500 tickers from Wikipedia...")
    tickers = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            # Locate the S&P 500 constituents table by its id
            table_match = re.search(r'<table[^>]*id="constituents"[^>]*>(.*?)</table>', response.text, re.DOTALL)
            if table_match:
                table_content = table_match.group(1)
                # Find all table rows
                rows = re.findall(r'<tr>(.*?)</tr>', table_content, re.DOTALL)
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                    if cells:
                        # First cell is the ticker symbol
                        symbol_cell = cells[0]
                        # Extract text inside <a> tag if it exists
                        sym_match = re.search(r'<a[^>]*>(.*?)</a>', symbol_cell)
                        sym = sym_match.group(1) if sym_match else symbol_cell
                        # Strip any remaining HTML tags
                        sym = re.sub(r'<[^>]*>', '', sym).strip()
                        # Valid ticker: uppercase letters only, max 5 chars
                        if sym and sym.isupper() and len(sym) <= 5 and '/' not in sym:
                            # Replace dots with hyphens for Yahoo Finance (e.g. BRK.B -> BRK-B)
                            sym_clean = sym.replace('.', '-')
                            tickers.append(sym_clean)
            else:
                print("Could not find the constituents table in Wikipedia HTML.")
        else:
            print(f"Failed to fetch Wikipedia page: status code {response.status_code}")
    except Exception as e:
        print(f"Error scraping Wikipedia S&P 500 table: {e}")

    # Remove duplicates
    tickers = sorted(list(set(tickers)))
    print(f"Successfully scraped {len(tickers)} S&P 500 tickers from Wikipedia.")
    return tickers


def main():
    print("Starting US stock ticker list updater...")

    # 1. Try TradingView first (most accurate, gets top ~1973 liquid US common stock tickers)
    tickers = fetch_from_tradingview()

    # 2. Fallback to Wikipedia S&P 500 scraping
    if not tickers or len(tickers) == 0:
        tickers = fetch_from_wikipedia()

    if tickers and len(tickers) > 0:
        tickers_file = os.path.join("data", "tickers.json")
        os.makedirs("data", exist_ok=True)

        # Save to JSON
        with open(tickers_file, "w") as f:
            json.dump(tickers, f, indent=2)

        print(f"Tickers updated successfully. Saved {len(tickers)} tickers to {tickers_file}")
    else:
        print("Error: Could not retrieve tickers from any source.")


if __name__ == "__main__":
    main()
