import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import statistics

print("=== MARKET RADAR FINAL (STAGES + STRENGTH + MEMO + CONCLUSION) ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10   # 10 минут
STATE_FILE = "radar_state.json"

# ===== PARAMS =====
COINS_LIMIT = 200
FLAT_RANGE_MAX = 1.5       # % диапазон флета
OVERHEAT_4H = 6.0          # % для перегрева
COOLDOWN_MIN = 90          # анти-спам в минутах

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

# ===== STATE =====
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ===== DATA =====
def get_top_coins():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": COINS_LIMIT,
        "page": 1,
        "sparkline": False
    }
    try:
        return requests.get(url, params=params, timeout=30).json()
    except:
        return []

def get_market_chart(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 2}
        data = requests.get(url, params=params, timeout=20).json()
        prices = [p[1] for p in data.get("prices", [])]
        volumes = [v[1] for v in data.get("total_volumes", [])]
        if len(prices) < 24:
            return None, None
        return pd.Series(prices), pd.Series(volumes)
    except:
        return None, None

def pct_change(series, h):
    if len(series) < h + 1:
        return 0
    return (series.iloc[-1] - series.iloc[-(h+1)]) / series.iloc[-(h+1)] * 100

def dynamic_threshold(series):
    changes = [
        abs((series.iloc[i] - series.iloc[i-1]) / series.iloc[i-1] * 100)
        for i in range(1, len(series))
    ]
    if len(changes) < 10:
        return 1.0
    return max(statistics.mean(changes) * 2, 0.8)

# ===== MEMO =====
def memo_by_strength(strength):
    if strength == 4:
        return (
            "• не входи сразу\
