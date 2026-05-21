import os
import json
import string
import requests
import pandas as pd

def fetch_from_cad_tickers():
    """
    Attempts to download tickers using the cad_tickers library.
    """
    try:
        from cad_tickers.exchanges.tsx import dl_tsx_xlsx
        print("Attempting to fetch tickers via cad_tickers package...")
        # Fetch both TSX and TSXV
        df = dl_tsx_xlsx(exchanges=["TSX", "TSXV"], return_df=True)
        
        # Verify columns and data
        if df is not None and not df.empty:
            tickers = []
            # Check likely column names
            symbol_col = None
            exchange_col = None
            
            for col in df.columns:
                if 'symbol' in col.lower():
                    symbol_col = col
                if 'exchange' in col.lower() or 'ex' == col.lower():
                    exchange_col = col
            
            if symbol_col:
                for _, row in df.iterrows():
                    sym = str(row[symbol_col]).strip()
                    # Skip empty/invalid
                    if not sym or sym.lower() == 'nan':
                        continue
                        
                    # Clean symbol formatting for Yahoo Finance
                    # Yahoo finance uses '-' instead of '.' for classes/pref (e.g. RY.PR.A -> RY-PA.TO)
                    sym_clean = sym.replace('.', '-')
                    
                    # Check exchange column to determine suffix
                    ex = str(row[exchange_col]).upper() if exchange_col else "TSX"
                    if "TSXV" in ex or "VENTURE" in ex or "V" == ex:
                        tickers.append(f"{sym_clean}.V")
                    else:
                        tickers.append(f"{sym_clean}.TO")
                
                # Remove duplicates
                tickers = sorted(list(set(tickers)))
                print(f"Successfully fetched {len(tickers)} tickers via cad_tickers.")
                return tickers
        print("cad_tickers returned empty or invalid DataFrame.")
    except Exception as e:
        print(f"Could not fetch tickers using cad_tickers package: {e}")
    return None

def fetch_from_tradingview():
    """
    Fetches the complete, up-to-date list of active TSX tickers from TradingView.
    """
    print("Attempting to fetch active TSX tickers from TradingView...")
    try:
        url = "https://scanner.tradingview.com/canada/scan"
        payload = {
            "filter": [
                {"left": "exchange", "operation": "in_range", "right": ["TSX"]}
            ],
            "options": {"active_symbols_only": True},
            "markets": ["canada"],
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name"],
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "range": [0, 4000]
        }
        response = requests.post(url, json=payload, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if response.status_code == 200:
            data = response.json()
            tickers = []
            for item in data.get('data', []):
                sym = item.get('d', [None])[0]
                if sym:
                    # Clean the ticker for Yahoo Finance (dots to hyphens)
                    sym_clean = str(sym).strip().replace('.', '-')
                    tickers.append(f"{sym_clean}.TO")
            
            # Remove duplicates and sort
            tickers = sorted(list(set(tickers)))
            print(f"Successfully fetched {len(tickers)} TSX tickers from TradingView.")
            return tickers
        else:
            print(f"TradingView scanner API failed with status code: {response.status_code}")
    except Exception as e:
        print(f"Error fetching from TradingView: {e}")
    return None

def fetch_from_wikipedia():
    """
    Falls back to scraping TSX tickers from Wikipedia using regex.
    """
    import re
    print("Falling back to scraping TSX tickers from Wikipedia...")
    tickers = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Wikipedia lists TSX tickers from A to Z
    for char in string.ascii_uppercase:
        url = f"https://en.wikipedia.org/wiki/Companies_listed_on_the_Toronto_Stock_Exchange_({char})"
        print(f"Scraping Wikipedia page: {char}...")
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                # Find all links of the form https://money.tmx.com/en/quote/SYMBOL
                symbols = re.findall(r'quote/([A-Z0-9.-]+)', response.text)
                for sym in symbols:
                    sym_str = str(sym).strip()
                    if sym_str and sym_str.lower() != 'nan':
                        # Clean symbol for Yahoo Finance (replace dots with hyphens)
                        sym_clean = sym_str.replace('.', '-')
                        tickers.append(f"{sym_clean}.TO")
            else:
                print(f"Failed to fetch page {char}: status code {response.status_code}")
        except Exception as e:
            try:
                print(f"Error scraping Wikipedia page ({char}): {str(e)}")
            except Exception:
                print(f"Error scraping Wikipedia page ({char})")
            continue

    # Remove duplicates
    tickers = sorted(list(set(tickers)))
    print(f"Successfully scraped {len(tickers)} TSX tickers from Wikipedia.")
    return tickers

def main():
    print("Starting Canadian stock ticker list updater...")
    
    # 1. Try TradingView first (most accurate and active listings)
    tickers = fetch_from_tradingview()
    
    # 2. Fallback to cad_tickers library
    if not tickers or len(tickers) == 0:
        tickers = fetch_from_cad_tickers()
        
    # 3. Fallback to Wikipedia scraping
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
