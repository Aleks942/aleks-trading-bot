import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 3 — DATA CLEANING) ===", flush=True)

# =========================
# ПЕРЕМЕННЫЕ
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5  # 5 минут
MIN_LIQUIDITY_USD = 50000     # фильтр по ликвидности
MIN_VOLUME_24H_USD = 50000   # фильтр по объёму

# =========================
# СПИСОК ТОКЕНОВ (ВЫРОВНЕН)
# =========================
TOKENS = [
    "bitcoin",
    "ethereum",
    "solana",
    "near",
    "arbitrum",
    "mina",
    "starknet",
    "zksync-era"
]

COINGECKO_IDS = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "solana": "solana",
    "near": "near",                # Near Protocol
    "arbitrum": "arbitrum",        # Эталон для ARB
    "mina": "mina",
    "starknet": "starknet",
    "zksync-era": "zksync-era"     # ВАЖНО: правильный ID
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
# DEX SCREENER (ТОЛЬКО ЛИКВИДНОСТЬ + ОБЪЁМ)
# =========================
def get_dex_data(query: str):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        r = requests.get(url, timeout=15)
        data = r.json()

        if "pairs" not in data or len(data["pairs"]) == 0:
            return None

        # Берём САМУЮ ЛИКВИДНУЮ пару
        pairs_sorted = sorted(
            data["pairs"],
            key=lambda x: x.get("liquidity", {}).get("usd", 0),
            reverse=True
        )
        pair = pairs_sorted[0]

        liquidity = pair.get("liquidity", {}).get("usd", 0)
        volume_24h = pair.get("volume", {}).get("h24", 0)
        dex = pair.get("dexId")

        # ФИЛЬТР МУСОРА
        if liquidity < MIN_LIQUIDITY_USD or volume_24h < MIN_VOLUME_24H_USD:
            return None

        return liquidity, volume_24h, dex

    except Exception as e:
        print("DEX ERROR:", e, flush=True)
        return None

# =========================
# COINGECKO (ЭТАЛОН ЦЕНЫ)
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
            return float(data[coin_id]["usd"])
        return None

    except Exception as e:
        print("COINGECKO ERROR:", e, flush=True)
        return None

# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================
def run_bot():
    print("=== BOT LOOP STARTED (STEP 3 — CLEAN DATA MODE) ===", flush=True)

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            report = "<b>🧹 ЧИСТЫЕ ДАННЫЕ (ШАГ 3)</b>\n"
            report += "Цена = CoinGecko | Ликвидность/Объём = DEX\n\n"

            for token in TOKENS:
                cg_price = get_coingecko_price(COINGECKO_IDS[token])
                dex_data = get_dex_data(token)

                if not cg_price or not dex_data:
                    report += f"<b>{token.upper()}</b>: недостаточно данных\n\n"
                    continue

                liquidity, volume, dex = dex_data

                report += (
                    f"<b>{token.upper()}</b>\n"
                    f"Цена (CG): {cg_price}$\n"
                    f"DEX: {dex}\n"
                    f"Ликвидность: {round(liquidity, 2)}$\n"
                    f"Объём 24ч: {round(volume, 2)}$\n\n"
                )

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
        print("=== MAIN ENTERED (STEP 3) ===", flush=True)
        send_telegram("✅ Бот перешёл в ШАГ 3. Включена очистка и выравнивание данных.")
        run_bot()
    except Exception as e:
        print("🔥 FATAL START ERROR:", e, flush=True)
        while True:
            time.sleep(30)
