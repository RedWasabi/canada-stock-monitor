import os
import json
import requests

def fetch_active_tickers_with_data(use_fallback=False):
    """
    Fetches US stocks and returns a dictionary of ticker -> metrics.
    If use_fallback is True, it fetches the top 100 stocks by market cap (no signal filters).
    Otherwise, it fetches the top 300 active signal stocks.
    """
    url = "https://scanner.tradingview.com/america/scan"
    
    # Base filters — ALL must be true (AND logic)
    filters = [
        {"left": "exchange",               "operation": "in_range",  "right": ["NYSE", "NASDAQ", "AMEX"]},
        {"left": "average_volume_30d_calc", "operation": "greater",   "right": 1000000},
        {"left": "close",                  "operation": "greater",   "right": 1.0},
    ]
    
    payload = {
        "filter": filters,
        "options": {"active_symbols_only": True},
        "markets": ["america"],
        "symbols": {"query": {"types": ["stock"]}, "tickers": []},
        "columns": ["name", "close", "change", "relative_volume_10d_calc", "RSI"],
    }
    
    if use_fallback:
        # Sort by market cap descending to get top 100 blue chips
        payload["sort"] = {"sortBy": "market_cap_basic", "sortOrder": "desc"}
        payload["range"] = [0, 100]
        print("Querying TradingView for fallback top market cap stocks...")
    else:
        # Signal filters — at least ONE must match (OR logic via filter2)
        payload["filter2"] = {
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
        }
        payload["sort"] = {"sortBy": "relative_volume_10d_calc", "sortOrder": "desc"}
        payload["range"] = [0, 300]
        print("Querying TradingView for active signal stocks...")
        
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            results = {}
            for item in data.get("data", []):
                d = item.get("d", [])
                if len(d) < 5 or not d[0]:
                    continue
                sym = str(d[0]).strip()
                if "/" in sym or " " in sym:
                    continue
                sym_clean = sym.replace(".", "-")
                
                results[sym_clean] = {
                    "close": float(d[1]) if d[1] is not None else 0.0,
                    "pct_change": float(d[2]) if d[2] is not None else 0.0,
                    "vol_ratio": float(d[3]) if d[3] is not None else 1.0,
                    "rsi": float(d[4]) if d[4] is not None else 50.0
                }
            return results
        else:
            print(f"TradingView scanner API failed (HTTP {response.status_code}): {response.text[:200]}")
            return {}
    except Exception as e:
        print(f"Error calling TradingView scanner API: {e}")
        return {}


def fetch_live_signals():
    """
    Fetches active signal stocks with live data.
    Falls back to top 100 market cap if signal query returns < 50 stocks.
    """
    data = fetch_active_tickers_with_data(use_fallback=False)
    if len(data) < 50:
        print(f"TradingView returned only {len(data)} signals. Fetching fallback market cap list.")
        data = fetch_active_tickers_with_data(use_fallback=True)
    return data


def fetch_active_tickers():
    """
    Returns only the list of tickers (backward compatibility).
    """
    return list(fetch_live_signals().keys())
