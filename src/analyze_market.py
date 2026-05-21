import pandas as pd
import yfinance as yf
import numpy as np
import time


def calculate_rsi(prices, period=14):
    """
    Calculates Wilder's RSI for a pandas Series of prices.
    Returns a pandas Series of RSI values, or np.nan if not enough data.
    """
    if len(prices) < period + 1:
        # Not enough data — return a Series of NaN matching the input length
        return pd.Series([np.nan] * len(prices), index=prices.index)

    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's smoothing (alpha = 1 / period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # Avoid division by zero when avg_loss is 0
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def analyze_stocks(tickers):
    """
    Downloads historical data for the tickers, processes them, and returns:
    - A list of processed stock data dicts passing the liquidity filter
    - A list of stocks with extreme price moves without a volume spike (anomalies)
    - A list of stocks with insufficient data for volume trend analysis
    """
    print(f"Downloading data for {len(tickers)} tickers in chunked bulk format...")

    # We download in chunks of 100 to avoid Yahoo Finance rate limits (YFRateLimitError).
    # Multi-threading (threads=True) is used within each chunk to download quickly.
    chunk_size = 100
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    successful_dfs = []

    for idx, chunk in enumerate(chunks):
        print(f"Downloading chunk {idx + 1}/{len(chunks)} ({len(chunk)} tickers)...")
        try:
            # Download 90 days of data to ensure we have enough history for:
            # - 14-period Wilder's RSI (needs ~28+ trading days for warmup)
            # - 20-period Bollinger Bands (needs 20 trading days minimum)
            data_chunk = yf.download(
                chunk,
                period="90d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True
            )
            if not data_chunk.empty:
                successful_dfs.append(data_chunk)
        except Exception as e:
            print(f"Error downloading chunk {idx + 1}: {e}")

        # Sleep 1.5 seconds between chunks to respect Yahoo's rate limit policies
        time.sleep(1.5)

    if not successful_dfs:
        print("Error: Failed to download data for any tickers.")
        return [], [], []

    try:
        # Concatenate all chunked dataframes side-by-side (matching on Date index)
        data = pd.concat(successful_dfs, axis=1)
    except Exception as e:
        print(f"Error concatenating chunk data: {e}")
        return [], [], []

    processed_stocks = []
    anomalies = []
    insufficient_data_stocks = []

    # Support both multi-index columns (multiple tickers) and single-ticker DataFrame
    has_multi_index = isinstance(data.columns, pd.MultiIndex)

    # When multi-index, build a set of tickers that actually have data
    # Use get_level_values(0) instead of .levels[0] to avoid stale level cache in newer pandas
    if has_multi_index:
        available_tickers = set(data.columns.get_level_values(0))
    else:
        available_tickers = None  # single ticker mode

    for ticker in tickers:
        try:
            if has_multi_index:
                if ticker not in available_tickers:
                    # Silently skip — no data was returned for this ticker
                    continue
                df = data[ticker].copy()
            else:
                # Single ticker download — data IS the DataFrame
                df = data.copy()

            # Drop rows where both Close and Volume are missing
            df = df.dropna(subset=['Close', 'Volume'])

            # Skip delisted or completely empty tickers
            if len(df) == 0:
                continue

            # Need at least 21 rows for 20-period volume average + 1 day lookback
            if len(df) < 21:
                insufficient_data_stocks.append(ticker)
                continue

            # --- Extract price/volume history ---
            close_history = df['Close']
            volume_history = df['Volume']

            current_close = float(close_history.iloc[-1])
            previous_close = float(close_history.iloc[-2])
            current_volume = float(volume_history.iloc[-1])

            # Percentage change vs previous close
            if previous_close == 0:
                continue
            pct_change = ((current_close - previous_close) / previous_close) * 100.0

            # --- 20-period average volume (excluding today's volume) ---
            # Use the 20 days before today
            vol_history = volume_history.iloc[-21:-1]
            if len(vol_history) < 20:
                # Fallback: use whatever we have
                vol_history = volume_history.iloc[:-1]

            avg_volume_20 = float(vol_history.mean())

            # Liquidity filter: discard stocks with average daily volume below 1,000,000
            if avg_volume_20 < 1_000_000:
                continue

            # --- Volume Ratio (current volume / 20-day average volume) ---
            vol_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 0.0
            vol_vs_avg = (vol_ratio - 1.0) * 100.0

            # Volume Spike: current volume at least 3% above 20-day average
            is_spike = vol_vs_avg >= 3.0
            alert_status = "Spike" if is_spike else ""

            # --- 1. Wilder's RSI (14-day) ---
            rsi_series = calculate_rsi(close_history, period=14)
            last_rsi = rsi_series.iloc[-1]
            # If RSI is NaN (not enough data), default to neutral 50
            latest_rsi = float(last_rsi) if not np.isnan(last_rsi) else 50.0

            # --- 2. Bollinger Bands (20-day SMA ± 2 std dev) ---
            sma_20_series = close_history.rolling(window=20).mean()
            std_20_series = close_history.rolling(window=20).std()

            latest_sma_20 = float(sma_20_series.iloc[-1])
            latest_std_20 = float(std_20_series.iloc[-1])

            # Guard against NaN std (e.g. all prices identical)
            if np.isnan(latest_sma_20) or np.isnan(latest_std_20):
                continue

            latest_upper_bb = latest_sma_20 + 2.0 * latest_std_20
            latest_lower_bb = latest_sma_20 - 2.0 * latest_std_20

            # --- 3. Daily return standard deviation (for high-volatility detection) ---
            pct_changes_series = close_history.pct_change() * 100.0
            std_pct_series = pct_changes_series.rolling(window=20).std()
            last_std_pct = std_pct_series.iloc[-1]
            latest_std_pct = float(last_std_pct) if not np.isnan(last_std_pct) else 0.0
            is_high_volatility = abs(pct_change) > (2.0 * latest_std_pct) if latest_std_pct > 0 else False

            # --- 4. Generate technical signals ---
            signals = []

            # Bollinger Band breakout/breakdown (must have volume confirmation)
            if current_close > latest_upper_bb and vol_ratio >= 1.5:
                signals.append("Bullish BB")
            elif current_close < latest_lower_bb and vol_ratio >= 1.5:
                signals.append("Bearish BB")
            elif vol_ratio >= 2.0:
                signals.append("Vol Surge")

            # RSI overbought / oversold
            if latest_rsi >= 70:
                signals.append("Overbought")
            elif latest_rsi <= 30:
                signals.append("Oversold")

            # High volatility without a BB breakout (unusual price swing)
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

            # Anomaly: price moved more than 5% but no volume spike to explain it
            if abs(pct_change) > 5.0 and not is_spike:
                anomalies.append(stock_info)

        except Exception as e:
            print(f"Error processing ticker {ticker}: {str(e)}")
            continue

    return processed_stocks, anomalies, insufficient_data_stocks
