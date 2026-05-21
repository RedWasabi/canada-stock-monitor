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
        table_data_str += f"{s['Ticker']}: Price Change = {s['pct_change']:.2f}%, Vol vs Avg = {s['vol_vs_avg']:.2f}%, Alert = {s['alert_status']}\n"

    anomalies_str = ", ".join([s['Ticker'] for s in anomalies]) if anomalies else "None"
    insufficient_str = ", ".join(insufficient_stocks) if insufficient_stocks else "None"

    # Create the prompt adhering strictly to the user's rules
    prompt = f"""
You are a professional financial data auditor.
I am providing you with processed Canadian market data below. Please format and analyze this data according to these strict rules:

1. Data Filtering:
• Liquidity Requirement: Already applied (all stocks below 1,000,000 avg volume are discarded).
• Volume Spike: Stocks with volume at least 3% higher than the 20-period moving average are marked as 'Spike'.
• Percentage Change: Already calculated.

2. Output Requirements:
• Create an ASCII table showing the Top 20 stocks by percentage change that pass the liquidity filter.
• Format the table inside a <pre>...</pre> block (so it renders in monospaced font on Telegram).
• The table must include these columns: Ticker, % Change, Volume vs. Avg (%), and Alert Status (Note 'Spike' if volume exceeds the threshold).
• Add a brief note at the end identifying any stock that had an extreme price move (over 5% absolute change) without a corresponding volume spike (this helps spot anomalies).
• Do provide buy/sell advice for the top stocks or anomalies.
• Do speculate on why a price moved (e.g. market trends, sector shifts, general speculation).
• If the data provided is insufficient to calculate a 20-period moving average, state: 'Insufficient data for volume trend analysis.' for those specific stocks (Note: we have tracked this in our list).

Processed Data:
- Top Stocks to display in Table:
{table_data_str}

- Anomalies (Extreme price move >5% without volume spike):
{anomalies_str}

- Stocks with Insufficient Data for 20-day MA:
{insufficient_str}

Format the entire message in HTML suitable for Telegram. 
Do NOT use unsupported HTML tags like <table>, <tr>, <td>, <h1>, <h2>, etc. 
Use ONLY:
- <b>...</b> for bold
- <i>...</i> for italic
- <pre>...</pre> for the monospaced ASCII table and code snippets
- <code>...</code> for inline code
- Inline links: <a href="url">link text</a>

Keep the report concise, professional, and audit-focused. Start directly with the report.
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional financial data auditor compiling a daily market report for a Telegram channel. You format outputs strictly in Telegram-compatible HTML."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
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
    report = "<b>📊 CANADIAN STOCK MARKET DAILY AUDIT REPORT</b>\n\n"
    report += "<pre>"
    report += f"{'Ticker':<10} | {'% Change':<10} | {'Vol vs Avg':<12} | {'Alert':<8}\n"
    report += "-" * 48 + "\n"
    for s in top_20_stocks[:20]:
        change_str = f"{s['pct_change']:+.2f}%"
        vol_str = f"{s['vol_vs_avg']:+.1f}%"
        report += f"{s['Ticker']:<10} | {change_str:<10} | {vol_str:<12} | {s['alert_status']:<8}\n"
    report += "</pre>\n\n"

    report += "<b>⚠️ ANOMALIES (Price Move &gt;5% without Volume Spike):</b>\n"
    if anomalies:
        for a in anomalies:
            report += f"• {a['Ticker']} ({a['pct_change']:+.2f}%, Vol vs Avg: {a['vol_vs_avg']:+.1f}%)\n"
    else:
        report += "• None\n"
    report += "\n"

    if insufficient_stocks:
        report += f"<b>⚠️ Insufficient data for volume trend analysis for:</b>\n"
        report += f"• {', '.join(insufficient_stocks)}\n\n"

    report += "<b>💡 AUDITOR'S MARKET SPECULATION & ADVICE (Fallback):</b>\n"
    report += "• <i>Note: Groq API was unavailable to generate live commentary.</i>\n"
    report += "• General Advice: Focus on tickers with volume spikes ('Spike') as they indicate high institutional interest. Be cautious with anomalies (high price move on low volume) as they might represent illiquid or manipulated price action.\n"
    
    return report
