import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT STARTED — BACKGROUND STATISTICS ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10  # 10 минут
REPORT_HOUR = 20
REPORT_MINUTE = 30

STATE_FILE = "background_stats.json"

RSI_PERIOD = 14

ALT_TOKENS = [
    "ethereum","binancecoin","solana","avalanche-2","cardano",
    "arbitrum","optimism","polygon",
    "chainlink","fantom",
    "dogecoin","shiba-inu"
]

# ===== TELEGRAM =====
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except:
        pass

# ===== FILE UTILS =====
def load_stats():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_stats(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ===== DATA =====
def get_prices(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        prices = requests.get(url, params=params, timeout=20).json().get("prices", [])
        if len(prices) < 60:
            return None
        return pd.Series([p[1] for p in prices])
    except:
        return None

def calc_rsi(series):
    diff = series.diff()
    gain = diff.where(diff > 0, 0)
    loss = -diff.where(diff < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_los
