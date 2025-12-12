import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT STARTED — LIQUIDATIONS + RSI CONTEXT ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10  # 10 минут
LIQ_RATIO = 1.5

STATE_FILE = "liq_rsi_state.json"

# ===== TELEGRAM =====
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except Exception as e:
        print("Telegram error:", e, flush=True)

# ===== LIQUIDATIONS =====
def get_liquidations(symbol="BTC"):
    try:
        url = f"https://fapi.coinglass.com/api/futures/liquidation_snapshot?symbol={symbol}"
        data = requests.get(url, timeout=20).json()["data"]
        return float(data["longVolUsd"]), float(data["shortVolUsd"])
    except:
        return None, None

# ===== RSI BTC =====
def get_btc_rsi():
    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        prices = requests.get(url, params=params, timeout=20).json().get("prices", [])
        if len(prices) < 60:
            return None, None

        df = pd.DataFrame({"close": [p[1] for p in prices]})
        diff = df["close"].diff()
        gain = diff.where(diff > 0, 0)
        loss = -diff.where(diff < 0, 0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-2]), float(rsi.iloc[-1])
    except:
        return None, None

# ===== STATE =====
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ===== MAIN LOGIC =====
def run_bot():
    state = load_state()
    send_telegram("✅ Контекст ликвидаций + RSI активирован.")

    while True:
        long_liq, short_liq = get_liquidations("BTC")
        rsi_prev, rsi_now = get_btc_rsi()

        if None in (long_liq, short_liq, rsi_prev, rsi_now):
            time.sleep(CHECK_INTERVAL)
            continue

        context = None
        reason = ""
        action = ""

        if long_liq > short_liq * LIQ_RATIO:
            context = "LONG"
            reason = "Вынесли слабые лонги"
            if rsi_prev < 40 and rsi_now > rsi_prev:
                action = "ЖДАТЬ ПОДТВЕРЖДЕНИЕ И ИСКАТЬ LONG"
            else:
                action = "ЖДАТЬ"

        elif short_liq > long_liq * LIQ_RATIO:
            context = "SHORT"
            reason = "Вынесли слабые шорты"
            if rsi_prev > 60 and rsi_now < rsi_prev:
                action = "ЖДАТЬ СИГНАЛ НА SHORT"
            else:
                action = "ЖДАТЬ"

        else:
            context = "FLAT"
            reason = "Баланс ликвидаций"
            action = "НЕ ЛЕЗТЬ В РЫНОК"

        key = f"{int(long_liq)}_{int(short_liq)}_{round(rsi_now,1)}"
        if state.get("last") == key:
            time.sleep(CHECK_INTERVAL)
            continue

        emoji = "🟢" if context == "LONG" else "🔴" if context == "SHORT" else "⚪"

        send_telegram(
            f"💥 <b>ЛИКВИДАЦИИ BTC (24ч)</b>\n\n"
            f"LONG: {round(long_liq/1e6,1)}M$\n"
            f"SHORT: {round(short_liq/1e6,1)}M$\n\n"
            f"{emoji} <b>КОНТЕКСТ ДЛЯ {context}</b>\n"
            f"Причина: {reason}\n"
            f"RSI BTC: {round(rsi_prev,1)} → {round(rsi_now,1)}\n"
            f"➡️ {action}"
        )

        state["last"] = key
        save_state(state)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()

