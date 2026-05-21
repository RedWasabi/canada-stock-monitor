import pandas as pd
import yfinance as yf
import numpy as np

def calculate_rsi(prices, period=14):
    """
    Calculates Wilder's RSI for a pandas Series of prices.
    """
    if len(prices) < period + 1:
        return np.nan
    
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Wilder's smoothing (alpha = 1 / period)
    avg_gain = gain.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def analyze_stocks(tickers):
    """
    Downloads historical data for the tickers, processes them, and returns:
    - A list of processed stock data dicts passing the liquidity filter
    - A list of stocks with extreme price moves without a volume spike (anomalies)
    - A list of stocks with insufficient data for volume trend analysis
    """
    print(f"Downloading data for {len(tickers)} tickers in bulk...")
    
    # Download 60 days of data to ensure we have enough data for 14-period RSI and 20-period Bollinger Bands
    try:
        data = yf.download(tickers, period="60d", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        print(f"Error downloading bulk data from yfinance: {e}")
        return [], [], []

    processed_stocks = []
    anomalies = []
    insufficient_data_stocks = []

    # Support both multi-index columns and single ticker DataFrame
    has_multi_index = isinstance(data.columns, pd.MultiIndex)

    for ticker in tickers:
        try:
            if has_multi_index:
                if ticker not in data.columns.levels[0]:
                    print(f"No data returned for ticker: {ticker}")
                    continue
                df = data[ticker].copy()
            else:
                df = data.copy()
            
            # Clean up missing rows
            df = df.dropna(subset=['Close', 'Volume'])
            
            # Skip delisted or empty tickers
            if len(df) == 0:
                continue

            # Need at least 21 days for moving average calculations
            if len(df) < 21:
                insufficient_data_stocks.append(ticker)
                continue

            # Extract Close and Volume histories
            close_history = df['Close']
            volume_history = df['Volume']

            current_close = float(close_history.iloc[-1])
            previous_close = float(close_history.iloc[-2])
            current_volume = float(volume_history.iloc[-1])

            # Calculate price percentage change from previous close
            pct_change = ((current_close - previous_close) / previous_close) * 100.0

            # Calculate 20-period moving average of volume excluding today
            vol_history = volume_history.iloc[-21:-1]
            if len(vol_history) < 20:
                vol_history = volume_history.iloc[-20:]
                
            avg_volume_20 = float(vol_history.mean())

            # Liquidity Requirement: Discard any stock with an average daily volume below 1,000,000
            if avg_volume_20 < 1000000:
                continue

            # Calculate Volume Ratio and Volume vs Avg (%)
            vol_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 0.0
            vol_vs_avg = (vol_ratio - 1.0) * 100.0

            # Volume Spike: current volume is at least 3% higher than 20-period moving average
            is_spike = vol_vs_avg >= 3.0
            alert_status = "Spike" if is_spike else ""

            # 1. Calculate Wilder's RSI (14-day)
            rsi_series = calculate_rsi(close_history, period=14)
            latest_rsi = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0

            # 2. Calculate Bollinger Bands (20-day)
            sma_20_series = close_history.rolling(window=20).mean()
            std_20_series = close_history.rolling(window=20).std()
            
            latest_sma_20 = float(sma_20_series.iloc[-1])
            latest_std_20 = float(std_20_series.iloc[-1])
            
            latest_upper_bb = latest_sma_20 + 2.0 * latest_std_20
            latest_lower_bb = latest_sma_20 - 2.0 * latest_std_20

            # 3. Calculate Daily Return Standard Deviation (for high volatility move detection)
            pct_changes_series = close_history.pct_change() * 100.0
            std_pct_series = pct_changes_series.rolling(window=20).std()
            latest_std_pct = float(std_pct_series.iloc[-1]) if not np.isnan(std_pct_series.iloc[-1]) else 0.0
            is_high_volatility = abs(pct_change) > (2.0 * latest_std_pct) if latest_std_pct > 0 else False

            # 4. Generate Signals
            signals = []
            if current_close > latest_upper_bb and vol_ratio >= 1.5:
                signals.append("Bullish BB")
            elif current_close < latest_lower_bb and vol_ratio >= 1.5:
                signals.append("Bearish BB")
            elif vol_ratio >= 2.0:
                signals.append("Vol Surge")

            if latest_rsi >= 70:
                signals.append("Overbought")
            elif latest_rsi <= 30:
                signals.append("Oversold")

            if is_high_volatility and not any("BB" in s for s in signals):
                signals.append("High Vol")

            signal_str = ", ".join(signals) if signals else "Normal"

            stock_info = {
                "Ticker": ticker,
                "Close": current_close,
                "pct_change": pct_change,
                "avg_volume": avg_volume_20,
                "current_volume": current_volume,
                "vol_vs_avg": vol_vs_avg,
                "vol_ratio": vol_ratio,
                "rsi": latest_rsi,
                "upper_bb": latest_upper_bb,
                "lower_bb": latest_lower_bb,
                "sma_20": latest_sma_20,
                "alert_status": alert_status,
                "signal": signal_str
            }

            processed_stocks.append(stock_info)

            # Anomaly: Extreme price move (over 5% absolute) without corresponding volume spike
            if abs(pct_change) > 5.0 and not is_spike:
                anomalies.append(stock_info)

        except Exception as e:
            print(f"Error processing ticker {ticker}: {str(e)}")
            continue

    return processed_stocks, anomalies, insufficient_data_stocks

