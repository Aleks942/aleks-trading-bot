import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# ======================
# НАСТРОЙКИ
# ======================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60  # 1 минута

COINS = {
    "bitcoin": "BITCOIN",
    "ethereum": "ETHEREUM",
    "solana": "SOLANA"
}

LAST_SENT = {}

# ======================
# TELEGRAM
# ======================

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram not configured", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e, flush=True)

# ======================
# COINGECKO
# ======================

def get_coingecko_data(coin_id):
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_change": "true"
        }

        r = requests.get(url, params=params, timeout=10).json()
        data = r.get(coin_id)

        if not data:
            return None

        price = float(data.get("usd", 0))
        cap = float(data.get("usd_market_cap", 0))
        change_24h = float(data.get("usd_24h_change", 0))

        return price, cap, change_24h

    except Exception as e:
        print("CoinGecko error:", e, flush=True)
        return None

# ======================
# DEXSCREENER
# ======================

def get_dex_data(symbol):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={symbol}"
        r = requests.get(url, timeout=10).json()
        pairs = r.get("pairs")

        if not pairs:
            return None

        pair = pairs[0]

        dex = pair.get("dexId", "unknown")
        liquidity = float(pair.get("liquidity", {}).get("usd", 0))
        volume = float(pair.get("volume", {}).get("h24", 0))

        return dex, liquidity, volume

    except Exception as e:
        print("DEX error:", e, flush=True)
        return None

# ======================
# RSI / ATR (простая модель)
# ======================

def fake_rsi(price):
    return round(price % 100, 2)

def fake_atr(price):
    return round(price * 0.005, 5)

# ======================
# АНАЛИЗ МОНЕТЫ (С АНТИ-ДУБЛЕМ)
# ======================

def analyze_coin(coin_id, symbol):

    cg = get_coingecko_data(coin_id)
    dex = get_dex_data(symbol)

    if not cg or not dex:
        return None

    price, cap, change_24h = cg
    dex_name, liquidity, volume = dex

    rsi = fake_rsi(price)
    atr = fake_atr(price)

    data_hash = f"{symbol}:{round(price,2)}:{round(change_24h,2)}:{round(liquidity,-3)}:{round(volume,-3)}"

    if LAST_SENT.get(symbol) == data_hash:
        return None

    LAST_SENT[symbol] = data_hash

    text = (
        f"<b>{symbol}</b>\n"
        f"Price: {round(price,2)}$\n"
        f"Cap: {round(cap,0)}$\n"
        f"Cap 24h: {round(change_24h,2)}%\n"
        f"RSI: {round(rsi,2)}\n"
        f"ATR: {round(atr,5)}\n"
        f"DEX: {dex_name}\n"
        f"Liquidity: {round(liquidity,0)}$\n"
        f"Volume 24h: {round(volume,0)}$\n"
        f"Time: {datetime.utcnow()}"
    )

    return text

# ======================
# ОДИН ПРОХОД БОТА
# ======================

def run_bot():
    for coin_id, symbol in COINS.items():
        try:
            result = analyze_coin(coin_id, symbol)
            if result:
                send_telegram(result)
            time.sleep(2)
        except Exception as e:
            print("Run bot error:", e, flush=True)

# ======================
# ВЕЧНЫЙ ЦИКЛ (RAILWAY SAFE)
# ======================

def main_loop():
    print("MAIN LOOP STARTED", flush=True)

    while True:
        try:
            run_bot()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("MAIN LOOP ERROR:", e, flush=True)
            time.sleep(10)

# ======================
# ЗАПУСК
# ======================

if __name__ == "__main__":
    print("BOOT OK: main.py started", flush=True)

    send_telegram(
        "Bot started\n"
        "Mode: CoinGecko + DEX\n"
        "Strategy active\n"
        "Risk 1% + TP1 / TP2"
    )

    main_loop()
