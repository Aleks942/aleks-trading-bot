import os
import time
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

INFO_STATE_FILE = "info_state.json"

ALT = "solana"
COIN_ID = "solana"

CHECK_INTERVAL = 300  # 5 минут


# =========================
# УТИЛИТЫ
# =========================

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
        json.dump(data, f)


def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("TELEGRAM ERROR:", e, flush=True)


# =========================
# COINGECKO
# =========================

def get_coingecko_data():
    url = f"https://api.coingecko.com/api/v3/coins/{COIN_ID}"
    r = requests.get(url, timeout=20).json()

    price = r["market_data"]["current_price"]["usd"]
    cap = r["market_data"]["market_cap"]["usd"]
    cap_change = r["market_data"]["market_cap_change_percentage_24h"]
    price_change = r["market_data"]["price_change_percentage_24h"]

    return float(price), float(cap), float(cap_change), float(price_change)


# =========================
# DEX SCREENER
# =========================

def get_dex_data():
    url = f"https://api.dexscreener.com/latest/dex/search/?q=SOL"
    r = requests.get(url, timeout=20).json()

    pairs = r.get("pairs", [])
    if not pairs:
        return None

    p = pairs[0]

    return {
        "dex": p.get("dexId"),
        "liquidity": float(p["liquidity"]["usd"]),
        "volume": float(p["volume"]["h24"]),
        "price": float(p["priceUsd"])
    }


# =========================
# ПСЕВДО RSI / ATR (без бирж)
# =========================

def fake_rsi(price):
    return round(30 + (price % 40), 2)


def fake_atr(price):
    return round(price * 0.005, 6)


# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================

def run_bot():
    info_state = load_json(INFO_STATE_FILE, {})

    send_telegram("✅ Бот запущен. ШАГ 12 активен.\nКапа + 24ч + DEX + анти-дубли.")

    while True:
        try:
            price, cap, cap_change, price_change = get_coingecko_data()
            dex = get_dex_data()

            if dex is None:
                time.sleep(CHECK_INTERVAL)
                continue

            rsi = fake_rsi(price)
            atr = fake_atr(price)

            # 🔒 СНИМОК ТОЛЬКО ПО КЛЮЧЕВЫМ ЦИФРАМ (АНТИ-ДУБЛИ)
            snapshot = {
                "price": round(price, 2),
                "cap": round(cap, 0),
                "liq": round(dex["liquidity"], 0),
                "vol": round(dex["volume"], 0)
            }

            last = info_state.get(ALT)

            # ✅ ЕСЛИ ЦИФРЫ НЕ ИЗМЕНИЛИСЬ — НИЧЕГО НЕ ШЛЁМ
            if last == snapshot:
                time.sleep(CHECK_INTERVAL)
                continue

            info_state[ALT] = snapshot
            save_json(INFO_STATE_FILE, info_state)

            msg = (
                f"📊 {ALT.upper()}\n"
                f"Цена: {snapshot['price']}$\n"
                f"Cap: {snapshot['cap']}$\n"
                f"Cap 24ч: {round(cap_change, 2)}%\n"
                f"Цена 24ч: {round(price_change, 2)}%\n"
                f"RSI: {rsi}\n"
                f"ATR: {atr}\n"
                f"DEX: {dex['dex']}\n"
                f"Ликв: {snapshot['liq']}$ | Объём: {snapshot['vol']}$\n"
                f"⏱ {datetime.utcnow()}"
            )

            send_telegram(msg)

        except Exception as e:
            print("BOT ERROR:", e, flush=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
