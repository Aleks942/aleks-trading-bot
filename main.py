# === ШАГ 12 — КАПИТАЛИЗАЦИЯ + ЛИКВИДАЦИИ (ИНФОРМАЦИОННО) ===

import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT BOOT STARTED (STEP 12 — MARKET CAP + LIQUIDATIONS) ===", flush=True)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5

STATE_FILE = "last_states.json"
POSITIONS_FILE = "open_positions.json"
TRADES_LOG_FILE = "trades_log.json"
DAILY_REPORT_FILE = "daily_report_state.json"

# ===== ВРЕМЯ ОТЧЁТА =====
REPORT_HOUR = 20
REPORT_MINUTE = 30   # 20:30 Польша (UTC+2)

# ===== РИСК =====
START_DEPOSIT = 100.0
RISK_PERCENT = 1.0
RISK_USD = START_DEPOSIT * (RISK_PERCENT / 100.0)

# ===== ФИЛЬТРЫ =====
ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

# ===== ИНДИКАТОРЫ =====
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65
EMA_FAST = 50
EMA_SLOW = 200

# ===== ТРЕЙЛИНГ =====
TRAIL_MULT = 1.5

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync"]

# ===== УТИЛИТЫ =====
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
        json.dump(data, f, indent=2)

# ===== TELEGRAM =====
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=15)
    except:
        pass

# ===== COINGECKO (ЦЕНЫ + КАПИТАЛИЗАЦИЯ) =====
def get_market_data(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        data = requests.get(url, timeout=20).json()["market_data"]

        price = data["current_price"]["usd"]
        cap = data["market_cap"]["usd"]
        cap_change = data["market_cap_change_percentage_24h"]
        price_change = data["price_change_percentage_24h"]

        return price, cap, cap_change, price_change
    except:
        return None

def get_ohlc(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        data = requests.get(url, params=params, timeout=20).json()
        prices = data.get("prices", [])
        if len(prices) < 60:
            return None
        return pd.DataFrame({"close": [x[1] for x in prices]})
    except:
        return None

# ===== ИНДИКАТОРЫ =====
def rsi(df):
    d = df["close"].diff()
    g = d.where(d > 0, 0)
    l = -d.where(d < 0, 0)
    ag = g.rolling(RSI_PERIOD).mean()
    al = l.rolling(RSI_PERIOD).mean()
    rs = ag / al
    r = 100 - (100 / (1 + rs))
    return round(float(r.dropna().iloc[-1]), 2)

def atr(df):
    tr = df["close"].diff().abs()
    return round(float(tr.rolling(ATR_PERIOD).mean().dropna().iloc[-1]), 6)

def ema(df, p):
    if len(df) < p:
        return None
    return round(float(df["close"].ewm(span=p).mean().iloc[-1]), 6)

# ===== DEX =====
def dex_data(query):
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

# ===== ЛИКВИДАЦИИ (АГРЕГАТОР) =====
def get_liquidations(symbol="BTC"):
    try:
        url = f"https://fapi.coinglass.com/api/futures/liquidation_snapshot?symbol={symbol}"
        r = requests.get(url, timeout=20)
        data = r.json()["data"]

        long_liq = data["longVolUsd"]
        short_liq = data["shortVolUsd"]

        return round(long_liq, 2), round(short_liq, 2)
    except:
        return None, None

# ===== ЖУРНАЛ =====
def log_trade(trade):
    log = load_json(TRADES_LOG_FILE, [])
    log.append(trade)
    save_json(TRADES_LOG_FILE, log)

# ===== СДЕЛКИ =====
def open_position(alt, side, price, atr_v, dex):
    stop = price - atr_v if side == "LONG" else price + atr_v
    tp1 = price + atr_v if side == "LONG" else price - atr_v
    tp2 = price + atr_v * 2 if side == "LONG" else price - atr_v * 2
    size = round(RISK_USD / abs(price - stop), 6)

    pos = {
        "alt": alt, "side": side,
        "entry": round(price, 6),
        "stop": round(stop, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "atr": atr_v,
        "size": size,
        "tp1_done": False,
        "active": True,
        "dex": dex,
        "time": datetime.utcnow().isoformat()
    }

    send_telegram(
        f"<b>ОТКРЫТА СДЕЛКА</b>\n{alt.upper()} {side}\n"
        f"Вход: {price}\nSTOP: {stop}\nTP1: {tp1} | TP2: {tp2}\nРазмер: {size}"
    )

    return pos

# ===== ОСНОВНОЙ ЦИКЛ =====
def run_bot():
    states = load_json(STATE_FILE, {})
    positions = load_json(POSITIONS_FILE, {})

    send_telegram("✅ ШАГ 12 активирован. Капитализация + ликвидации добавлены.")

    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=2)  # Польша UTC+2

            # === ЛИКВИДАЦИИ BTC (ИНФО)
            btc_long_liq, btc_short_liq = get_liquidations("BTC")

            if btc_long_liq and btc_short_liq:
                send_telegram(
                    f"💥 <b>ЛИКВИДАЦИИ BTC (24ч)</b>\n"
                    f"LONG: {btc_long_liq}$\n"
                    f"SHORT: {btc_short_liq}$"
                )

            # === АЛЬТЫ + КАПИТАЛИЗАЦИЯ
            for alt in ALT_TOKENS:
                df = get_ohlc(alt)
                market = get_market_data(alt)
                dex = dex_data(alt)

                if not df or not market or not dex:
                    continue

                price, cap, cap_change, price_change = market
                r = rsi(df)

                liq, vol, dex_name = dex

                send_telegram(
                    f"📊 <b>{alt.upper()}</b>\n"
                    f"Цена: {price}$\n"
                    f"Cap: {round(cap,0)}$\n"
                    f"Cap 24ч: {round(cap_change,2)}%\n"
                    f"Цена 24ч: {round(price_change,2)}%\n"
                    f"RSI: {r}\n"
                    f"DEX: {dex_name}\n"
                    f"Ликв: {round(liq,0)}$ | Объём: {round(vol,0)}$"
                )

        except Exception as e:
            send_telegram(f"❌ BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
