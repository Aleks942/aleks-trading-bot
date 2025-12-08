import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 4.3 — RSI 35/65) ===", flush=True)

# =========================
# ПЕРЕМЕННЫЕ
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5  # 5 минут
STATE_FILE = "last_signals.json"

# ФИЛЬТРЫ ДЛЯ АЛЬТОВ (DEX)
ALT_MIN_LIQUIDITY = 10_000
ALT_MIN_VOLUME = 10_000

# ПАРАМЕТРЫ СТРАТЕГИИ
RSI_PERIOD = 14
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5

# ✅ НОВЫЕ ПОРОГИ (35 / 65)
RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65

# =========================
# СПИСОК ТОКЕНОВ
# =========================
BIG_TOKENS = ["bitcoin", "ethereum"]

ALT_TOKENS = [
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
    "near": "near",
    "arbitrum": "arbitrum",
    "mina": "mina",
    "starknet": "starknet",
    "zksync-era": "zksync-era"
}

# =========================
# СОСТОЯНИЕ СИГНАЛОВ (АНТИ-ДУБЛИКАТ)
# =========================
def load_last_states():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_last_states(states):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(states, f)
    except Exception as e:
        print("STATE SAVE ERROR:", e, flush=True)

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
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print("❌ TELEGRAM ERROR:", e, flush=True)

# =========================
# COINGECKO — СВЕЧИ
# =========================
def get_ohlc_from_coingecko(coin_id: str):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 1}
        r = requests.get(url, params=params, timeout=20)
        data = r.json()

        prices = data.get("prices", [])
        if len(prices) < 60:
            return None

        closes = [p[1] for p in prices]
        df = pd.DataFrame({"close": closes})
        return df

    except Exception as e:
        print("COINGECKO OHLC ERROR:", e, flush=True)
        return None

# =========================
# RSI и ATR
# =========================
def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)

def calculate_atr(df, period=14):
    high_low = df["close"].diff().abs()
    atr = high_low.rolling(period).mean().iloc[-1]
    return round(float(atr), 6)

# =========================
# DEX — ОБЪЁМ И ЛИКВИДНОСТЬ
# =========================
def get_dex_data_alt(query: str):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        r = requests.get(url, timeout=15)
        data = r.json()

        if "pairs" not in data or len(data["pairs"]) == 0:
            return None

        pairs_sorted = sorted(
            data["pairs"],
            key=lambda x: x.get("liquidity", {}).get("usd", 0),
            reverse=True
        )

        pair = pairs_sorted[0]
        liquidity = pair.get("liquidity", {}).get("usd", 0)
        volume_24h = pair.get("volume", {}).get("h24", 0)
        dex = pair.get("dexId")

        if liquidity < ALT_MIN_LIQUIDITY or volume_24h < ALT_MIN_VOLUME:
            return None

        return liquidity, volume_24h, dex

    except Exception as e:
        print("DEX ERROR:", e, flush=True)
        return None

# =========================
# ЛОГИКА СИГНАЛА (35 / 65)
# =========================
def make_signal(token: str):
    df = get_ohlc_from_coingecko(COINGECKO_IDS[token])
    if df is None:
        return None

    rsi = calculate_rsi(df, RSI_PERIOD)
    atr = calculate_atr(df, ATR_PERIOD)
    price = float(df["close"].iloc[-1])

    signal = "NEUTRAL"
    if rsi < RSI_LONG_LEVEL:
        signal = "LONG"
    elif rsi > RSI_SHORT_LEVEL:
        signal = "SHORT"

    if signal == "NEUTRAL":
        return {"signal": "NEUTRAL"}

    if signal == "LONG":
        stop = price - atr * ATR_MULTIPLIER
        target = price + atr * ATR_MULTIPLIER
    else:
        stop = price + atr * ATR_MULTIPLIER
        target = price - atr * ATR_MULTIPLIER

    return {
        "signal": signal,
        "price": round(price, 6),
        "rsi": rsi,
        "atr": atr,
        "stop": round(stop, 6),
        "target": round(target, 6)
    }

# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================
def run_bot():
    print("=== BOT LOOP STARTED (STEP 4.3 — RSI 35/65) ===", flush=True)

    last_states = load_last_states()

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            report = "<b>📈 СИГНАЛЫ (ШАГ 4.3 — RSI 35/65)</b>\n\n"

            # ФОН РЫНКА
            for big in BIG_TOKENS:
                df_bg = get_ohlc_from_coingecko(COINGECKO_IDS[big])
                if df_bg is not None:
                    rsi_bg = calculate_rsi(df_bg)
                    price_bg = round(float(df_bg["close"].iloc[-1]), 2)
                    report += f"<b>{big.upper()}</b> | Цена: {price_bg}$ | RSI: {rsi_bg}\n\n"

            signals_found = False

            # АЛЬТЫ
            for alt in ALT_TOKENS:
                dex_data = get_dex_data_alt(alt)
                sig = make_signal(alt)

                if not dex_data or not sig:
                    continue

                current_signal = sig["signal"]
                prev_signal = last_states.get(alt)

                # ✅ АНТИ-ДУБЛИКАТ
                if current_signal == prev_signal:
                    continue

                last_states[alt] = current_signal
                save_last_states(last_states)

                if current_signal == "NEUTRAL":
                    continue

                signals_found = True
                liquidity, volume, dex = dex_data

                report += (
                    f"<b>{alt.upper()}</b>\n"
                    f"СИГНАЛ: <b>{sig['signal']}</b>\n"
                    f"Цена: {sig['price']}$\n"
                    f"RSI: {sig['rsi']}\n"
                    f"ATR: {sig['atr']}\n"
                    f"STOP: {sig['stop']}\n"
                    f"TARGET: {sig['target']}\n"
                    f"DEX: {dex}\n"
                    f"Ликвидность: {round(liquidity,2)}$\n"
                    f"Объём 24ч: {round(volume,2)}$\n\n"
                )

            if not signals_found:
                report += "Нет новых сигналов (анти-дубликаты + 35/65).\n\n"

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
        print("=== MAIN ENTERED (STEP 4.3) ===", flush=True)
        send_telegram("✅ ШАГ 4.3 активирован. RSI установлен на 35 / 65.")
        run_bot()
    except Exception as e:
        print("🔥 FATAL START ERROR:", e, flush=True)
        while True:
            time.sleep(30)

