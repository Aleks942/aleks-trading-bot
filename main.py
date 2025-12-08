# === ШАГ 8 — УСИЛЕННЫЙ ФИЛЬТР ЛИКВИДНОСТИ И ОБЪЁМА ===

import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 8 — LIQ/VOL FILTER) ===", flush=True)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5
STATE_FILE = "last_signals.json"

# ===== РИСК =====
DEPOSIT_USD = 100.0
RISK_PERCENT = 1.0
RISK_USD = DEPOSIT_USD * (RISK_PERCENT / 100.0)

# ===== УСИЛЕННЫЕ ФИЛЬТРЫ (ПОДТВЕРЖДЁННЫЕ) =====
ALT_MIN_LIQUIDITY = 100_000     # 100k $
ALT_MIN_VOLUME = 250_000        # 250k $

# ===== ПАРАМЕТРЫ =====
RSI_PERIOD = 14
ATR_PERIOD = 14

RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65

EMA_FAST = 50
EMA_SLOW = 200

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync-era"]

# ===== СОСТОЯНИЕ =====
def load_last_states():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_last_states(states):
    with open(STATE_FILE, "w") as f:
        json.dump(states, f)

# ===== TELEGRAM =====
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=15)
    except:
        pass

# ===== COINGECKO =====
def get_ohlc_from_coingecko(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        data = requests.get(url, params=params, timeout=20).json()
        prices = data.get("prices", [])
        if len(prices) < 60:
            return None
        closes = [x[1] for x in prices]
        return pd.DataFrame({"close": closes})
    except:
        return None

def calculate_rsi(df):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.dropna().iloc[-1]), 2)

def calculate_atr(df):
    tr = df["close"].diff().abs()
    return round(float(tr.rolling(ATR_PERIOD).mean().dropna().iloc[-1]), 6)

def calculate_ema(df, period):
    if len(df) < period:
        return None
    return round(float(df["close"].ewm(span=period).mean().iloc[-1]), 6)

# ===== DEX (УСИЛЕННЫЙ ФИЛЬТР) =====
def get_dex_data_alt(query):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        data = requests.get(url, timeout=15).json()
        pairs = data.get("pairs", [])
        if not pairs:
            return None

        pair = sorted(
            pairs,
            key=lambda x: x.get("liquidity", {}).get("usd", 0),
            reverse=True
        )[0]

        liq = pair.get("liquidity", {}).get("usd", 0)
        vol = pair.get("volume", {}).get("h24", 0)
        dex = pair.get("dexId")

        # === УСИЛЕННЫЕ ПОРОГИ ===
        if liq < ALT_MIN_LIQUIDITY or vol < ALT_MIN_VOLUME:
            return None

        return liq, vol, dex
    except:
        return None

# ===== ОСНОВНОЙ ЦИКЛ =====
def run_bot():
    last_states = load_last_states()

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            report = "<b>📈 СИГНАЛЫ (ШАГ 8 — УСИЛЕННЫЙ ФИЛЬТР ЛИКВ/ОБЪЁМ)</b>\n\n"

            signals_found = False

            for alt in ALT_TOKENS:
                dex_data = get_dex_data_alt(alt)
                df = get_ohlc_from_coingecko(alt)

                if not dex_data or df is None:
                    continue

                rsi = calculate_rsi(df)
                atr = calculate_atr(df)
                price = float(df["close"].iloc[-1])

                ema50 = calculate_ema(df, EMA_FAST)
                ema200 = calculate_ema(df, EMA_SLOW)

                trend = "FLAT"
                if ema50 and ema200:
                    trend = "UP" if ema50 > ema200 else "DOWN"
                elif ema50:
                    trend = "UP" if price > ema50 else "DOWN"

                signal = "NEUTRAL"
                if rsi < RSI_LONG_LEVEL and trend == "UP":
                    signal = "LONG"
                elif rsi > RSI_SHORT_LEVEL and trend == "DOWN":
                    signal = "SHORT"

                if last_states.get(alt) == signal:
                    continue

                last_states[alt] = signal
                save_last_states(last_states)

                if signal == "NEUTRAL":
                    continue

                liq, vol, dex = dex_data

                stop = price - atr if signal == "LONG" else price + atr
                tp1 = price + atr if signal == "LONG" else price - atr
                tp2 = price + atr * 2 if signal == "LONG" else price - atr * 2

                stop_dist = abs(price - stop)
                position_size = RISK_USD / stop_dist
                part = position_size / 2

                profit_tp1 = abs(tp1 - price) * part
                profit_tp2 = abs(tp2 - price) * part
                total_profit = profit_tp1 + profit_tp2

                signals_found = True

                report += (
                    f"<b>{alt.upper()}</b>\n"
                    f"ТРЕНД: {trend}\n"
                    f"RSI: {rsi}\n"
                    f"EMA50: {ema50}\n"
                    f"EMA200: {ema200}\n"
                    f"СИГНАЛ: <b>{signal}</b>\n"
                    f"Вход: {round(price,6)}\n"
                    f"STOP: {round(stop,6)}\n"
                    f"TP1: {round(tp1,6)}\n"
                    f"TP2: {round(tp2,6)}\n"
                    f"Размер позиции: {round(position_size,6)}\n"
                    f"ИТОГО прибыль: ~{round(total_profit,2)}$\n"
                    f"Ликвидность: {round(liq,2)}$\n"
                    f"Объём 24ч: {round(vol,2)}$\n"
                    f"DEX: {dex}\n\n"
                )

            if not signals_found:
                report += "Нет новых сигналов (усиленный фильтр ликвидности/объёма).\n\n"

            report += f"⏱ UTC: {now}"
            send_telegram(report)

        except Exception as e:
            send_telegram(f"❌ BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    send_telegram("✅ ШАГ 8 активирован. Ликвидность ≥ 100k$, Объём ≥ 250k$.")
    run_bot()
