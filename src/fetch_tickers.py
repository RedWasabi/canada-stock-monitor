import os
import json
import string
import requests
import re

def fetch_from_tradingview():
    """
    Fetches the complete, up-to-date list of active US tickers (NYSE, NASDAQ, AMEX)
    from TradingView. We fetch the top 1,000 stocks by market cap.
    """
    print("Attempting to fetch active, liquid US tickers from TradingView...")
    try:
        url = "https://scanner.tradingview.com/america/scan"
        payload = {
            "filter": [
                {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]}
            ],
            "options": {"active_symbols_only": True},
            "markets": ["america"],
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name"],
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "range": [0, 1000]
        }
        response = requests.post(url, json=payload, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if response.status_code == 200:
            data = response.json()
            tickers = []
            for item in data.get('data', []):
                sym = item.get('d', [None])[0]
                if sym:
                    # Clean the ticker for Yahoo Finance (dots to hyphens, e.g., BRK.B -> BRK-B)
                    sym_clean = str(sym).strip().replace('.', '-')
                    # US tickers do not need a suffix on Yahoo Finance
                    tickers.append(sym_clean)
            
            # Remove duplicates and sort
            tickers = sorted(list(set(tickers)))
            print(f"Successfully fetched {len(tickers)} US tickers from TradingView.")
            return tickers
        else:
            print(f"TradingView scanner API failed with status code: {response.status_code}")
    except Exception as e:
        print(f"Error fetching US tickers from TradingView: {e}")
    return None

def fetch_from_wikipedia():
    """
    Falls back to scraping S&P 500 tickers from Wikipedia using regex.
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
            # Locate the table of constituents
            table_match = re.search(r'<table[^>]*id="constituents"[^>]*>(.*?)</table>', response.text, re.DOTALL)
            if table_match:
                table_content = table_match.group(1)
                # Find all table rows
                rows = re.findall(r'<tr>(.*?)</tr>', table_content, re.DOTALL)
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                    if cells:
                        # First cell is typically the ticker symbol
                        symbol_cell = cells[0]
                        # Extract ticker symbol text inside <a> tag if exists
                        sym_match = re.search(r'<a[^>]*>(.*?)</a>', symbol_cell)
                        sym = sym_match.group(1) if sym_match else symbol_cell
                        # Clean any HTML tags
                        sym = re.sub(r'<[^>]*>', '', sym).strip()
                        if sym and sym.isupper() and len(sym) <= 5:
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
    
    # 1. Try TradingView first (most accurate, gets top 1000 liquid US tickers)
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

