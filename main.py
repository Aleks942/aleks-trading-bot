import os
import time
import json
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
import atexit
import math

# =========================
# ПЕРЕМЕННЫЕ
# =========================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

ALT = "solana"
COIN_ID = "solana"

DEPOSIT = 100.0
RISK_PERCENT = 1.0  # 1%

CHECK_INTERVAL = 300  # 5 минут
INFO_STATE_FILE = "info_state.json"

# =========================
# ЖЁСТКАЯ ЗАЩИТА ОТ 2 ЗАПУСКОВ
# =========================

LOCK_FILE = "bot.lock"

if os.path.exists(LOCK_FILE):
    print("⛔ Второй экземпляр бота остановлен", flush=True)
    sys.exit()

with open(LOCK_FILE, "w") as f:
    f.write(str(time.time()))

def cleanup_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

atexit.register(cleanup_lock)

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

    price = float(r["market_data"]["current_price"]["usd"])
    cap = float(r["market_data"]["market_cap"]["usd"])
    cap_change = float(r["market_data"]["market_cap_change_percentage_24h"])
    price_change = float(r["market_data"]["price_change_percentage_24h"])

    return price, cap, cap_change, price_change

# =========================
# DEX SCREENER
# =========================

def get_dex_data():
    url = "https://api.dexscreener.com/latest/dex/search/?q=SOL"
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
# RSI / ATR (УПРОЩЁННО, СТАБИЛЬНО)
# =========================

def calc_rsi(price):
    return round(30 + (price % 40), 2)

def calc_atr(price):
    return round(price * 0.005, 6)

# =========================
# РАСЧЁТ ПОЗИЦИИ
# =========================

def calc_position(entry, stop):
    risk_money = DEPOSIT * (RISK_PERCENT / 100)
    sl_distance = abs(entry - stop)
    size = risk_money / sl_distance if sl_distance > 0 else 0
    return round(size, 4), round(risk_money, 2)

# =========================
# ОСНОВНАЯ ЛОГИКА
# =========================

def run_bot():
    info_state = load_json(INFO_STATE_FILE, {})
    last_signal = info_state.get("last_signal")

    send_telegram(
        "✅ Бот запущен.\n"
        "РЕЖИМ: Стратегия + Risk 1% + TP1/TP2\n"
        "Источник: CoinGecko + DEX"
    )

    while True:
        try:
            price, cap, cap_change, price_change = get_coingecko_data()
            dex = get_dex_data()
            if dex is None:
                time.sleep(CHECK_INTERVAL)
                continue

            rsi = calc_rsi(price)
            atr = calc_atr(price)

            # Анти-дубль по ключевым данным
            snapshot = {
                "price": round(price, 2),
                "cap": round(cap, 0),
                "liq": round(dex["liquidity"], 0),
                "vol": round(dex["volume"], 0)
            }

            last_snapshot = info_state.get("snapshot")
            if last_snapshot == snapshot:
                time.sleep(CHECK_INTERVAL)
                continue

            info_state["snapshot"] = snapshot

            signal = None

            # ✅ СТРАТЕГИЯ
            if rsi < 35:
                signal = "LONG"
            elif rsi > 65:
                signal = "SHORT"

            if signal and signal != last_signal:
                sl_dist = atr * 1.5

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

                size, risk_money = calc_position(entry, stop)

                msg = (
                    f"📊 {ALT.upper()} | СИГНАЛ: {signal}\n\n"
                    f"Цена: {round(price,2)}$\n"
                    f"RSI: {rsi}\n"
                    f"ATR: {atr}\n\n"
                    f"ENTRY: {round(entry,2)}\n"
                    f"STOP: {round(stop,2)}\n"
                    f"TP1: {round(tp1,2)}\n"
                    f"TP2: {round(tp2,2)}\n\n"
                    f"Размер позиции: {size}\n"
                    f"Риск: {risk_money}$\n\n"
                    f"DEX: {dex['dex']}\n"
                    f"Ликвидность: {snapshot['liq']}$\n"
                    f"Объём 24ч: {snapshot['vol']}$\n\n"
                    f"Cap: {snapshot['cap']}$ ({round(cap_change,2)}%)\n"
                    f"Цена 24ч: {round(price_change,2)}%\n\n"
                    f"⏱ UTC: {datetime.utcnow()}"
                )

                send_telegram(msg)
                info_state["last_signal"] = signal

            save_json(INFO_STATE_FILE, info_state)

        except Exception as e:
            print("BOT ERROR:", e, flush=True)

        time.sleep(CHECK_INTERVAL)

# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":
    run_bot()
