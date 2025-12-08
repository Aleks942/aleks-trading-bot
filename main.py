# === ШАГ 8 — УСИЛЕННЫЙ ФИЛЬТР ЛИКВИДНОСТИ И ОБЪЁМА ===

import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 8 — LIQ/VOL FILTER) ===", flush=True)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5
STATE_FILE = "last_signals.json"

# ===== РИСК =====
DEPOSIT_USD = 100.0
RISK_PERCENT = 1.0
RISK_USD = DEPOSIT_USD * (RISK_PERCENT / 100.0)

# ===== УСИЛЕННЫЕ ФИЛЬТРЫ (ПОДТВЕРЖДЁННЫЕ) =====
ALT_MIN_LIQUIDITY = 100_000     # 100k $
ALT_MIN_VOLUME = 250_000        # 250k $

# ===== ПАРАМЕТРЫ =====
RSI_PERIOD = 14
ATR_PERIOD = 14

RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65

EMA_FAST = 50
EMA_SLOW = 200

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync-era"]

# ===== СОСТОЯНИЕ =====
def load_last_states():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_last_states(states):
    with open(STATE_FILE, "w") as f:
        json.dump(states, f)

# ===== TELEGRAM =====
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=15)
    except:
        pass

# ===== COINGECKO =====
def get_ohlc_from_coingecko(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        data = requests.get(url, params=params, timeout=20).json()
        prices = data.get("prices", [])
        if len(prices) < 60:
            return None
        closes = [x[1] for x in prices]
        return pd.DataFrame({"close": closes})
    except:
        return None

def calculate_rsi(df):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.dropna().iloc[-1]), 2)

def calculate_atr(df):
    tr = df["close"].diff().abs()
    return round(float(tr.rolling(ATR_PERIOD).mean().dropna().iloc[-1]), 6)

def calculate_ema(df, period):
    if len(df) < period:
        return None
    return round(float(df["close"].ewm(span=period).mean().iloc[-1]), 6)

# ===== DEX (УСИЛЕННЫЙ ФИЛЬТР) =====
def get_dex_data_alt(query):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        data = requests.get(url, timeout=15).json()
        pairs = data.get("pairs", [])
        if not pairs:

