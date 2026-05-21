import os
from groq import Groq

def generate_report(top_20_stocks, anomalies, insufficient_stocks):
    """
    Sends the processed data to the Groq API (Llama 3.3) to generate
    the final report, complete with the stock table, anomaly note,
    buy/sell advice, and speculation on price movements.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Warning: GROQ_API_KEY environment variable is not set. Generating a fallback template report.")
        return generate_fallback_report(top_20_stocks, anomalies, insufficient_stocks)

    # Initialize the Groq client
    client = Groq(api_key=api_key)

    # Prepare data description for the prompt
    table_data_str = ""
    for idx, s in enumerate(top_20_stocks):
        table_data_str += f"{s['Ticker']}: Price = {s['Close']:.2f}, Change = {s['pct_change']:.2f}%, Vol Ratio = {s['vol_ratio']:.1f}x, RSI = {s['rsi']:.0f}, Signal = {s['signal']}\n"

    anomalies_str = ", ".join([s['Ticker'] for s in anomalies]) if anomalies else "None"
    insufficient_str = ", ".join(insufficient_stocks) if insufficient_stocks else "None"

    # Create the prompt adhering strictly to the user's rules
    prompt = f"""
You are a senior Wall Street quantitative analyst and market auditor.
I am providing you with processed US stock market data below. Please format and analyze this data according to these strict rules:

1. Data Filtering & Analysis:
• Liquidity Requirement: Already applied (all stocks below 1,000,000 avg volume are discarded).
• Technical Indicators: We have computed 14-day Wilder's RSI, 20-day Bollinger Bands (BB), and Volume Ratio (current volume / 20-day average volume).
• Technical Signals: Already generated (e.g. Bullish BB, Bearish BB, Vol Surge, Overbought, Oversold, High Vol, Normal).

2. Output Requirements:
• Create a clean ASCII table showing the Top 20 stocks by percentage change that pass the liquidity filter.
• Format the table inside a <pre>...</pre> block (so it renders in monospaced font on Telegram).
• The table MUST use this exact header and column spacing (total 58 characters wide) to prevent wrapping on mobile:
Ticker | Price   | Chg%    | VolR  | RSI | Signal         
----------------------------------------------------------
(Format each row using: Ticker (6 chars, left), Close (7 chars, right, 2 decimal places), pct_change (7 chars, right, 1 decimal place with sign, e.g. +12.4%), vol_ratio (5 chars, right, 1 decimal place, e.g. 3.4x), rsi (3 chars, right, integer), signal (15 chars, left))
• Add a brief note at the end identifying any stock that had an extreme price move (over 5% absolute change) without a corresponding volume spike (this helps spot anomalies).
• Provide sharp quantitative insights and speculation on why these stocks moved (e.g. catalyst news, sector shifts, technical breakouts, overbought/oversold reversals).
• Do provide professional commentary and short-term tactical bias/advice for the top stocks or anomalies.
• If the data provided is insufficient to calculate indicators, list them.

Processed Data:
- Top Stocks to display in Table:
{table_data_str}

- Anomalies (Extreme price move >5% without volume spike):
{anomalies_str}

- Stocks with Insufficient Data:
{insufficient_str}

Format the entire message in HTML suitable for Telegram. 
Do NOT use unsupported HTML tags like <table>, <tr>, <td>, <h1>, <h2>, etc. 
Use ONLY:
- <b>...</b> for bold
- <i>...</i> for italic
- <pre>...</pre> for the monospaced ASCII table
- <code>...</code> for inline code
- Inline links: <a href="url">link text</a>

Keep the report concise, professional, and quantitative. Start directly with the report.
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior quantitative market analyst compiling a daily stock report for a Telegram channel. You format outputs strictly in Telegram-compatible HTML."
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
        print(f"Error generating commentary from Groq: {e}")
        return generate_fallback_report(top_20_stocks, anomalies, insufficient_stocks)

def generate_fallback_report(top_20_stocks, anomalies, insufficient_stocks):
    """
    Fallback report generator in case Groq API is unavailable or fails.
    """
    report = "<b>📊 US STOCK MARKET DAILY AUDIT REPORT</b>\n\n"
    report += "<pre>"
    report += f"{'Ticker':<6} | {'Price':>7} | {'Chg%':>7} | {'VolR':>5} | {'RSI':>3} | {'Signal':<15}\n"
    report += "-" * 58 + "\n"
    for s in top_20_stocks[:20]:
        change_str = f"{s['pct_change']:+.1f}%"
        vol_str = f"{s['vol_ratio']:.1f}x"
        rsi_val = int(round(s['rsi']))
        sig_str = s['signal'][:15]
        report += f"{s['Ticker']:<6} | {s['Close']:>7.2f} | {change_str:>7} | {vol_str:>5} | {rsi_val:>3} | {sig_str:<15}\n"
    report += "</pre>\n\n"

    report += "<b>⚠️ ANOMALIES (Price Move &gt;5% without Volume Spike):</b>\n"
    if anomalies:
        for a in anomalies:
            report += f"• {a['Ticker']} ({a['pct_change']:+.2f}%, VolR: {a['vol_ratio']:.1f}x)\n"
    else:
        report += "• None\n"
    report += "\n"

    if insufficient_stocks:
        report += f"<b>⚠️ Insufficient data for trend analysis for:</b>\n"
        report += f"• {', '.join(insufficient_stocks)}\n\n"

    report += "<b>💡 QUANTITATIVE MARKET ADVICE (Fallback):</b>\n"
    report += "• <i>Note: Groq API was unavailable to generate live commentary.</i>\n"
    report += "• Focus on stocks with 'Bullish BB' or 'Bearish BB' breakout signals and high 'VolR' (Volume Ratio) as they suggest institutional momentum.\n"
    report += "• Keep an eye on 'Oversold' (RSI <= 30) or 'Overbought' (RSI >= 70) indicators for potential mean-reversion trade setups.\n"
    
    return report

