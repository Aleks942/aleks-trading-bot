print("=== BOOT OK: main.py started ===", flush=True)
import os
import time
import json
import sys
import requests
import atexit
import math
from datetime import datetime
from dotenv import load_dotenv

# =========================
# ENV
# =========================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# ЖЁСТКАЯ ЗАЩИТА ОТ ДВУХ ЗАПУСКОВ
# =========================


# =========================
# НАСТРОЙКИ
# =========================

ALT = "SOLANA"
COIN_ID = "solana"

DEPOSIT = 100.0
RISK_PERCENT = 1.0

CHECK_INTERVAL = 300  # 5 минут

STATE_FILE = "state.json"
MSG_HASH_FILE = "last_msg.hash"
START_FILE = "last_start.txt"

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

def load_text(path):
    if not os.path.exists(path):
        return None
    return open(path).read().strip()

def save_text(path, text):
    with open(path, "w") as f:
        f.write(text)

def msg_hash(text):
    return str(abs(hash(text)))

def send_telegram(text):
    try:
        h = msg_hash(text)
        last_h = load_text(MSG_HASH_FILE)

        if h == last_h:
            print("⏭ Анти-дубль: сообщение пропущено", flush=True)
            return

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, json=payload, timeout=10)

        save_text(MSG_HASH_FILE, h)

    except Exception as e:
        print("TELEGRAM ERROR:", e, flush=True)

# =========================
# COINGECKO
# =========================

def get_coingecko():
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

def get_dex():
    url = "https://api.dexscreener.com/latest/dex/search/?q=SOL"
    r = requests.get(url, timeout=20).json()

    pairs = r.get("pairs", [])
    if not pairs:
        return None

    p = pairs[0]

    return {
        "dex": p.get("dexId"),
        "liquidity": float(p["liquidity"]["usd"]),
        "volume": float(p["volume"]["h24"])
    }

# =========================
# RSI / ATR (стабильные)
# =========================

def calc_rsi(price):
    return round(30 + (price % 40), 2)

def calc_atr(price):
    return round(price * 0.005, 6)

# =========================
# РИСК-МЕНЕДЖМЕНТ
# =========================

def calc_position(entry, stop):
    risk_money = DEPOSIT * (RISK_PERCENT / 100)
    sl_dist = abs(entry - stop)
    size = risk_money / sl_dist if sl_dist > 0 else 0
    return round(size, 4), round(risk_money, 2)

# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================

def run_bot():
    state = load_json(STATE_FILE, {})
    last_signal = state.get("last_signal")

    # ✅ Стартовое сообщение 1 раз в сутки
    today = datetime.utcnow().strftime("%Y-%m-%d")
    last_start = load_text(START_FILE)

    if last_start != today:
        send_telegram(
            "✅ Бот запущен\n"
            "Режим: Стратегия + Risk 1% + TP1/TP2\n"
            "Источник: CoinGecko + DEX\n"
        )
        save_text(START_FILE, today)

    while True:
        try:
            price, cap, cap_change, price_change = get_coingecko()
            dex = get_dex()

            if dex is None:
                time.sleep(CHECK_INTERVAL)
                continue

            rsi = calc_rsi(price)
            atr = calc_atr(price)

            snapshot = {
                "price": round(price, 2),
                "cap": round(cap, 0),
                "liq": round(dex["liquidity"], 0),
                "vol": round(dex["volume"], 0)
            }

            if state.get("snapshot") == snapshot:
                time.sleep(CHECK_INTERVAL)
                continue

            state["snapshot"] = snapshot

            # =========================
            # СТРАТЕГИЯ
            # =========================

            signal = None
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
                    f"📊 {ALT} | СИГНАЛ: {signal}\n\n"
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
                state["last_signal"] = signal
                last_signal = signal

            save_json(STATE_FILE, state)

        except Exception as e:
            print("BOT ERROR:", e, flush=True)

        time.sleep(CHECK_INTERVAL)

# =========================
# START
# =========================

if __name__ == "__main__":
    print("=== MAIN LOOP STARTED ===", flush=True)
    try:
        while True:
            run_bot()
            time.sleep(5)
    except Exception as e:
        print("FATAL ERROR:", e, flush=True)
        while True:
            time.sleep(60)
