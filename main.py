import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 2 — DEX + COINGECKO) ===", flush=True)

# =========================
# ЗАГРУЗКА ПЕРЕМЕННЫХ
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print("❌ BOT_TOKEN или CHAT_ID не заданы", flush=True)

CHECK_INTERVAL = 60 * 5  # 5 минут

# Монеты для отслеживания (символы для поиска в DEX Screener)
TOKENS = [
    "bitcoin",
    "ethereum",
    "solana",
    "near",
    "arbitrum",
    "mina-protocol",
    "starknet",
    "zksync"
]

COINGECKO_IDS = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "solana": "solana",
    "near": "near",
    "arbitrum": "arbitrum",
    "mina-protocol": "mina",
    "starknet": "starknet",
    "zksync": "zksync"
}

# =========================
# TELEGRAM
# =========================

def send_telegram(message: str):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            print("=== TELEGRAM SENT OK ===", flush=True)
        else:
            print("❌ TELEGRAM ERROR:", r.text, flush=True)
    except Exception as e:
        print("❌ TELEGRAM EXCEPTION:", e, flush=True)

# =========================
# DEX SCREENER
# =========================

def get_dex_data(query: str):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        r = requests.get(url, timeout=15)
        data = r.json()

        if "pairs" not in data or len(data["pairs"]) == 0:
            return None

        pair = data["pairs"][0]

        price = pair.get("priceUsd")
        liquidity = pair.get("liquidity", {}).get("usd")
        volume_24h = pair.get("volume", {}).get("h24")
        dex = pair.get("dexId")

        return price, liquidity, volume_24h, dex
    except Exception as e:
        print("DEX ERROR:", e, flush=True)
        return None

# =========================
# COINGECKO
# =========================

def get_coingecko_price(coin_id: str):
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd"
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        if coin_id in data:
            return data[coin_id]["usd"]
        return None
    except Exception as e:
        print("COINGECKO ERROR:", e, flush=True)
        return None

# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================

def run_bot():
    print("=== BOT LOOP STARTED (STEP 2 — DATA MODE) ===", flush=True)

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            report = "<b>📡 DEX + CoinGecko (ШАГ 2)</b>\n\n"

            for token in TOKENS:
                dex_data = get_dex_data(token)
                cg_price = get_coingecko_price(COINGECKO_IDS[token])

                if dex_data:
                    price, liquidity, volume, dex = dex_data
                    report += (
                        f"<b>{token.upper()}</b>\n"
                        f"DEX: {dex}\n"
                        f"Цена DEX: {price}$\n"
                        f"Ликвидность: {liquidity}$\n"
                        f"Объём 24ч: {volume}$\n"
                        f"CoinGecko: {cg_price}$\n\n"
                    )
                else:
                    report += f"<b>{token.upper()}</b>: нет данных в DEX\n\n"

            report += f"⏱ UTC: {now}"

            send_telegram(report)

        except Exception as e:
            print("❌ BOT LOOP ERROR:", e, flush=True)

        time.sleep(CHECK_INTERVAL)

# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":
    try:
        print("=== MAIN ENTERED (STEP 2) ===", flush=True)
        send_telegram("✅ Бот перешёл в ШАГ 2. Подключены DEX Screener + CoinGecko.")
        run_bot()
    except Exception as e:
        print("🔥 FATAL START ERROR:", e, flush=True)
        while True:
            time.sleep(30)

