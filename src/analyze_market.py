import pandas as pd
import yfinance as yf
import numpy as np
import time


def calculate_rsi(prices, period=14):
    """
    Calculates Wilder's RSI for a pandas Series of prices.
    Always returns a pandas Series (never a scalar NaN) even with insufficient data.
    """
    if len(prices) < period + 1:
        return pd.Series([np.nan] * len(prices), index=prices.index)

    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # Guard against division by zero (no down days in the period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calculate_bullish_confidence(pct_change, vol_ratio, rsi, signal):
    """
    Computes a 0–100 AI Bullish Confidence score based on technical indicators.
    Higher score = stronger evidence the stock will move up.

    Score components:
      - Price direction  : up to ±20 pts
      - Volume confirmation: up to ±15 pts (volume must confirm the direction)
      - RSI zone         : ±8–15 pts (oversold = bullish potential; overbought = risk)
      - Signal bonus     : ±12–15 pts (Bullish/Bearish BB, Oversold/Overbought)
    """
    score = 50  # neutral baseline

    # 1. Price direction (+20 max for strong up move, -20 for strong down)
    score += max(-20, min(20, pct_change * 2.5))

    # 2. Volume confirmation (volume must agree with the price direction)
    if vol_ratio >= 2.0 and pct_change > 0:
        score += 15   # strong volume confirms up move
    elif vol_ratio >= 1.5 and pct_change > 0:
        score += 10   # moderate volume confirms up move
    elif vol_ratio >= 2.0 and pct_change < 0:
        score -= 15   # strong volume confirms down move
    elif vol_ratio >= 1.5 and pct_change < 0:
        score -= 10

    # 3. RSI zone
    if rsi <= 30:
        score += 15   # deeply oversold → bullish reversal potential
    elif rsi <= 40:
        score += 8    # approaching oversold
    elif rsi >= 70:
        score -= 15   # overbought → limited upside, reversal risk
    elif rsi >= 65:
        score -= 8

    # 4. Signal bonus/penalty
    if "Bullish BB" in signal:
        score += 15
    elif "Bearish BB" in signal:
        score -= 15
    if "Oversold" in signal:
        score += 12
    elif "Overbought" in signal:
        score -= 12

    return max(0, min(100, int(round(score))))


def calculate_trend_metrics(ticker, snapshot_history):
    """
    Analyzes the snapshot history for a given ticker to determine:
      - persistence: fraction of snapshots where the stock was present (e.g., 3/4)
      - price_trend: "Continuation" (increasing), "Reversing" (decreasing), or "Neutral"
      - vol_trend: "Accelerating" (increasing volume ratio) or "Fading" (decreasing)
      - trend_confidence_adjustment: int value to add/subtract from base confidence
    """
    if not snapshot_history:
        return {
            "persistence": "1/1",
            "price_trend": "Neutral",
            "vol_trend": "Neutral",
            "adjustment": 0,
            "history_closes": [],
            "history_vols": []
        }
        
    prices = []
    vols = []
    present_count = 0
    total_snapshots = len(snapshot_history)
    
    for snap in snapshot_history:
        snap_data = snap.get("data", {})
        if ticker in snap_data:
            present_count += 1
            prices.append(snap_data[ticker]["close"])
            vols.append(snap_data[ticker]["vol_ratio"])
            
    persistence_str = f"{present_count}/{total_snapshots}"
    
    # Need at least 2 data points in history to calculate trend
    if len(prices) < 2:
        # If it only appeared once in multiple runs, it's a transient spike
        adjustment = -15 if total_snapshots >= 3 and present_count == 1 else 0
        return {
            "persistence": persistence_str,
            "price_trend": "Neutral",
            "vol_trend": "Neutral",
            "adjustment": adjustment,
            "history_closes": prices,
            "history_vols": vols
        }
        
    # Check price trend
    # If all consecutive changes are positive -> Continuation
    # If all consecutive changes are negative -> Reversing
    price_diffs = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    if all(d > 0 for d in price_diffs):
        price_trend = "Continuation"
        price_adj = 10
    elif all(d < 0 for d in price_diffs):
        price_trend = "Reversing"
        price_adj = -10
    else:
        price_trend = "Neutral"
        price_adj = 0
        
    # Check volume trend
    vol_diffs = [vols[i] - vols[i-1] for i in range(1, len(vols))]
    if all(d > 0 for d in vol_diffs):
        vol_trend = "Accelerating"
        vol_adj = 10
    elif all(d < 0 for d in vol_diffs):
        vol_trend = "Fading"
        vol_adj = -5
    else:
        vol_trend = "Neutral"
        vol_adj = 0
        
    # Persistence adjustment
    persist_ratio = present_count / total_snapshots
    if persist_ratio >= 0.9:
        persist_adj = 15
    elif persist_ratio >= 0.7:
        persist_adj = 10
    elif persist_ratio <= 0.3:
        persist_adj = -15
    else:
        persist_adj = 0
        
    adjustment = price_adj + vol_adj + persist_adj
    return {
        "persistence": persistence_str,
        "price_trend": price_trend,
        "vol_trend": vol_trend,
        "adjustment": adjustment,
        "history_closes": prices,
        "history_vols": vols
    }


def analyze_stocks(tickers, snapshot_history=None):
    """
    Downloads 90 days of OHLCV data for the given tickers in rate-limit-safe chunks,
    then computes technical indicators and returns:
      - processed_stocks: list of rich stock_info dicts for stocks passing liquidity filter
      - anomalies: stocks with extreme price moves (>5%) but NO volume spike
      - insufficient_data_stocks: tickers with too little history to compute indicators
    """
    print(f"Downloading data for {len(tickers)} tickers in chunked bulk format...")

    # --- Chunked Download ---
    # Download in chunks of 100 with threads=True for speed.
    # 1.5s sleep between chunks avoids Yahoo Finance rate limiting (YFRateLimitError).
    chunk_size = 100
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    chunk_dfs = []

    for idx, chunk in enumerate(chunks):
        print(f"  Chunk {idx + 1}/{len(chunks)}: downloading {len(chunk)} tickers...")
        try:
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
                chunk_dfs.append(data_chunk)
        except Exception as e:
            print(f"  Chunk {idx + 1} download failed: {e}")

        # Brief pause between chunks to avoid rate limiting
        if idx < len(chunks) - 1:
            time.sleep(1.5)

    if not chunk_dfs:
        print("Error: No data downloaded from any chunk.")
        return [], [], []

    try:
        data = pd.concat(chunk_dfs, axis=1)
    except Exception as e:
        print(f"Error merging chunk data: {e}")
        return [], [], []

    # --- Per-ticker Analysis ---
    processed_stocks = []
    anomalies = []
    insufficient_data_stocks = []

    has_multi_index = isinstance(data.columns, pd.MultiIndex)
    available_tickers = set(data.columns.get_level_values(0)) if has_multi_index else None

    for ticker in tickers:
        try:
            if has_multi_index:
                if ticker not in available_tickers:
                    continue
                df = data[ticker].copy()
            else:
                df = data.copy()

            # Drop rows missing both Close and Volume
            df = df.dropna(subset=["Close", "Volume"])

            if len(df) == 0:
                continue

            # Need at least 21 rows: 20-day avg volume + 1 previous day
            if len(df) < 21:
                insufficient_data_stocks.append(ticker)
                continue

            # ── Price History ──────────────────────────────────────
            close_history   = df["Close"]
            volume_history  = df["Volume"]

            # Today's OHLC (for Groq deep analysis)
            today_open   = float(df["Open"].iloc[-1])   if "Open"   in df.columns else float("nan")
            today_high   = float(df["High"].iloc[-1])   if "High"   in df.columns else float("nan")
            today_low    = float(df["Low"].iloc[-1])    if "Low"    in df.columns else float("nan")
            today_close  = float(close_history.iloc[-1])
            prev_close   = float(close_history.iloc[-2])
            today_volume = float(volume_history.iloc[-1])

            if prev_close == 0:
                continue

            pct_change = ((today_close - prev_close) / prev_close) * 100.0

            # ── Volume Analysis ────────────────────────────────────
            # 20-day average volume excluding today
            vol_hist_20 = volume_history.iloc[-21:-1]
            if len(vol_hist_20) < 20:
                vol_hist_20 = volume_history.iloc[:-1]
            avg_volume_20 = float(vol_hist_20.mean())

            # Liquidity filter: drop stocks with avg daily volume < 5,000,000 shares
            if avg_volume_20 < 5_000_000:
                continue

            vol_ratio   = today_volume / avg_volume_20 if avg_volume_20 > 0 else 0.0
            vol_vs_avg  = (vol_ratio - 1.0) * 100.0
            is_spike    = vol_vs_avg >= 3.0
            alert_status = "Spike" if is_spike else ""

            # ── RSI (14-day Wilder's) ──────────────────────────────
            rsi_series  = calculate_rsi(close_history, period=14)
            last_rsi    = rsi_series.iloc[-1]
            latest_rsi  = float(last_rsi) if not np.isnan(last_rsi) else 50.0

            # ── Bollinger Bands (20-day) ───────────────────────────
            sma_20_s = close_history.rolling(window=20).mean()
            std_20_s = close_history.rolling(window=20).std()
            latest_sma_20 = float(sma_20_s.iloc[-1])
            latest_std_20 = float(std_20_s.iloc[-1])

            if np.isnan(latest_sma_20) or np.isnan(latest_std_20):
                continue

            upper_bb = latest_sma_20 + 2.0 * latest_std_20
            lower_bb = latest_sma_20 - 2.0 * latest_std_20

            # BB position: how far price is from the band as % of band width
            # Positive = above upper band, Negative = below lower band
            band_width = upper_bb - lower_bb if (upper_bb - lower_bb) > 0 else 1.0
            if today_close > upper_bb:
                bb_position_pct = ((today_close - upper_bb) / band_width) * 100.0
                bb_label = f"{bb_position_pct:.1f}% ABOVE upper band"
            elif today_close < lower_bb:
                bb_position_pct = ((lower_bb - today_close) / band_width) * 100.0
                bb_label = f"{bb_position_pct:.1f}% BELOW lower band"
            else:
                # Between bands: 0% = lower band, 100% = upper band
                bb_position_pct = ((today_close - lower_bb) / band_width) * 100.0
                bb_label = f"{bb_position_pct:.1f}% inside bands"

            # ── Daily Return Std Dev (for High Volatility detection) ──
            pct_changes_s = close_history.pct_change() * 100.0
            std_pct_s     = pct_changes_s.rolling(window=20).std()
            last_std_pct  = std_pct_s.iloc[-1]
            latest_std_pct = float(last_std_pct) if not np.isnan(last_std_pct) else 0.0
            is_high_vol    = abs(pct_change) > (2.0 * latest_std_pct) if latest_std_pct > 0 else False

            # ── Signal Classification ──────────────────────────────
            signals = []
            if today_close > upper_bb and vol_ratio >= 1.5:
                signals.append("Bullish BB")
            elif today_close < lower_bb and vol_ratio >= 1.5:
                signals.append("Bearish BB")
            elif vol_ratio >= 2.0:
                signals.append("Vol Surge")

            if latest_rsi >= 70:
                signals.append("Overbought")
            elif latest_rsi <= 30:
                signals.append("Oversold")

            if is_high_vol and not any("BB" in s for s in signals):
                signals.append("High Vol")

            signal_str = ", ".join(signals) if signals else "Normal"

            # Calculate base confidence
            base_conf = calculate_bullish_confidence(pct_change, vol_ratio, latest_rsi, signal_str)

            # Apply trend adjustments if snapshot history is available
            trend = calculate_trend_metrics(ticker, snapshot_history)
            final_conf = max(0, min(100, base_conf + trend["adjustment"]))

            stock_info = {
                "Ticker":          ticker,
                # OHLC for Groq deep analysis
                "Open":            today_open,
                "High":            today_high,
                "Low":             today_low,
                "Close":           today_close,
                # Change
                "pct_change":      pct_change,
                # Volume data
                "avg_volume":      avg_volume_20,
                "current_volume":  today_volume,
                "vol_vs_avg":      vol_vs_avg,
                "vol_ratio":       vol_ratio,
                # Technical indicators
                "rsi":             latest_rsi,
                "upper_bb":        upper_bb,
                "lower_bb":        lower_bb,
                "sma_20":          latest_sma_20,
                "bb_label":        bb_label,          # human-readable BB position
                # Classification
                "alert_status":    alert_status,
                "signal":          signal_str,
                # AI Bullish Confidence score (0–100)
                "bullish_conf":    final_conf,
                # Trend metrics
                "persistence":     trend["persistence"],
                "price_trend":     trend["price_trend"],
                "vol_trend":       trend["vol_trend"],
                "trend_adj":       trend["adjustment"]
            }

            processed_stocks.append(stock_info)

            # Anomaly: extreme price move (>5%) with NO volume spike — suspicious
            if abs(pct_change) > 5.0 and not is_spike:
                anomalies.append(stock_info)

        except Exception as e:
            print(f"  Error processing {ticker}: {e}")
            continue

    return processed_stocks, anomalies, insufficient_data_stocks
