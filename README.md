# 🇺🇸 US Stock Market Telegram Monitor Bot

A serverless, automated Telegram bot that monitors US stock exchanges (NYSE, NASDAQ, AMEX), filters for liquidity, runs deep quantitative technical analysis (RSI, Bollinger Bands, Volume Ratio, Daily Volatility), generates professional Wall Street-style financial analysis via the **Groq API** (Llama 3.3), and sends reports hourly.

The bot is designed to run entirely within **GitHub Actions** triggered by a cron job website (like `cron-job.org`) every 15 minutes, storing its state in a private **GitHub Gist** to avoid git clutter.

---

## 🛠️ Architecture Overview

1. **Trigger**: `cron-job.org` sends an HTTP POST request to GitHub's `repository_dispatch` endpoint every 15 minutes.
2. **Compute**: GitHub Actions launches a runner to run `src/main.py`.
3. **Data Retrieval**: High-precision intraday and historical data are fetched via `yfinance` for US tickers.
4. **State Storage**: The script reads/writes the 15-minute state (price/volume snapshots) from/to a secret **GitHub Gist** via the GitHub API.
5. **Core Filtering & Technical Analysis Logic**:
   - **Liquidity Filter**: Confirms average 20-day volume is $\ge 1,500,000$ (with source-level pre-filtering of stocks from TradingView).
   - **Volume Ratio**: Current volume compared to the 20-period volume moving average.
   - **14-day Wilder's RSI**: Calculates overbought ($\ge 70$) and oversold ($\le 30$) conditions.
   - **Bollinger Bands**: Detects price breakouts (Upper BB) and breakdowns (Lower BB) with volume validation.
   - **Daily Volatility**: Identifies statistically significant price moves ($> 2$ standard deviations).
   - **Anomalies**: Spots stocks with extreme price moves ($> 5\%$ change) without a volume spike.
6. **AI Commentary**: Every 1 hour (4 triggers), the bot feeds the quantitative metrics to the **Groq API** (`llama-3.3-70b-versatile`) representing a Wall Street quantitative analyst, producing short-term tactical advice and breakout explanations.
7. **Telegram Broadcast**: The report is formatted in a clean, monospaced ASCII HTML table and sent to your Telegram channel/chat.

---

## 🚀 Setup & Configuration

Follow these steps to deploy and activate the bot:

### Step 1: Create a GitHub Gist for State
1. Go to [gist.github.com](https://gist.github.com).
2. Create a new **Secret Gist** named `state.json`.
3. Set the content to:
   ```json
   {
     "last_report_time": 0,
     "snapshots": {}
   }
   ```
4. Save the Gist and copy the **Gist ID** from the URL (the trailing hash in the address bar, e.g. `https://gist.github.com/username/GIST_ID_HERE`).

### Step 2: Generate a GitHub Personal Access Token (PAT)
1. Go to **Settings** $\to$ **Developer Settings** $\to$ **Personal Access Tokens (classic)**.
2. Click **Generate new token (classic)**.
3. Select the **`gist`** scope and (optionally) **`repo`** scope (required to call repository dispatch).
4. Generate and save the token (referred to as `GH_PAT`).

### Step 3: Configure GitHub Secrets
In your GitHub repository, go to **Settings** $\to$ **Secrets and variables** $\to$ **Actions** and add the following repository secrets:

| Secret Name | Description | Source |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Token for your bot | Get from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Telegram chat/channel ID | E.g. `@your_channel` or ID (e.g. `-100...`) |
| `GROQ_API_KEY` | Groq API Key | Get from [Groq Console](https://console.groq.com) |
| `GIST_ID` | The ID of your secret Gist | Step 1 |
| `GH_PAT` | GitHub Personal Access Token | Step 2 |

### Step 4: Configure the Cron Trigger on `cron-job.org`
1. Create a free account at [cron-job.org](https://cron-job.org).
2. Create a new Cron Job with the following details:
   - **Title**: `US Stock Bot Trigger`
   - **Address (URL)**: `https://api.github.com/repos/{YOUR_GITHUB_USERNAME}/{YOUR_REPOSITORY_NAME}/dispatches`
   - **Schedule**: Every 15 minutes (`*/15 * * * *`).
   - **Request Method**: `POST`
   - **Headers**: Add the following headers:
     - `Accept`: `application/vnd.github+json`
     - `Authorization`: `Bearer YOUR_GH_PAT` (Replace with your actual GitHub PAT)
     - `User-Agent`: `CronJobOrg`
   - **Request Body**: Select `Raw / JSON` and enter:
     ```json
     {
       "event_type": "cron_trigger"
     }
     ```
3. Save the job. It will now automatically trigger your bot every 15 minutes!

---

## 💻 Local Development & Testing

If you want to run or test the bot locally on your machine:

1. Clone your repository.
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   GROQ_API_KEY=your_groq_api_key
   GIST_ID=your_gist_id
   GH_PAT=your_github_pat
   ```
4. Run the orchestrator script:
   - **Standard test mode** (downloads only 5 tickers, updates local cache, doesn't force Telegram report unless 1 hour elapsed):
     ```bash
     python src/main.py --test-run
     ```
   - **Force immediate Telegram report** (pulls all tickers, generates Groq audit, and fires directly to Telegram):
     ```bash
     python src/main.py --force-report
     ```
   - **Test + Force combined**:
     ```bash
     python src/main.py --test-run --force-report
     ```

### Updating Ticker List
The bot has a seeded file `data/tickers.json` with liquid US stocks. To dynamically expand or refresh this list from the TradingView America Scanner API or Wikipedia S&P 500 fallback, run:
```bash
python src/fetch_tickers.py
```
This will rebuild `data/tickers.json` with the top 1,000 liquid US tickers.

