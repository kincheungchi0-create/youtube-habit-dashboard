import os
import requests
import html
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send(msg, mode="HTML"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": mode}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

print("--- Test 1: Simple Text ---")
send("Hello from debug script", mode=None)

print("\n--- Test 2: Valid HTML ---")
send("<b>Bold</b> and <i>Italic</i>", mode="HTML")

print("\n--- Test 3: Invalid HTML (Unclosed tag) ---")
send("<b>Unclosed Bold", mode="HTML")

print("\n--- Test 4: Check Chat ID ---")
print(f"Chat ID: {CHAT_ID}")
print(f"Token: {TOKEN[:10]}...") 
