import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT BOOT STARTED (STEP 12 — MARKET CAP + LIQUIDATIONS) ===", flush=True)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5

STATE_FILE = "last_states.json"
POSITIONS_FILE = "open_positions.json"
TRADES_LOG_FILE = "trades_log.json"
DAILY_REPORT_FILE = "daily_report_state.json"

# ===== ВРЕМЯ ОТЧЁТА =====
REPORT_HOUR = 20
REPORT_MINUTE = 30  # 20:30 Польша (UTC+2)

# ===== РИСК =====
START_DEPOSIT = 100.0
RISK_PERCENT = 1.0
RISK_USD = START_DEPOSIT * (RISK_PERCENT / 100.0)

# ===== ФИЛЬТРЫ =====
ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

# ===== ИНДИКАТОРЫ =====
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65
EMA_FAST = 50
EMA_SLOW = 200

# ===== ТРЕЙЛИНГ =====
TRAIL_MULT = 1.5

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync"]

# ===== УТИЛИТЫ =====
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ===== TELEGRAM =====
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=15)
    except:
        pass

# ===== COINGECKO =====
def get_market_data(coin_id):
    try:
        url = f"https://api.coingecko.com/ap
