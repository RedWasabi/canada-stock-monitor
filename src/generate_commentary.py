import os
from groq import Groq


def _get_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    return Groq(api_key=api_key)


def _format_volume(vol):
    """Format raw volume number into a human-readable string: 1.2M, 45.3M, 890M."""
    if vol >= 1_000_000_000:
        return f"{vol / 1_000_000_000:.1f}B"
    elif vol >= 1_000_000:
        return f"{vol / 1_000_000:.1f}M"
    elif vol >= 1_000:
        return f"{vol / 1_000:.1f}K"
    return str(int(vol))


def generate_report(top_stocks, anomalies, insufficient_stocks):
    """
    Sends rich OHLCV + indicator data to Groq (Llama 3.3) to generate
    an in-depth US stock market report with per-stock tactical analysis.
    """
    client = _get_client()
    if not client:
        print("Warning: GROQ_API_KEY not set. Generating fallback report.")
        return generate_fallback_report(top_stocks, anomalies, insufficient_stocks)

    # ── Build rich per-stock data string for Groq ──────────────────────────────
    stock_lines = []
    for s in top_stocks[:20]:
        vol_str     = _format_volume(s["current_volume"])
        avg_vol_str = _format_volume(s["avg_volume"])
        stock_lines.append(
            f"{s['Ticker']}: "
            f"O={s['Open']:.2f} H={s['High']:.2f} L={s['Low']:.2f} C={s['Close']:.2f} | "
            f"Chg={s['pct_change']:+.2f}% | "
            f"Vol={vol_str} (Avg={avg_vol_str}) VolR={s['vol_ratio']:.1f}x | "
            f"RSI={s['rsi']:.0f} | "
            f"BB: price is {s['bb_label']} | "
            f"Signal: {s['signal']}"
        )
    stock_data_str = "\n".join(stock_lines)

    anomalies_str = "\n".join(
        [f"  {a['Ticker']}: Chg={a['pct_change']:+.2f}%, VolR={a['vol_ratio']:.1f}x" for a in anomalies]
    ) if anomalies else "  None"

    insufficient_str = ", ".join(insufficient_stocks) if insufficient_stocks else "None"

    prompt = f"""
You are a senior Wall Street quantitative analyst and market intelligence officer.

I am providing you with real-time US stock market data. Every stock listed below was pre-screened to show a live signal today (volume surge, RSI extreme, or significant price move). Your job is to produce a sharp, professional market intelligence report for a Telegram channel.

=== TODAY'S ACTIVE SIGNAL STOCKS (Top 20 by relative volume) ===
{stock_data_str}

=== ANOMALIES (Price move >5% but NO volume spike — suspicious or data gap) ===
{anomalies_str}

=== INSUFFICIENT DATA ===
{insufficient_str}

=== YOUR REPORT MUST INCLUDE ===

1. <b>📊 US MARKET SIGNAL REPORT</b> — Start with this header.

2. <b>Stock Table</b> inside a <pre>...</pre> block. Use this EXACT column format (58 chars wide):
Ticker | Price   | Chg%    | VolR  | RSI | Signal
----------------------------------------------------------
(Ticker: 6 left, Price: 7 right 2dp, Chg%: 7 right 1dp with sign, VolR: 5 right 1dp + "x", RSI: 3 right int, Signal: 15 left)

3. <b>🔍 Deep Stock Analysis</b> — For each stock in the top 5 by relative volume, write 2–3 sentences covering:
   - What the OHLC shape tells us (e.g. "wide range candle with close near high = strong buying")
   - Why volume is spiking (earnings? news? sector rotation? short squeeze?)
   - Tactical bias: <b>Bullish</b>, <b>Bearish</b>, <b>Watch</b>, or <b>Avoid</b> with a one-line reason

4. <b>⚠️ Anomalies</b> — Briefly flag stocks with extreme moves but no volume (could be thin trading, halt, or bad data).

5. <b>💡 Market Pulse</b> — 2–3 sentences on the overall tone of today's active movers. What sector or theme is dominating? Any macro driver visible?

=== FORMATTING RULES ===
- Use ONLY Telegram-supported HTML: <b>, <i>, <pre>, <code>, <a href="">
- NO <table>, <tr>, <td>, <h1>, <h2>, or markdown
- Keep the full report concise — target 600–900 words
- Start directly with the report, no preamble
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior quantitative market analyst writing a real-time stock signal report for a professional Telegram channel. You produce sharp, data-driven insights with tactical buy/sell/watch bias. Format strictly in Telegram-compatible HTML."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            max_tokens=2048
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling Groq API: {e}")
        return generate_fallback_report(top_stocks, anomalies, insufficient_stocks)


def generate_weekly_summary(all_stocks):
    """
    Generates a Friday end-of-week / market-close summary using Groq.
    Called once when the market closes on Friday (or any day after 4 PM ET).
    Uses a different prompt focused on weekly recap and next-week outlook.
    """
    client = _get_client()
    if not client:
        return generate_fallback_close_report(all_stocks)

    # Pick top 10 by volume ratio for the summary
    top_movers = sorted(all_stocks, key=lambda x: x["vol_ratio"], reverse=True)[:10]

    stock_lines = []
    for s in top_movers:
        stock_lines.append(
            f"{s['Ticker']}: Chg={s['pct_change']:+.2f}%, VolR={s['vol_ratio']:.1f}x, RSI={s['rsi']:.0f}, Signal={s['signal']}"
        )
    movers_str = "\n".join(stock_lines) if stock_lines else "No significant movers."

    prompt = f"""
You are a senior Wall Street market strategist writing a weekly wrap-up for a Telegram trading channel.

The US stock market has just closed. Here are today's top movers:

{movers_str}

Write a concise weekly market close summary that includes:

1. <b>🔔 Market Close Summary</b> — Start with this header, and the date/session context.
2. <b>📈 Top Movers Recap</b> — Brief summary of the biggest moves and what they signal.
3. <b>🧭 Sector & Theme Analysis</b> — What sector or macro theme dominated today? Growth vs value? Risk-on vs risk-off?
4. <b>📅 Next Week Outlook</b> — Key things to watch next week (macro events, earnings, technical levels).
5. <b>💤 Market Status</b> — End with: "The market is now closed. The bot will resume monitoring when trading opens on Monday."

Formatting rules:
- Use ONLY Telegram-compatible HTML: <b>, <i>, <pre>, <code>
- NO markdown, NO <table> tags
- Keep it under 500 words
- Start directly with the report
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior market strategist writing a professional weekly market close summary for a Telegram trading channel. Use Telegram-compatible HTML only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=1024
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling Groq for weekly summary: {e}")
        return generate_fallback_close_report(all_stocks)


def generate_fallback_report(top_stocks, anomalies, insufficient_stocks):
    """
    Fallback table-based report used when Groq API is unavailable.
    Includes full OHLC columns for completeness.
    """
    report = "<b>📊 US MARKET SIGNAL REPORT</b>\n\n"
    report += "<pre>"
    report += f"{'Ticker':<6} | {'Price':>7} | {'Chg%':>7} | {'VolR':>5} | {'RSI':>3} | {'Signal':<15}\n"
    report += "-" * 58 + "\n"
    for s in top_stocks[:20]:
        change_str = f"{s['pct_change']:+.1f}%"
        vol_str    = f"{s['vol_ratio']:.1f}x"
        rsi_val    = int(round(s["rsi"]))
        sig_str    = s["signal"][:15]
        report += f"{s['Ticker']:<6} | {s['Close']:>7.2f} | {change_str:>7} | {vol_str:>5} | {rsi_val:>3} | {sig_str:<15}\n"
    report += "</pre>\n\n"

    report += "<b>⚠️ ANOMALIES (Price &gt;5% move, no volume spike):</b>\n"
    if anomalies:
        for a in anomalies:
            report += f"• {a['Ticker']} ({a['pct_change']:+.2f}%, VolR: {a['vol_ratio']:.1f}x)\n"
    else:
        report += "• None\n"
    report += "\n"

    if insufficient_stocks:
        report += "<b>⚠️ Insufficient data:</b>\n"
        report += f"• {', '.join(insufficient_stocks)}\n\n"

    report += "<b>💡 Note:</b>\n"
    report += "• <i>Groq API was unavailable — fallback table shown.</i>\n"
    report += "• All stocks above were pre-screened for live signals (volume spike, RSI extreme, or large price move).\n"

    return report


def generate_fallback_close_report(all_stocks):
    """Fallback close summary when Groq is unavailable."""
    top = sorted(all_stocks, key=lambda x: x["vol_ratio"], reverse=True)[:5]
    report = "<b>🔔 Market Close Summary</b>\n\n"
    report += "<b>📈 Top Movers Today:</b>\n"
    for s in top:
        report += f"• {s['Ticker']}: {s['pct_change']:+.2f}% | VolR: {s['vol_ratio']:.1f}x | RSI: {s['rsi']:.0f} | {s['signal']}\n"
    report += "\n<b>💤 Market Status:</b>\n"
    report += "The market is now closed. The bot will resume monitoring when trading opens on Monday.\n"
    return report
