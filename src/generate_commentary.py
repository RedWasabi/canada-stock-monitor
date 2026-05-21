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
        lines.append(
            f"{emoji} <b>{s['Ticker']}</b>: {chg} | VolR {volr} | "
            f"AI: <b>{conf}%</b> {label}"
        )
    return "\n".join(lines)


def generate_report(top_stocks, anomalies, insufficient_stocks):
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
            f"Signal: {s['signal']}"
        )
    stock_data_str = "\n".join(stock_lines)

    anomalies_str = "\n".join(
        [f"  {a['Ticker']}: Chg={a['pct_change']:+.2f}%, VolR={a['vol_ratio']:.1f}x, Conf={a['bullish_conf']}%"
         for a in anomalies]
    ) if anomalies else "  None"

    insufficient_str = ", ".join(insufficient_stocks) if insufficient_stocks else "None"

    prompt = f"""
You are a senior Wall Street quantitative analyst writing a real-time stock signal report for a professional Telegram trading channel.

Every stock below was pre-screened for live signals (volume surge, RSI extreme, or significant price move).
An "AI Bullish Confidence" score (0–100%) is already pre-computed from technical indicators — use it in your analysis but you may also refine it based on OHLC candle patterns.

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
    """
    client = _get_client()
    if not client:
        return generate_fallback_close_report(all_stocks)

    top_movers = sorted(all_stocks, key=lambda x: x["vol_ratio"], reverse=True)[:10]

    stock_lines = []
    for s in top_movers:
        emoji = _conf_emoji(s["bullish_conf"])
        stock_lines.append(
            f"{emoji} {s['Ticker']}: Chg={s['pct_change']:+.2f}%, "
            f"VolR={s['vol_ratio']:.1f}x, RSI={s['rsi']:.0f}, "
            f"AI Conf={s['bullish_conf']}%, Signal={s['signal']}"
        )
    movers_str = "\n".join(stock_lines) if stock_lines else "No significant movers today."

    prompt = f"""
You are a senior Wall Street market strategist writing a weekly wrap-up for a professional Telegram trading channel.

The US stock market has just closed for the week. Here are today's top active movers:

{movers_str}

Write a concise weekly market close summary. Include:

1. Start with: <b>🔔 Weekly Market Close Summary</b>
2. <b>📈 Top Movers Recap</b> — Key moves and their meaning. Use 🔥🚀🟢🟡🔴⛔ emojis next to each ticker.
3. <b>🧭 Sector & Theme Analysis</b> — Dominant sector/macro theme today. Growth vs value? Risk-on or off?
4. <b>📅 Next Week Outlook</b> — What to watch next week: macro events, earnings, key technical levels.
5. End with: <b>💤 Market Status:</b> <i>The market is now closed. Monitoring resumes Monday at market open.</i>

Formatting rules:
- Use ONLY Telegram HTML: <b>, <i>, <pre>, <code>
- Use emojis generously — they make it easy to skim
- No markdown, no <table> tags
- Under 500 words
- Start directly with the report
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional market strategist writing a weekly market close report for a Telegram trading channel. Use Telegram HTML and emojis for maximum readability."
                },
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=1024
        )

        groq_report = response.choices[0].message.content
        snapshot    = _build_snapshot(top_movers, n=5)
        return snapshot + "\n\n" + groq_report

    except Exception as e:
        print(f"Error calling Groq for weekly summary: {e}")
        return generate_fallback_close_report(all_stocks)


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


def generate_fallback_close_report(all_stocks):
    """Fallback close summary when Groq is unavailable."""
    top = sorted(all_stocks, key=lambda x: x["vol_ratio"], reverse=True)[:5]
    snapshot = _build_snapshot(top, n=5)

    report  = "<b>🔔 Market Close Summary</b>\n\n"
    report += snapshot + "\n\n"
    report += "<b>💤 Market Status:</b>\n"
    report += "<i>The market is now closed. Monitoring resumes Monday at market open.</i>\n"
    return report
