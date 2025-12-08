# === ШАГ 9 — ТРЕЙЛИНГ-СТОП 1.5×ATR (ПОСЛЕ TP1) ===

import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 9 — TRAILING 1.5 ATR) ===", flush=True)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5
STATE_FILE = "last_states.json"
POSITIONS_FILE = "open_positions.json"

# ===== РИСК =====
DEPOSIT_USD = 100.0
RISK_PERCENT = 1.0
RISK_USD = DEPOSIT_USD * (RISK_PERCENT / 100.0)

# ===== УСИЛЕННЫЕ ФИЛЬТРЫ (ШАГ 8) =====
ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

# ===== ПАРАМЕТРЫ ИНДИКАТОРОВ =====
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65
EMA_FAST = 50
EMA_SLOW = 200

# ===== ТРЕЙЛИНГ =====
TRAIL_MULT = 1.5  # выбран вариант 2

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync-era"]

# ===== УТИЛИТЫ СОСТОЯНИЯ =====
def load_json_safe(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json_safe(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

# ===== TELEGRAM =====
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=15)
    except:
        pass

# ===== COINGECKO (ЦЕНЫ И ИСТОРИЯ) =====
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

# ===== DEX (ШАГ 8 — УСИЛЕННЫЙ ФИЛЬТР) =====
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

        if liq < ALT_MIN_LIQUIDITY or vol < ALT_MIN_VOLUME:
            return None

        return liq, vol, dex
    except:
        return None

# ===== ОТКРЫТИЕ СДЕЛКИ =====
def open_position(alt, signal, price, atr, dex):
    stop = price - atr if signal == "LONG" else price + atr
    tp1 = price + atr if signal == "LONG" else price - atr
    tp2 = price + atr * 2 if signal == "LONG" else price - atr * 2
    stop_dist = abs(price - stop)
    size = round(RISK_USD / stop_dist, 6)

    pos = {
        "alt": alt,
        "signal": signal,
        "entry": round(price, 6),
        "stop": round(stop, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "atr": atr,
        "size": size,
        "dex": dex,
        "tp1_done": False,
        "active": True
    }

    send_telegram(
        f"<b>ОТКРЫТИЕ СДЕЛКИ</b>\n"
        f"{alt.upper()} | {signal}\n"
        f"Вход: {round(price,6)}\n"
        f"STOP: {round(stop,6)}\n"
        f"TP1: {round(tp1,6)} | TP2: {round(tp2,6)}\n"
        f"Размер: {size}\nDEX: {dex}"
    )
    return pos

# ===== ОБНОВЛЕНИЕ ТРЕЙЛИНГА =====
def update_trailing(pos, current_price):
    atr = pos["atr"]
    trail_dist = atr * TRAIL_MULT

    if pos["signal"] == "LONG":
        # фиксация TP1 → безубыток
        if (not pos["tp1_done"]) and current_price >= pos["tp1"]:
            pos["tp1_done"] = True
            pos["stop"] = pos["entry"]
            send_telegram(f"🔒 TP1 достигнут, STOP в безубытке: {pos['stop']}")
        # трейлинг после TP1
        if pos["tp1_done"]:
            new_stop = max(pos["stop"], current_price - trail_dist)
            pos["stop"] = round(new_stop, 6)
        # выход по стопу
        if current_price <= pos["stop"]:
            pos["active"] = False
            send_telegram(f"✅ ТРЕЙЛИНГ-ВЫХОД: {pos['alt'].upper()} | Цена: {current_price}")
    else:
        if (not pos["tp1_done"]) and current_price <= pos["tp1"]:
            pos["tp1_done"] = True
            pos["stop"] = pos["entry"]
            send_telegram(f"🔒 TP1 достигнут, STOP в безубытке: {pos['stop']}")
        if pos["tp1_done"]:
            new_stop = min(pos["stop"], current_price + trail_dist)
            pos["stop"] = round(new_stop, 6)
        if current_price >= pos["stop"]:
            pos["active"] = False
            send_telegram(f"✅ ТРЕЙЛИНГ-ВЫХОД: {pos['alt'].upper()} | Цена: {current_price}")

    return pos

# ===== ОСНОВНОЙ ЦИКЛ =====
def run_bot():
    last_states = load_json_safe(STATE_FILE, {})
    positions = load_json_safe(POSITIONS_FILE, {})

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # ---- 1) ОБНОВЛЯЕМ ТРЕЙЛИНГ ПО ОТКРЫТЫМ ПОЗИЦИЯМ
            for alt, pos in list(positions.items()):
                if not pos.get("active"):
                    continue

                df = get_ohlc_from_coingecko(alt)
                if df is None:
                    continue

                price = float(df["close"].iloc[-1])
                pos = update_trailing(pos, price)
                positions[alt] = pos

                if not pos["active"]:
                    positions.pop(alt, None)

            save_json_safe(POSITIONS_FILE, positions)

            # ---- 2) ИЩЕМ НОВЫЕ СИГНАЛЫ (ЕСЛИ ПОЗИЦИЯ НЕ ОТКРЫТА)
            report = "<b>📈 СИГНАЛЫ (ШАГ 9 — ТРЕЙЛИНГ 1.5×ATR)</b>\n\n"
            signals_found = False

            for alt in ALT_TOKENS:
                if alt in positions:
                    continue

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
                save_json_safe(STATE_FILE, last_states)

                if signal == "NEUTRAL":
                    continue

                liq, vol, dex = dex_data
                pos = open_position(alt, signal, price, atr, dex)
                positions[alt] = pos
                save_json_safe(POSITIONS_FILE, positions)

                signals_found = True

                report += (
                    f"<b>{alt.upper()}</b>\n"
                    f"СИГНАЛ: <b>{signal}</b>\n"
                    f"Цена: {round(price,6)}\n"
                    f"RSI: {rsi}\n"
                    f"EMA50: {ema50} | EMA200: {ema200}\n"
                    f"Ликвидность: {round(liq,2)}$ | Объём: {round(vol,2)}$\n\n"
                )

            if not signals_found:
                report += "Нет новых сигналов.\n\n"

            report += f"⏱ UTC: {now}"
            send_telegram(report)

        except Exception as e:
            send_telegram(f"❌ BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    send_telegram("✅ ШАГ 9 активирован. Трейлинг-стоп 1.5×ATR после TP1.")
    run_bot()
