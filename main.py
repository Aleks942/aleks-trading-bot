import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT STARTED — STEP 15 (TRADING SIGNALS) ===", flush=True)

# ===== MODE =====
BOT_MODE = "LIVE"  # DEBUG | LIVE | DAILY

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5

STATE_FILE = "last_sent_state.json"
DAILY_FILE = "daily_report_state.json"
SIGNALS_FILE = "signals_state.json"

# ===== RISK =====
START_DEPOSIT = 100.0
RISK_PERCENT = 1.0
RISK_USD = START_DEPOSIT * (RISK_PERCENT / 100.0)

# ===== LIMITS =====
ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

RSI_PERIOD = 14
ATR_PERIOD = 14

RSI_LONG = 35
RSI_SHORT = 65

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync"]

# ===== UTILS =====
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
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=15)
    except Exception as e:
        print("Telegram error:", e, flush=True)

# ===== DATA =====
def get_market_data(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        data = requests.get(url, timeout=20).json()["market_data"]
        return data["current_price"]["usd"]
    except:
        return None

def get_ohlc(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        prices = requests.get(url, params=params, timeout=20).json().get("prices", [])
        if len(prices) < 60:
            return None
        return pd.DataFrame({"close": [p[1] for p in prices]})
    except:
        return None

def rsi(df):
    d = df["close"].diff()
    g = d.where(d > 0, 0)
    l = -d.where(d < 0, 0)
    ag = g.rolling(RSI_PERIOD).mean()
    al = l.rolling(RSI_PERIOD).mean()
    rs = ag / al
    r = 100 - (100 / (1 + rs))
    return float(r.dropna().iloc[-1])

def atr(df):
    tr = df["close"].diff().abs()
    return float(tr.rolling(ATR_PERIOD).mean().dropna().iloc[-1])

def dex_data(coin):
    try:
        url = "https://api.dexscreener.com/latest/dex/search"
        data = requests.get(url, params={"q": coin}, timeout=15).json()
        pairs = data.get("pairs", [])
        if not pairs:
            return None
        pair = max(pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0))
        liq = pair.get("liquidity", {}).get("usd", 0)
        vol = pair.get("volume", {}).get("h24", 0)
        dex = pair.get("dexId", "unknown")
        if liq < ALT_MIN_LIQUIDITY or vol < ALT_MIN_VOLUME:
            return None
        return liq, vol, dex
    except:
        return None

# ===== MAIN =====
def run_bot():
    last_state = load_json(STATE_FILE, {})
    daily_state = load_json(DAILY_FILE, {})
    signal_state = load_json(SIGNALS_FILE, {})
    daily_signals = []

    if not last_state:
        send_telegram(f"✅ ЭТАП 3 АКТИВЕН. РЕЖИМ: {BOT_MODE}")

    while True:
        now = datetime.utcnow() + timedelta(hours=2)

        for alt in ALT_TOKENS:
            price = get_market_data(alt)
            df = get_ohlc(alt)
            dex = dex_data(alt)

            if price is None or df is None or dex is None:
                continue

            r = rsi(df)
            a = atr(df)
            liq, vol, dex_name = dex

            prev = signal_state.get(alt, {})
            prev_rsi = prev.get("rsi")

            signal = None

            if prev_rsi is not None:
                if prev_rsi < RSI_LONG and r >= RSI_LONG:
                    signal = "LONG"
                if prev_rsi > RSI_SHORT and r <= RSI_SHORT:
                    signal = "SHORT"

            if signal:
                stop = price - a if signal == "LONG" else price + a
                tp1 = price + a if signal == "LONG" else price - a
                tp2 = price + 2 * a if signal == "LONG" else price - 2 * a
                size = round(RISK_USD / abs(price - stop), 6)

                msg = (
                    f"🚨 <b>{signal} {alt.upper()}</b>\n"
                    f"Цена: {round(price,4)}\n"
                    f"RSI: {round(prev_rsi,2)} → {round(r,2)}\n"
                    f"STOP: {round(stop,4)}\n"
                    f"TP1: {round(tp1,4)} | TP2: {round(tp2,4)}\n"
                    f"Размер: {size}\n"
                    f"DEX: {dex_name}"
                )

                if BOT_MODE in ["DEBUG", "LIVE"]:
                    send_telegram(msg)

                if BOT_MODE == "DAILY":
                    daily_signals.append(msg)

            signal_state[alt] = {"rsi": r}
            save_json(SIGNALS_FILE, signal_state)

        if BOT_MODE == "DAILY" and now.hour == 20 and now.minute >= 30:
            if daily_signals:
                send_telegram("📊 <b>DAILY SIGNALS</b>\n\n" + "\n\n".join(daily_signals))
            daily_signals.clear()
            save_json(DAILY_FILE, {"date": now.strftime("%Y-%m-%d")})

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()

