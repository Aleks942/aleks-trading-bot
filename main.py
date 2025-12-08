import os
import time
import math
import requests
import ccxt
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd

# =========================
# ЗАГРУЗКА НАСТРОЕК
# =========================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"
TREND_TIMEFRAME = "1h"

RISK_PERCENT = 1.0        # риск 1% от депозита
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5

TP1_MULTIPLIER = 1.0
TP2_MULTIPLIER = 2.0

CHECK_INTERVAL = 60 * 5  # проверка каждые 5 минут

LAST_SIGNAL_FILE = "last_signal.txt"

exchange = ccxt.binance({
    "enableRateLimit": True
})

# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Ошибка Telegram:", e)

def get_klines(tf, limit=200):
    ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=tf, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
    return df

def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(period).mean()
    return atr.iloc[-1]

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
    with open(LAST_SIGNAL_FILE, "r") as f:
        return f.read().strip()

def save_last_signal(signal):
    with open(LAST_SIGNAL_FILE, "w") as f:
        f.write(signal)

def get_balance():
    balance = exchange.fetch_balance()
    return float(balance["USDT"]["free"])

# =========================
# ОСНОВНАЯ ЛОГИКА
# =========================

def analyze_market():
    df_15m = get_klines(TIMEFRAME)
    df_1h = get_klines(TREND_TIMEFRAME)

    price = float(df_15m["close"].iloc[-1])
    volume = float(df_15m["volume"].iloc[-1])
    avg_volume = float(df_15m["volume"].rolling(20).mean().iloc[-1])
    volume_ratio = volume / avg_volume if avg_volume > 0 else 0

    rsi = calculate_rsi(df_15m, 14)
    atr = calculate_atr(df_15m, ATR_PERIOD)
    trend = get_trend(df_1h)

    signal = "NEUTRAL"

    if trend == "UP" and rsi < 70 and rsi > 50:
        signal = "LONG"
    elif trend == "DOWN" and rsi > 30 and rsi < 50:
        signal = "SHORT"

    if rsi > 70 and signal == "LONG":
        signal = "NEUTRAL"
    if rsi < 30 and signal == "SHORT":
        signal = "NEUTRAL"

    return signal, price, rsi, atr, volume_ratio, trend

def calculate_trade_levels(signal, price, atr):
    sl_distance = atr * ATR_MULTIPLIER

    if signal == "LONG":
        entry = price
        stop = entry - sl_distance
        tp1 = entry + sl_distance * TP1_MULTIPLIER
        tp2 = entry + sl_distance * TP2_MULTIPLIER
    else:
        entry = price
        stop = entry + sl_distance
        tp1 = entry - sl_distance * TP1_MULTIPLIER
        tp2 = entry - sl_distance * TP2_MULTIPLIER

    return entry, stop, tp1, tp2, sl_distance

def calculate_position_size(sl_distance):
    balance = get_balance()
    risk_amount = balance * (RISK_PERCENT / 100)
    size = risk_amount / sl_distance
    return round(size, 4), round(risk_amount, 2)

def run_bot():
    while True:
        try:
            signal, price, rsi, atr, volume_ratio, trend = analyze_market()

            last_signal = load_last_signal()

            if signal != "NEUTRAL" and signal != last_signal:
                entry, stop, tp1, tp2, sl_distance = calculate_trade_levels(signal, price, atr)
                size, risk_amount = calculate_position_size(sl_distance)

                message = f"""
<b>СИГНАЛ: {signal}</b>

Монета: BTC
Таймфрейм: 15m
Тренд 1h: {trend}

Цена: {price}
RSI: {round(rsi,2)}
ATR: {round(atr,2)}
Объём: {round(volume_ratio,2)}x

<b>ENTRY:</b> {round(entry,2)}
<b>STOP:</b> {round(stop,2)}
<b>TP1:</b> {round(tp1,2)} (50%)
<b>TP2:</b> {round(tp2,2)} (50%)

Риск: {RISK_PERCENT}% ≈ {risk_amount}$  
Объём позиции: {size} BTC

Время: {datetime.now().strftime('%H:%M:%S')}
                """

                send_telegram(message)
                save_last_signal(signal)

        except Exception as e:
            print("Ошибка:", e)

        time.sleep(CHECK_INTERVAL)

# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":
    send_telegram("✅ Бот успешно запущен и начал мониторинг рынка.")
    run_bot()
