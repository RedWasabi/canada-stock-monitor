import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz

ET_TZ = pytz.timezone("America/New_York")

def parse_rss_feed(feed_url):
    """
    Parses an RSS feed and returns a list of dictionaries with title, link, description, pubDate.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(feed_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch RSS feed {feed_url} (HTTP {response.status_code})")
            return []
        
        # Parse XML content
        # Use fromstring to handle raw bytes properly
        root = ET.fromstring(response.content)
        items = []
        for item in root.findall(".//item"):
            title = item.find("title")
            link = item.find("link")
            desc = item.find("description")
            pub_date = item.find("pubDate")
            
            items.append({
                "title": title.text.strip() if title is not None and title.text else "",
                "link": link.text.strip() if link is not None and link.text else "",
                "description": desc.text.strip() if desc is not None and desc.text else "",
                "pub_date": pub_date.text.strip() if pub_date is not None and pub_date.text else ""
            })
        return items
    except Exception as e:
        print(f"Error parsing RSS feed {feed_url}: {e}")
        return []

def fetch_fed_news(hours_back=24):
    """
    Fetches Speeches and Press Releases from the Federal Reserve.
    """
    feeds = {
        "Fed Speeches": "https://www.federalreserve.gov/feeds/speeches.xml",
        "Fed Press Releases": "https://www.federalreserve.gov/feeds/press_all.xml"
    }
    
    news_items = []
    now = datetime.now(pytz.utc)
    
    for category, url in feeds.items():
        items = parse_rss_feed(url)
        for item in items:
            try:
                pub_str = item["pub_date"]
                parts = pub_str.split(" ")
                if len(parts) >= 5:
                    # Expected format: "Fri, 22 May 2026 14:00:00"
                    clean_date_str = " ".join(parts[:5])
                    dt = datetime.strptime(clean_date_str, "%a, %d %b %Y %H:%M:%S")
                    
                    tz_suffix = parts[-1]
                    if tz_suffix in ["EDT", "EST"]:
                        dt = ET_TZ.localize(dt).astimezone(pytz.utc)
                    else:
                        dt = pytz.utc.localize(dt)
                    
                    if now - dt <= timedelta(hours=hours_back):
                        item["category"] = category
                        news_items.append(item)
                else:
                    item["category"] = category
                    news_items.append(item)
            except Exception:
                # If date parsing fails, keep the item as a safety fallback
                item["category"] = category
                news_items.append(item)
                
    return news_items[:10]


def fetch_market_news(api_key):
    """
    Fetches general market news headlines from Finnhub.
    """
    if not api_key:
        return []
    url = "https://finnhub.io/api/v1/news"
    params = {"category": "general", "token": api_key}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()[:8]
        else:
            print(f"Finnhub general news failed: HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching Finnhub general news: {e}")
        return []

def clean_ticker_for_news(ticker):
    """
    Cleans/maps TSX CDR tickers to their main US or international symbols
    for querying news and insider transactions on Finnhub.
    """
    mapping = {
        "BMW.TO": "BMWYY",  # BMW ADR
        "IBM.TO": "IBM",
        "COST.TO": "COST",
        "GIB-A.TO": "GIB"
    }
    return mapping.get(ticker, ticker)


def fetch_ticker_news(ticker, api_key, days_back=1):
    """
    Fetches stock-specific news headlines from Finnhub.
    """
    if not api_key:
        return []
    
    query_ticker = clean_ticker_for_news(ticker)
    now_dt = datetime.now(ET_TZ)
    start_dt = now_dt - timedelta(days=days_back)
    
    url = "https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": query_ticker,
        "from": start_dt.strftime("%Y-%m-%d"),
        "to": now_dt.strftime("%Y-%m-%d"),
        "token": api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()[:3]
        else:
            print(f"Finnhub company news failed for {ticker} (queried as {query_ticker}): HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching Finnhub company news for {ticker} (queried as {query_ticker}): {e}")
        return []

def fetch_insider_transactions(ticker, api_key, days_back=14):
    """
    Fetches recent significant insider transactions (Form 4) for a stock.
    """
    if not api_key:
        return []
    
    query_ticker = clean_ticker_for_news(ticker)
    url = "https://finnhub.io/api/v1/stock/insider-transactions"
    now_dt = datetime.now(ET_TZ)
    start_dt = now_dt - timedelta(days=days_back)
    
    params = {
        "symbol": query_ticker,
        "from": start_dt.strftime("%Y-%m-%d"),
        "to": now_dt.strftime("%Y-%m-%d"),
        "token": api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json().get("data", [])
            significant = []
            for tx in data:
                change = abs(tx.get("change", 0))
                # Only include transactions of 1,000 shares or more
                if change >= 1000:
                    tx["symbol"] = ticker  # Overwrite with original ticker to ensure matches in reports
                    significant.append(tx)
            return significant[:5]
        else:
            print(f"Finnhub insider transactions failed for {ticker} (queried as {query_ticker}): HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching insider transactions for {ticker} (queried as {query_ticker}): {e}")
        return []
