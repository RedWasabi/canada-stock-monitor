import pandas as pd
import yfinance as yf
import numpy as np

def analyze_stocks(tickers):
    """
    Downloads historical data for the tickers, processes them, and returns:
    - A list of processed stock data dicts passing the liquidity filter
    - A list of stocks with extreme price moves without a volume spike (anomalies)
    - A list of stocks with insufficient data for volume trend analysis
    """
    print(f"Downloading data for {len(tickers)} tickers in bulk...")
    
    # Download 35 days of data to ensure we have at least 20 trading days
    try:
        data = yf.download(tickers, period="35d", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        print(f"Error downloading bulk data from yfinance: {e}")
        return [], [], []

    processed_stocks = []
    anomalies = []
    insufficient_data_stocks = []

    # If yf.download returns a single ticker, group_by might behave differently,
    # but we will always have multiple tickers here.
    # We support both multi-index columns and single ticker DataFrame.
    has_multi_index = isinstance(data.columns, pd.MultiIndex)

    for ticker in tickers:
        try:
            if has_multi_index:
                if ticker not in data.columns.levels[0]:
                    print(f"No data returned for ticker: {ticker}")
                    continue
                df = data[ticker].copy()
            else:
                # If only one ticker was requested
                df = data.copy()
            
            # Clean up missing rows
            df = df.dropna(subset=['Close', 'Volume'])
            
            # If the stock has no data at all, it is likely delisted or invalid.
            # We skip it entirely to keep the report clean.
            if len(df) == 0:
                continue

            # Check for insufficient data
            # We need at least 21 days: 20 days for the volume moving average, 
            # and today's data to compare.
            if len(df) < 20:
                insufficient_data_stocks.append(ticker)
                continue

            # Identify "today's" data and "historical" data.
            # Usually, the last row in df is the current day's latest data.
            current_close = float(df['Close'].iloc[-1])
            previous_close = float(df['Close'].iloc[-2])
            current_volume = float(df['Volume'].iloc[-1])

            # Calculate price percentage change from previous close
            pct_change = ((current_close - previous_close) / previous_close) * 100

            # Calculate 20-period moving average of volume of the preceding 20 days (excluding today's incomplete volume if market is open,
            # or including it if we want the moving average of the last 20 periods.
            # The prompt says: "Identify stocks where the current volume is at least 3% higher than the 20-period moving average."
            # We will calculate the 20-period moving average of daily volume over the past 20 trading days.
            # We can use the last 20 days of volume including today, or excluding today.
            # Let's use the past 20 days excluding today: df['Volume'].iloc[-21:-1].mean()
            # If the market is closed, today's volume is complete. If it's open, today's volume is building.
            # Excluding today is standard for checking a spike against historical baseline.
            # Let's calculate the baseline average volume:
            vol_history = df['Volume'].iloc[-21:-1]
            if len(vol_history) < 20:
                # Fall back to including today if there aren't enough preceding days
                vol_history = df['Volume'].iloc[-20:]
                
            avg_volume_20 = float(vol_history.mean())

            # Liquidity Requirement: Discard any stock with an average daily volume below 1,000,000
            if avg_volume_20 < 1000000:
                continue

            # Calculate Volume vs Avg (%)
            # If average volume is 0, set to 0
            if avg_volume_20 > 0:
                vol_vs_avg = ((current_volume - avg_volume_20) / avg_volume_20) * 100
            else:
                vol_vs_avg = 0.0

            # Volume Spike: current volume is at least 3% higher than 20-period moving average
            is_spike = vol_vs_avg >= 3.0
            alert_status = "Spike" if is_spike else ""

            stock_info = {
                "Ticker": ticker,
                "Close": current_close,
                "pct_change": pct_change,
                "avg_volume": avg_volume_20,
                "current_volume": current_volume,
                "vol_vs_avg": vol_vs_avg,
                "alert_status": alert_status
            }

            processed_stocks.append(stock_info)

            # Anomaly: Extreme price move (over 5% absolute) without corresponding volume spike
            if abs(pct_change) > 5.0 and not is_spike:
                anomalies.append(stock_info)

        except Exception as e:
            print(f"Error processing ticker {ticker}: {str(e)}")
            continue

    return processed_stocks, anomalies, insufficient_data_stocks
