import os
from groq import Groq


def _get_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    return Groq(api_key=api_key)


def _format_volume(vol):
    """Format raw volume as human-readable string: 1.2M, 45.3M, 890M."""
    if vol >= 1_000_000_000:
        return f"{vol / 1_000_000_000:.1f}B"
    elif vol >= 1_000_000:
        return f"{vol / 1_000_000:.1f}M"
    elif vol >= 1_000:
        return f"{vol / 1_000:.1f}K"
    return str(int(vol))


def _conf_emoji(conf):
    """Return an emoji based on the bullish confidence score (0–100)."""
    if conf >= 80:
        return "🔥"   # Strong Bull
    elif conf >= 65:
        return "🚀"   # Bullish
    elif conf >= 50:
        return "🟢"   # Mild Bull
    elif conf >= 35:
        return "🟡"   # Neutral / Watch
    elif conf >= 20:
        return "🔴"   # Bearish
    else:
        return "⛔"   # Strong Bear


def _conf_label(conf):
    """Return a short text label for a bullish confidence score."""
    if conf >= 80:
        return "Strong Bull"
    elif conf >= 65:
        return "Bullish"
    elif conf >= 50:
        return "Mild Bull"
    elif conf >= 35:
        return "Neutral"
    elif conf >= 20:
        return "Bearish"
    else:
        return "Strong Bear"


def _build_snapshot(top_stocks, n=6):
    """
    Build a quick emoji Signal Snapshot for the top N stocks (by relative volume).
    Designed to be read in 10 seconds — emojis, ticker, key numbers, and AI verdict.
    """
    lines = ["<b>⚡ Quick Snapshot — Top Movers</b>"]
    for s in top_stocks[:n]:
        emoji  = _conf_emoji(s["bullish_conf"])
        label  = _conf_label(s["bullish_conf"])
        volr   = f"{s['vol_ratio']:.1f}x"
        chg    = f"{s['pct_change']:+.1f}%"
        conf   = s["bullish_conf"]
        
        # Add trend indicators for quick skimming
        trend_suffix = ""
        if s.get("persistence") == "4/4" or s.get("persistence") == "5/5":
            trend_suffix += " ⭐"  # Persistent signal
        if s.get("price_trend") == "Continuation":
            trend_suffix += " 📈"  # Making higher highs
        elif s.get("price_trend") == "Reversing":
            trend_suffix += " 📉"  # Making lower lows
        if s.get("vol_trend") == "Accelerating":
            trend_suffix += " ⚡"  # Volume building up
            
        lines.append(
            f"{emoji} <b>{s['Ticker']}</b>{trend_suffix}: {chg} | VolR {volr} | "
            f"AI: <b>{conf}%</b> {label}"
        )
    return "\n".join(lines)


def generate_report(top_stocks, anomalies, insufficient_stocks, news_data=None):
    """
    Sends rich OHLCV + indicator data (incl. AI Bullish Confidence %) to Groq
    to generate an in-depth US stock market signal report for Telegram.
    """
    client = _get_client()
    if not client:
        print("Warning: GROQ_API_KEY not set. Generating fallback report.")
        return generate_fallback_report(top_stocks, anomalies, insufficient_stocks)

    # ── Build per-stock data string for the Groq prompt ───────────────────────
    stock_lines = []
    for s in top_stocks[:20]:
        vol_str     = _format_volume(s["current_volume"])
        avg_vol_str = _format_volume(s["avg_volume"])
        stock_lines.append(
            f"{s['Ticker']}: "
            f"O={s['Open']:.2f} H={s['High']:.2f} L={s['Low']:.2f} C={s['Close']:.2f} | "
            f"Chg={s['pct_change']:+.2f}% | "
            f"Vol={vol_str} (Avg={avg_vol_str}) VolR={s['vol_ratio']:.1f}x | "
            f"RSI={s['rsi']:.0f} | BB: price is {s['bb_label']} | "
            f"AI Conf={s['bullish_conf']}% ({_conf_label(s['bullish_conf'])}) | "
            f"Trend: Persist={s.get('persistence','1/1')} Price={s.get('price_trend','Neutral')} Vol={s.get('vol_trend','Neutral')} | "
            f"Signal: {s['signal']}"
        )
    stock_data_str = "\n".join(stock_lines)

    anomalies_str = "\n".join(
        [f"  {a['Ticker']}: Chg={a['pct_change']:+.2f}%, VolR={a['vol_ratio']:.1f}x, Conf={a['bullish_conf']}%"
         for a in anomalies]
    ) if anomalies else "  None"

    insufficient_str = ", ".join(insufficient_stocks) if insufficient_stocks else "None"

    # Build news prompt section if news_data is provided
    news_prompt_addition = ""
    if news_data:
        ticker_news_str = ""
        insider_txs_str = ""
        
        if news_data.get("ticker_news"):
            for ticker, articles in news_data["ticker_news"].items():
                if articles:
                    ticker_news_str += f"\nNews/Events for {ticker}:\n"
                    for art in articles:
                        ticker_news_str += f"  - {art.get('headline')} (Source: {art.get('source')})\n"
                        
        if news_data.get("insider_transactions"):
            top_tickers = {s["Ticker"] for s in top_stocks}
            for tx in news_data["insider_transactions"]:
                if tx.get("symbol") in top_tickers:
                    change_type = "BUY" if tx.get("change", 0) > 0 else "SELL"
                    insider_txs_str += (
                        f"  - {tx.get('symbol')}: {tx.get('name')} ({tx.get('position')}) "
                        f"{change_type} {abs(tx.get('change', 0)):,} shares (Date: {tx.get('transactionDate')})\n"
                    )
                    
        if ticker_news_str or insider_txs_str:
            news_prompt_addition = f"\n=== NEWS & INSIDER MOVES FOR THESE STOCKS ==={ticker_news_str}{insider_txs_str}\n"

    prompt = f"""
You are a senior Wall Street quantitative analyst writing a real-time stock signal report for a professional Telegram trading channel.

Every stock below was pre-screened for live signals (volume surge, RSI extreme, or significant price move).
An "AI Bullish Confidence" score (0–100%) is already pre-computed from technical indicators — use it in your analysis but you may also refine it based on OHLC candle patterns.
{news_prompt_addition}
=== TODAY'S ACTIVE SIGNAL STOCKS (Top 20 by price change) ===
{stock_data_str}

=== ANOMALIES (Price move >5% but NO volume spike) ===
{anomalies_str}

=== INSUFFICIENT DATA ===
{insufficient_str}

=== REPORT REQUIREMENTS ===

1. Start with: <b>📊 US MARKET SIGNAL REPORT</b>

2. <b>Stock Table</b> in a <pre>...</pre> block. Use EXACTLY this format (59 chars wide):
Ticker | Price   | Chg%  | VolR | RSI | Conf | Signal
-----------------------------------------------------------
Each row:
  - Ticker: 6 chars, left-aligned
  - Price: 7 chars, right, 2 decimal places
  - Chg%: 6 chars, right, 1dp with sign (e.g. +12.4%)
  - VolR: 5 chars, right, 1dp + "x" (e.g.  3.4x)
  - RSI: 3 chars, right, integer
  - Conf: 4 chars, right, integer + "%" (e.g.  72%)
  - Signal: 13 chars, left

3. <b>⚡ Deep Analysis — Top 5 Movers</b>:
   For each of the top 5 stocks by VolR, write 2-3 sentences covering:
   - What the OHLC candle shape tells us (e.g. "wide range bar closing near highs = strong buying pressure")
   - Why volume might be spiking (earnings catalyst, sector rotation, short squeeze, news?)
   - Final verdict using EXACTLY this format: <b>📈 Bullish</b>, <b>📉 Bearish</b>, <b>👀 Watch</b>, or <b>🚫 Avoid</b> with a one-line reason

4. <b>⚠️ Anomalies</b> — Briefly explain each stock with extreme move but no volume. Could be thin liquidity, news gap, or halt.

5. <b>🌡️ Market Pulse</b> — 2-3 sentences: What sector/theme is dominating? Macro driver? Risk-on or risk-off tone?

=== FORMATTING RULES ===
- Use ONLY Telegram HTML: <b>, <i>, <pre>, <code>, <a href="">
- NO markdown, NO <table>, NO <h1>, NO <h2>
- Emojis are welcome throughout — they help readability
- Keep the full report 600–900 words
- Start directly with the report, no preamble
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior quantitative market analyst writing a real-time stock signal report "
                        "for a professional Telegram trading channel. Produce sharp, data-driven insights with "
                        "clear tactical bias. Use Telegram-compatible HTML and emojis for readability."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            max_tokens=2048
        )
        groq_report = response.choices[0].message.content

        # Prepend the emoji Quick Snapshot for instant skimming
        # Sort top_stocks by vol_ratio descending to surface highest activity first
        top_by_vol = sorted(top_stocks, key=lambda x: x["vol_ratio"], reverse=True)
        snapshot   = _build_snapshot(top_by_vol, n=6)
        return snapshot + "\n\n" + groq_report

    except Exception as e:
        print(f"Error calling Groq API: {e}")
        return generate_fallback_report(top_stocks, anomalies, insufficient_stocks)


def generate_weekly_summary(all_stocks):
    """
    Generates a Friday end-of-week / market-close summary using Groq.
    Called once when the market closes (first run after 4 PM ET).
    This report wraps up the week's price action and forecasts the next week's outlook
    using deep trend insights (persistence, volume trends, adjusted confidence).
    """
    client = _get_client()
    if not client:
        return generate_fallback_close_report(all_stocks)

    # Take top 20 movers to provide comprehensive context
    top_movers = all_stocks[:20]

    stock_lines = []
    for s in top_movers:
        vol_str     = _format_volume(s["current_volume"])
        avg_vol_str = _format_volume(s["avg_volume"])
        stock_lines.append(
            f"{s['Ticker']}: "
            f"O={s['Open']:.2f} H={s['High']:.2f} L={s['Low']:.2f} C={s['Close']:.2f} | "
            f"Chg={s['pct_change']:+.2f}% | "
            f"Vol={vol_str} (Avg={avg_vol_str}) VolR={s['vol_ratio']:.1f}x | "
            f"RSI={s['rsi']:.0f} | BB: price is {s['bb_label']} | "
            f"AI Conf={s['bullish_conf']}% ({_conf_label(s['bullish_conf'])}) | "
            f"Trend: Persist={s.get('persistence','1/1')} Price={s.get('price_trend','Neutral')} Vol={s.get('vol_trend','Neutral')} | "
            f"Signal: {s['signal']}"
        )
    movers_str = "\n".join(stock_lines) if stock_lines else "No significant movers today."

    prompt = f"""
You are a senior Wall Street market strategist writing a weekly wrap-up and next-week forecast for a professional Telegram trading channel.

The US stock market has just closed for the week. Below is the closing and trend data for the top active stocks:
- **Persistence (e.g. 4/5)**: How consistently the ticker was flagged in scanning snapshots today.
- **Price Trend (Continuation / Reversing)**: Directional intraday trend behavior.
- **Vol Trend (Accelerating / Fading)**: Volume behavior towards the weekly close.
- **AI Conf (0-100%)**: Pre-computed bullish confidence.

=== WEEK'S MOVER DATA ===
{movers_str}

=== REPORT REQUIREMENTS ===

1. Start with: <b>🔔 Weekly Market Close Summary & Next-Week Forecast</b>

2. <b>📈 Weekly Movers Recap</b>:
   Summarize the most significant moves of the week. Highlight the key drivers behind the volume spikes and price extensions.

3. <b>🔮 Deep Insight: Next-Week Outlook</b>:
   Select 3-5 of the top movers and analyze their charts based on today's candle close and accumulated trends. Provide a clear, actionable forecast for their price action next week (e.g., Bullish Continuation, Support Retest, Pullback/Reversal, Consolidation).
   Use emojis next to each ticker: 📈 (Bullish), 📉 (Bearish), or 👀 (Watch).

4. <b>🧭 Macro & Sector Sentiment</b>:
   What sector or theme dominated the week? What is the prevailing market sentiment (risk-on/risk-off) going into next week's open?

5. End with: <b>💤 Market Status:</b> <i>The market is now closed for the weekend. Monitoring resumes Monday at market open.</i>

=== FORMATTING RULES ===
- Use ONLY Telegram HTML: <b>, <i>, <pre>, <code>
- Use emojis generously to make it easy to skim
- No markdown, no <table> tags
- Under 600 words
- Start directly with the report, no preamble
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional market strategist writing a weekly market close report and next-week outlook for a Telegram channel. Use Telegram HTML and emojis."
                },
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=1536
        )

        groq_report = response.choices[0].message.content
        snapshot    = _build_snapshot(top_movers, n=5)
        return snapshot + "\n\n" + groq_report

    except Exception as e:
        print(f"Error calling Groq for weekly summary: {e}")
        return generate_fallback_close_report(all_stocks)


def generate_daily_close_summary(all_stocks, anomalies, insufficient_stocks, news_data=None):
    """
    Generates a Monday-Thursday end-of-day market-close summary using Groq.
    This report contains today's market wrap-up and a detailed, data-driven
    forecast for the next day's trading session using accumulated intraday trend metrics.
    """
    client = _get_client()
    if not client:
        return generate_fallback_daily_close_report(all_stocks, anomalies, insufficient_stocks)

    # Top 20 stocks by volume ratio or price change
    top_stocks = all_stocks[:20]

    stock_lines = []
    for s in top_stocks:
        vol_str     = _format_volume(s["current_volume"])
        avg_vol_str = _format_volume(s["avg_volume"])
        stock_lines.append(
            f"{s['Ticker']}: "
            f"O={s['Open']:.2f} H={s['High']:.2f} L={s['Low']:.2f} C={s['Close']:.2f} | "
            f"Chg={s['pct_change']:+.2f}% | "
            f"Vol={vol_str} (Avg={avg_vol_str}) VolR={s['vol_ratio']:.1f}x | "
            f"RSI={s['rsi']:.0f} | BB: price is {s['bb_label']} | "
            f"AI Conf={s['bullish_conf']}% ({_conf_label(s['bullish_conf'])}) | "
            f"Trend: Persist={s.get('persistence','1/1')} Price={s.get('price_trend','Neutral')} Vol={s.get('vol_trend','Neutral')} | "
            f"Signal: {s['signal']}"
        )
    stock_data_str = "\n".join(stock_lines)

    anomalies_str = "\n".join(
        [f"  {a['Ticker']}: Chg={a['pct_change']:+.2f}%, VolR={a['vol_ratio']:.1f}x, Conf={a['bullish_conf']}%"
         for a in anomalies]
    ) if anomalies else "  None"

    insufficient_str = ", ".join(insufficient_stocks) if insufficient_stocks else "None"

    # Build news prompt section if news_data is provided
    news_prompt_addition = ""
    if news_data:
        ticker_news_str = ""
        insider_txs_str = ""
        
        if news_data.get("ticker_news"):
            for ticker, articles in news_data["ticker_news"].items():
                if articles:
                    ticker_news_str += f"\nNews/Events for {ticker}:\n"
                    for art in articles:
                        ticker_news_str += f"  - {art.get('headline')} (Source: {art.get('source')})\n"
                        
        if news_data.get("insider_transactions"):
            top_tickers = {s["Ticker"] for s in top_stocks}
            for tx in news_data["insider_transactions"]:
                if tx.get("symbol") in top_tickers:
                    change_type = "BUY" if tx.get("change", 0) > 0 else "SELL"
                    insider_txs_str += (
                        f"  - {tx.get('symbol')}: {tx.get('name')} ({tx.get('position')}) "
                        f"{change_type} {abs(tx.get('change', 0)):,} shares (Date: {tx.get('transactionDate')})\n"
                    )
                    
        if ticker_news_str or insider_txs_str:
            news_prompt_addition = f"\n=== NEWS & INSIDER MOVES FOR THESE STOCKS ==={ticker_news_str}{insider_txs_str}\n"

    prompt = f"""
You are a senior Wall Street quantitative strategist writing a daily close report and next-day forecast for a professional Telegram trading channel.
{news_prompt_addition}

Today's trading session has just concluded. Below is the final data for the most active stocks, including accumulated trend indicators from snapshot checks conducted throughout the day:
- **Persistence (e.g. 4/5)**: How consistently the ticker was flagged in scanning snapshots today. Higher persistence indicates sustained buying/selling pressure.
- **Price Trend (Continuation / Reversing)**: Indicates whether price action was consistently building higher highs or reversing throughout the session.
- **Vol Trend (Accelerating / Fading)**: Indicates whether institutional volume was building up or tapering off into the close.
- **AI Conf (0-100%)**: Pre-computed bullish confidence adjusted by persistence and trend factors.

=== TODAY'S CLOSING STOCK DATA (Top 20 by activity) ===
{stock_data_str}

=== ANOMALIES (Price move >5% but NO volume spike) ===
{anomalies_str}

=== INSUFFICIENT DATA ===
{insufficient_str}

=== REPORT REQUIREMENTS ===

1. Start with: <b>🔔 US DAILY MARKET CLOSE & NEXT-DAY FORECAST</b>

2. <b>Stock Table</b> in a <pre>...</pre> block. Use EXACTLY this format (59 chars wide):
Ticker | Price   | Chg%  | VolR | RSI | Conf | Signal
-----------------------------------------------------------
Each row:
  - Ticker: 6 chars, left-aligned
  - Price: 7 chars, right, 2 decimal places
  - Chg%: 6 chars, right, 1dp with sign (e.g. +12.4%)
  - VolR: 5 chars, right, 1dp + "x" (e.g.  3.4x)
  - RSI: 3 chars, right, integer
  - Conf: 4 chars, right, integer + "%" (e.g.  72%)
  - Signal: 13 chars, left

3. <b>🔮 Deep Insight: Next-Day Price Action Forecast</b>:
   Select the 3-5 most compelling setups based on persistence, volume trends, and candle structures. For each:
   - Provide a precise next-day outlook (e.g., Continuation, Breakout, Pullback, or Reversal).
   - Use the candle shape (Open, High, Low, Close relation) and Volume Trend to justify the forecast.
   - Use emojis next to each ticker to indicate the directional bias: 📈 (Bullish Continuation), 📉 (Bearish Extension/Pullback), or 👀 (Watch/Consolidation).

4. <b>⚠️ Anomalies & Key Risks</b>:
   Comment briefly on any key stock anomalies or risk factors to watch.

5. <b>🌡️ Closing Market Pulse</b>:
   Synthesize the overall market tone. What does today's close suggest about the opening direction for tomorrow's session?

=== FORMATTING RULES ===
- Use ONLY Telegram HTML: <b>, <i>, <pre>, <code>, <a href="">
- NO markdown, NO <table>, NO <h1>, NO <h2>
- Emojis are welcome throughout — they help readability
- Keep the full report 500–700 words
- Start directly with the report, no preamble
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior quantitative strategist writing a daily close market report "
                        "and next-day forecast for a Telegram trading channel. Provide high-density, "
                        "professional analysis. Format output strictly in Telegram HTML."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.25,
            max_tokens=1536
        )
        groq_report = response.choices[0].message.content

        # Prepend the emoji Quick Snapshot for instant skimming
        top_by_vol = sorted(all_stocks, key=lambda x: x["vol_ratio"], reverse=True)
        snapshot   = _build_snapshot(top_by_vol, n=6)
        return snapshot + "\n\n" + groq_report

    except Exception as e:
        print(f"Error calling Groq for daily close summary: {e}")
        return generate_fallback_daily_close_report(all_stocks, anomalies, insufficient_stocks)


def generate_fallback_report(top_stocks, anomalies, insufficient_stocks):
    """
    Fallback report used when Groq API is unavailable.
    Includes emoji snapshot + table with Conf column.
    """
    # Sort by vol_ratio descending for snapshot
    top_by_vol = sorted(top_stocks, key=lambda x: x["vol_ratio"], reverse=True)
    snapshot   = _build_snapshot(top_by_vol, n=6)

    report  = snapshot + "\n\n"
    report += "<b>📊 US MARKET SIGNAL REPORT</b>\n\n"
    report += "<pre>"
    report += f"{'Ticker':<6} | {'Price':>7} | {'Chg%':>6} | {'VolR':>5} | {'RSI':>3} | {'Conf':>4} | {'Signal':<13}\n"
    report += "-" * 61 + "\n"

    for s in top_stocks[:20]:
        chg_str  = f"{s['pct_change']:+.1f}%"
        vol_str  = f"{s['vol_ratio']:.1f}x"
        rsi_val  = int(round(s["rsi"]))
        conf_str = f"{s['bullish_conf']}%"
        sig_str  = s["signal"][:13]
        report  += (
            f"{s['Ticker']:<6} | {s['Close']:>7.2f} | {chg_str:>6} | "
            f"{vol_str:>5} | {rsi_val:>3} | {conf_str:>4} | {sig_str:<13}\n"
        )
    report += "</pre>\n\n"

    report += "<b>⚠️ Anomalies (Price &gt;5%, no volume spike):</b>\n"
    if anomalies:
        for a in anomalies:
            emoji = _conf_emoji(a["bullish_conf"])
            report += f"{emoji} {a['Ticker']}: {a['pct_change']:+.2f}% | VolR {a['vol_ratio']:.1f}x | Conf {a['bullish_conf']}%\n"
    else:
        report += "• None\n"
    report += "\n"

    if insufficient_stocks:
        report += f"<b>⚠️ Insufficient data:</b> {', '.join(insufficient_stocks)}\n\n"

    report += "<b>💡 Note:</b> <i>Groq API unavailable — fallback table shown.</i>\n"
    return report


def generate_fallback_daily_close_report(all_stocks, anomalies, insufficient_stocks):
    """Fallback daily close report if Groq is unavailable."""
    top_by_vol = sorted(all_stocks, key=lambda x: x["vol_ratio"], reverse=True)
    snapshot = _build_snapshot(top_by_vol, n=6)

    report  = "<b>🔔 US DAILY MARKET CLOSE & NEXT-DAY FORECAST</b>\n\n"
    report += snapshot + "\n\n"
    
    report += "<pre>"
    report += f"{'Ticker':<6} | {'Price':>7} | {'Chg%':>6} | {'VolR':>5} | {'RSI':>3} | {'Conf':>4} | {'Signal':<13}\n"
    report += "-" * 61 + "\n"

    for s in all_stocks[:20]:
        chg_str  = f"{s['pct_change']:+.1f}%"
        vol_str  = f"{s['vol_ratio']:.1f}x"
        rsi_val  = int(round(s["rsi"]))
        conf_str = f"{s['bullish_conf']}%"
        sig_str  = s["signal"][:13]
        report  += (
            f"{s['Ticker']:<6} | {s['Close']:>7.2f} | {chg_str:>6} | "
            f"{vol_str:>5} | {rsi_val:>3} | {conf_str:>4} | {sig_str:<13}\n"
        )
    report += "</pre>\n\n"

    report += "<b>💡 Note:</b> <i>Groq API unavailable — daily close fallback table shown. Price monitoring resumes tomorrow at market open.</i>\n"
    return report


def generate_fallback_close_report(all_stocks):
    """Fallback close summary when Groq is unavailable."""
    top = sorted(all_stocks, key=lambda x: x["vol_ratio"], reverse=True)[:5]
    snapshot = _build_snapshot(top, n=5)

    report  = "<b>🔔 Weekly Market Close Summary & Next-Week Forecast</b>\n\n"
    report += snapshot + "\n\n"
    report += "<b>💤 Market Status:</b>\n"
    report += "<i>The market is now closed for the weekend. Monitoring resumes Monday at market open.</i>\n"
    return report


def generate_pre_market_summary(news_data):
    """
    Generates a pre-market morning briefing outlining macro trends, Fed speeches,
    market news headlines, and recent whale/insider trades using Groq.
    """
    client = _get_client()
    if not client:
        return generate_fallback_pre_market_report(news_data)

    fed_str = ""
    if news_data.get("fed_news"):
        for item in news_data["fed_news"]:
            fed_str += f"- [{item['category']}] {item['title']} (<a href='{item['link']}'>Link</a>)\n"
    else:
        fed_str = "- No new Fed speeches or press releases in the past 24 hours.\n"

    market_str = ""
    if news_data.get("market_news"):
        for item in news_data["market_news"]:
            market_str += f"- {item.get('headline')} (Source: {item.get('source')}, <a href='{item.get('url')}'>Link</a>)\n"
    else:
        market_str = "- No general market news available.\n"

    insider_str = ""
    if news_data.get("insider_transactions"):
        for tx in news_data["insider_transactions"]:
            change_type = "BUY" if tx.get("change", 0) > 0 else "SELL"
            insider_str += (
                f"- {tx.get('symbol')}: {tx.get('name')} ({tx.get('position')}) "
                f"{change_type} {abs(tx.get('change', 0)):,} shares at ${tx.get('sharePrice', 0):.2f} "
                f"(Date: {tx.get('transactionDate')})\n"
            )
    else:
        insider_str = "- No significant insider transactions detected recently.\n"

    prompt = f"""
You are a senior Wall Street quantitative strategist writing a morning pre-market briefing and day outlook for a professional Telegram trading channel.

Today is a new trading day. Below are the key macroeconomic and corporate inputs available before the market open:

=== FEDERAL RESERVE Speeches & Press Releases ===
{fed_str}

=== GENERAL MARKET NEWS & BREAKING HEADLINES ===
{market_str}

=== CRITICAL INSIDER TRANSACTION REPORTS (Form 4) ===
{insider_str}

=== REPORT REQUIREMENTS ===

1. Start with: <b>☀️ WALL STREET MORNING BRIEFING</b>

2. **Macro & Fed Policy Outlook**: Summarize the Fed speeches/releases and macro headlines. Explain how they might affect today's stock market open (e.g. interest rate expectations, sector shifts, yield action).

3. **Strategic News Highlights**: Mention 2-3 significant general news stories that traders should watch today.

4. **🐋 Insider Buy/Sell Flow**: Synthesize the insider reports. Call out any major patterns (e.g., strong executive buys in specific tickers).

5. **🔮 Today's Trading Outlook**: Provide a concise day outlook forecast: Bullish Expansion, Rangebound Consolidation, Bearish Retreat, or High Volatility Warning.

Keep the entire message concise, punchy, professional, and formatted in clean HTML (using <b>, <i>, <a> tags). Do not use Markdown (like **, ##, or *). Avoid table structures. Max 500 words.
"""
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a quantitative strategist who writes clear, professional, HTML-formatted financial briefings."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.4,
            max_tokens=1024
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling Groq for pre-market summary: {e}")
        return generate_fallback_pre_market_report(news_data)


def generate_fallback_pre_market_report(news_data):
    """Fallback pre-market report when Groq is unavailable."""
    lines = [
        "<b>☀️ WALL STREET MORNING BRIEFING (Fallback)</b>\n",
        "<i>Groq AI commentary unavailable. Raw briefing data below:</i>\n",
        "<b>🔔 Federal Reserve & Macro Events:</b>"
    ]
    
    if news_data.get("fed_news"):
        for item in news_data["fed_news"]:
            lines.append(f"- <b>{item['category']}</b>: <a href='{item['link']}'>{item['title']}</a>")
    else:
        lines.append("- No recent Fed updates.")
        
    lines.append("\n<b>📰 General Market Headlines:</b>")
    if news_data.get("market_news"):
        for item in news_data["market_news"][:5]:
            url = item.get("url", "#")
            headline = item.get("headline", "No Title")
            source = item.get("source", "Market")
            lines.append(f"- <a href='{url}'>{headline}</a> (<i>{source}</i>)")
    else:
        lines.append("- No general headlines available.")
        
    lines.append("\n<b>🐋 Insider Flows (Form 4):</b>")
    if news_data.get("insider_transactions"):
        for tx in news_data["insider_transactions"][:5]:
            change_type = "BUY" if tx.get("change", 0) > 0 else "SELL"
            lines.append(
                f"- <b>{tx.get('symbol')}</b>: {tx.get('name')} {change_type} "
                f"{abs(tx.get('change', 0)):,} shares @ ${tx.get('sharePrice', 0):.2f}"
            )
    else:
        lines.append("- No significant insider trades.")
        
    return "\n".join(lines)
