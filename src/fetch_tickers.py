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
        {"left": "average_volume_30d_calc", "operation": "greater",   "right": 10000000},
        {"left": "close",                  "operation": "greater",   "right": 1.0},
    ]
    
    payload = {
        "filter": filters,
        "options": {"active_symbols_only": True},
        "markets": ["america"],
        "symbols": {"query": {"types": ["stock"]}, "tickers": []},
        "columns": ["name", "close", "change", "relative_volume_10d_calc", "RSI", "average_volume_30d_calc"],
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
                if len(d) < 6 or not d[0]:
                    continue
                sym = str(d[0]).strip()
                if "/" in sym or " " in sym:
                    continue
                sym_clean = sym.replace(".", "-")
                
                # Minimum volume filter: average daily volume must be > 10,000,000 shares
                close_price = float(d[1]) if d[1] is not None else 0.0
                avg_vol_shares = float(d[5]) if d[5] is not None else 0.0
                if avg_vol_shares <= 10000000.0:
                    continue
                
                results[sym_clean] = {
                    "close": close_price,
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


def fetch_watchlist_live_data(watchlist_tickers):
    """
    Downloads recent data for the watchlist tickers using yfinance
    and computes the metrics needed for snapshots.
    """
    import yfinance as yf
    import pandas as pd
    import numpy as np
    
    print(f"Fetching live stats for {len(watchlist_tickers)} watchlist tickers...")
    try:
        data = yf.download(
            watchlist_tickers,
            period="30d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True
        )
        
        has_multi = isinstance(data.columns, pd.MultiIndex)
        results = {}
        
        for ticker in watchlist_tickers:
            try:
                if has_multi:
                    if ticker not in data.columns.get_level_values(0):
                        continue
                    df = data[ticker].copy()
                else:
                    df = data.copy()
                    
                df = df.dropna(subset=["Close"])
                if len(df) < 2:
                    continue
                    
                close_history = df["Close"]
                volume_history = df.get("Volume", pd.Series(dtype=float))
                
                today_close = float(close_history.iloc[-1])
                prev_close = float(close_history.iloc[-2])
                pct_change = ((today_close - prev_close) / prev_close) * 100.0 if prev_close != 0 else 0.0
                
                # Volume ratio calculation
                vol_ratio = 1.0
                if not volume_history.empty and len(volume_history) >= 2:
                    today_vol = float(volume_history.iloc[-1])
                    avg_vol = float(volume_history.iloc[-21:-1].mean()) if len(volume_history) >= 21 else float(volume_history.iloc[:-1].mean())
                    if avg_vol > 0:
                        vol_ratio = today_vol / avg_vol
                        
                # Quick RSI calculation
                rsi_val = 50.0
                if len(close_history) >= 15:
                    delta = close_history.diff()
                    gain = delta.clip(lower=0)
                    loss = -delta.clip(upper=0)
                    avg_gain = gain.iloc[-15:-1].mean()
                    avg_loss = loss.iloc[-15:-1].mean()
                    if avg_loss > 0:
                        rs = avg_gain / avg_loss
                        rsi_val = 100.0 - (100.0 / (1.0 + rs))
                    elif avg_gain > 0:
                        rsi_val = 100.0
                        
                results[ticker] = {
                    "close": today_close,
                    "pct_change": pct_change,
                    "vol_ratio": vol_ratio,
                    "rsi": rsi_val
                }
            except Exception as e:
                print(f"Error processing live stats for {ticker}: {e}")
                continue
                
        return results
    except Exception as e:
        print(f"Error downloading live stats for watchlist: {e}")
        return {}
