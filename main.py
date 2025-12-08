# === ШАГ 6.1 — TP1 / TP2 (1R / 2R) ===

import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 6.1 — TP1 / TP2) ===", flush=True)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5
STATE_FILE = "last_signals.json"

# ===== РИСК =====
DEPOSIT_USD = 100.0
RISK_PERCENT = 1.0
RISK_USD = DEPOSIT_USD * (RISK_PERCENT / 100.0)

# ===== ФИЛЬТРЫ ДЛЯ АЛЬТОВ =====
ALT_MIN_LIQUIDITY = 10_000
ALT_MIN_VOLUME = 10_000

# ===== ПАРАМЕТРЫ =====
RSI_PERIOD = 14
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.0  # 1R

RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync-era"]

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

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=15)
    except:
        pass

def get_ohlc_from_coingecko(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 1}
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

def get_dex_data_alt(query):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        data = requests.get(url, timeout=15).json()
        pairs = data.get("pairs", [])
        if not pairs:
            return None

        pair = sorted(pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0), reverse=True)[0]
        liq = pair.get("liquidity", {}).get("usd", 0)
        vol = pair.get("volume", {}).get("h24", 0)
        dex = pair.get("dexId")

        if liq < ALT_MIN_LIQUIDITY or vol < ALT_MIN_VOLUME:
            return None

        return liq, vol, dex
    except:
        return None

def run_bot():
    last_states = load_last_states()

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            report = "<b>📈 СИГНАЛЫ (ШАГ 6.1 — TP1 / TP2)</b>\n\n"

            btc_df = get_ohlc_from_coingecko("bitcoin")
            if btc_df is None:
                time.sleep(CHECK_INTERVAL)
                continue

            btc_price = round(float(btc_df["close"].iloc[-1]), 2)
            btc_rsi = calculate_rsi(btc_df)

            report += f"<b>BITCOIN</b> | Цена: {btc_price}$ | RSI: {btc_rsi}\n\n"

            allow_long = btc_rsi <= RSI_SHORT_LEVEL
            allow_short = btc_rsi >= RSI_LONG_LEVEL

            signals_found = False

            for alt in ALT_TOKENS:
                dex_data = get_dex_data_alt(alt)
                df = get_ohlc_from_coingecko(alt)
                if not dex_data or df is None:
                    continue

                rsi = calculate_rsi(df)
                atr = calculate_atr(df)
                price = float(df["close"].iloc[-1])

                signal = "NEUTRAL"
                if rsi < RSI_LONG_LEVEL and allow_long:
                    signal = "LONG"
                elif rsi > RSI_SHORT_LEVEL and allow_short:
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
                    f"СИГНАЛ: <b>{signal}</b>\n"
                    f"Вход: {round(price,6)}\n"
                    f"STOP: {round(stop,6)}\n"
                    f"TP1 (50%): {round(tp1,6)}\n"
                    f"TP2 (50%): {round(tp2,6)}\n"
                    f"Размер: {round(position_size,6)}\n"
                    f"Прибыль TP1: ~{round(profit_tp1,2)}$\n"
                    f"Прибыль TP2: ~{round(profit_tp2,2)}$\n"
                    f"ИТОГО: ~{round(total_profit,2)}$\n"
                    f"DEX: {dex}\n\n"
                )

            if not signals_found:
                report += "Нет новых сигналов (TP1/TP2 активны).\n\n"

            report += f"⏱ UTC: {now}"
            send_telegram(report)

        except Exception as e:
            print("BOT ERROR:", e, flush=True)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    send_telegram("✅ ШАГ 6.1 активирован. TP1 / TP2 (1R / 2R).")
    run_bot()
