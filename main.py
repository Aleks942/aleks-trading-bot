import os
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# =========================
# НАСТРОЙКИ
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = {
    "bitcoin": "BITCOIN",
    "ethereum": "ETHEREUM",
    "solana": "SOLANA"
}

TIMEFRAME_MINUTES = 5
CANDLES_LIMIT = 100
CHECK_INTERVAL = 60

LAST_HASH_FILE = "last_hash.txt"

# =========================
# TELEGRAM
# =========================
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass

# =========================
# COINGECKO OHLC
# =========================
def get_ohlc(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": 1
    }
    r = requests.get(url, params=params, timeout=20)
    data = r.json()
    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
    return df.tail(CANDLES_LIMIT)

# =========================
# RSI
# =========================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

# =========================
# ATR
# =========================
def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(period).mean()
    return float(atr.iloc[-1])

# =========================
# АНТИ-ДУБЛИ
# =========================
def load_last_hash():
    if not os.path.exists(LAST_HASH_FILE):
        return None
    with open(LAST_HASH_FILE, "r") as f:
        return f.read().strip()

def save_last_hash(h):
    with open(LAST_HASH_FILE, "w") as f:
        f.write(h)

# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================
def run():
    send_telegram("Bot started. Real OHLC + RSI/ATR 5m active.")

    while True:
        try:
            messages = []
            current_hash = ""

            for coin_id, name in SYMBOLS.items():
                df = get_ohlc(coin_id)

                price = float(df["close"].iloc[-1])
                rsi = calculate_rsi(df["close"])
                atr = calculate_atr(df)

                line = (
                    f"{name}\n"
                    f"Price: {round(price, 2)}$\n"
                    f"RSI (5m): {round(rsi, 2)}\n"
                    f"ATR (5m): {round(atr, 4)}\n"
                    f"Time: {datetime.utcnow()}\n"
                )

                messages.append(line)
                current_hash += str(round(price, 2)) + str(round(rsi, 2))

            last_hash = load_last_hash()

            if current_hash != last_hash:
                for msg in messages:
                    send_telegram(msg)
                save_last_hash(current_hash)

        except Exception as e:
            send_telegram(f"BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

# =========================
# ЗАПУСК
# =========================
if __name__ == "__main__":
    print("BOOT OK: main.py started")
    run()
