import os
import time
import math
import requests
import ccxt
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

# === ДИАГНОСТИКА СТАРТА ===
print("=== BOT BOOT STARTED ===", flush=True)

# =========================
# ЗАГРУЗКА НАСТРОЕК
# =========================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"
TREND_TIMEFRAME = "1h"

RISK_PERCENT = 1.0
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5

TP1_MULTIPLIER = 1.0
TP2_MULTIPLIER = 2.0

CHECK_INTERVAL = 60 * 5  # каждые 5 минут

LAST_SIGNAL_FILE = "last_signal.txt"

# === ДИАГНОСТИКА ПЕРЕД СОЗДАНИЕМ EXCHANGE ===
print("=== LOADING EXCHANGE ===", flush=True)

try:
    exchange = ccxt.binance({"enableRateLimit": True})
except Exception as e:
    print("FATAL: BINANCE INIT FAILED:", e, flush=True)
    while True:
        time.sleep(30)


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def send_telegram(message):
    print("=== SENDING TELEGRAM ===", flush=True)
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=payload, timeout=10)
        print("=== TELEGRAM SENT ===", flush=True)
    except Exception as e:
        print("TELEGRAM ERROR:", e, flush=True)


def get_klines(tf, limit=200):
    print(f"=== FETCHING KLINES {tf} ===", flush=True)
    return pd.DataFrame(
        exchange.fetch_ohlcv(SYMBOL, timeframe=tf, limit=limit),
        columns=["time","open","high","low","close","volume"]
    )


def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return (100 - (100 / (1 + rs))).iloc[-1]


def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean().iloc[-1]


def get_trend(df):
    ema_fast = df["close"].ewm(span=20).mean().iloc[-1]
    ema_slow = df["close"].ewm(span=50).mean().iloc[-1]
    if ema_fast > ema_slow:
        return "UP"
    elif ema_fast < ema_slow:
        return "DOWN"
    return "FLAT"


def load_last_signal():
    if not os.path.exists(LAST_SIGNAL_FILE):
        return None
    return open(LAST_SIGNAL_FILE).read().strip()


def save_last_signal(sig):
    with open(LAST_SIGNAL_FILE, "w") as f:
        f.write(sig)


def get_balance():
    print("=== FETCH BALANCE ===", flush=True)
    try:
        b = exchange.fetch_balance()
        return float(b["USDT"]["free"])
    except Exception as e:
        print("BALANCE ERROR:", e, flush=True)
        return 100  # fallback, чтобы не упасть


# =========================
# ОСНОВНАЯ ЛОГИКА
# =========================

def analyze_market():
    print("=== ANALYZING MARKET ===", flush=True)

    df15 = get_klines(TIMEFRAME)
    df1h = get_klines(TREND_TIMEFRAME)

    price = float(df15["close"].iloc[-1])
    rsi = calculate_rsi(df15)
    atr = calculate_atr(df15)
    trend = get_trend(df1h)

    # объём
    volume = df15["volume"].iloc[-1]
    avg = df15["volume"].rolling(20).mean().iloc[-1]
    volume_ratio = volume / avg if avg > 0 else 1

    # базовый сигнал
    signal = "NEUTRAL"

    if trend == "UP" and 50 < rsi < 70:
        signal = "LONG"
    elif trend == "DOWN" and 30 < rsi < 50:
        signal = "SHORT"

    # фильтр RSI
    if rsi > 70 and signal == "LONG":
        signal = "NEUTRAL"
    if rsi < 30 and signal == "SHORT":
        signal = "NEUTRAL"

    print(f"=== SIGNAL: {signal}, PRICE: {price}, RSI: {rsi}, TREND: {trend} ===", flush=True)

    return signal, price, rsi, atr, volume_ratio, trend


def calc_levels(signal, price, atr):
    sl_dist = atr * ATR_MULTIPLIER

    if signal == "LONG":
        entry = price
        stop = price - sl_dist
        tp1 = price + sl_dist
        tp2 = price + sl_dist * 2
    else:
        entry = price
        stop = price + sl_dist
        tp1 = price - sl_dist
        tp2 = price - sl_dist * 2

    return entry, stop, tp1, tp2, sl_dist


def calc_size(sl_dist):
    bal = get_balance()
    risk = bal * (RISK_PERCENT / 100)
    size = risk / sl_dist
    return round(size, 4), round(risk, 2)


def run_bot():
    print("=== BOT LOOP STARTED ===", flush=True)
    while True:
        try:
            signal, price, rsi, atr, volume, trend = analyze_market()
            last = load_last_signal()

            if signal != "NEUTRAL" and signal != last:
                entry, stop, tp1, tp2, sl = calc_le_
