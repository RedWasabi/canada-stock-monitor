import os
import sys
import requests

def send_telegram_message(text):
    """
    Sends an HTML-formatted message to the Telegram channel/chat.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured. Skipping Telegram send.")
        print("\n--- REPORT OUTPUT ---")
        try:
            print(text)
        except UnicodeEncodeError:
            try:
                # Fallback for Windows CP1252 consoles
                encoding = sys.stdout.encoding or 'utf-8'
                print(text.encode(encoding, errors='replace').decode(encoding, errors='replace'))
            except Exception:
                # Absolute fallback
                print(text.encode('ascii', errors='replace').decode('ascii'))
        print("---------------------")
        return False

    # Telegram has a max message length of 4096 characters.
    # We chunk the message if it exceeds the limit.
    MAX_LENGTH = 4000
    chunks = [text[i:i+MAX_LENGTH] for i in range(0, len(text), MAX_LENGTH)]

    success = True
    for idx, chunk in enumerate(chunks):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML"
        }
        
        try:
            response = requests.post(url, json=payload)
            result = response.json()
            if response.status_code == 200 and result.get("ok"):
                print(f"Telegram report chunk {idx+1}/{len(chunks)} sent successfully.")
            else:
                print(f"Failed to send Telegram report chunk {idx+1}: {result}")
                success = False
        except Exception as e:
            print(f"Error sending message to Telegram: {e}")
            success = False

    return success
