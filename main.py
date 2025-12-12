import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT STARTED — STEP 14 (MODES) ===", flush=True)

# ===== MODE =====
BOT_MODE = "LIVE"  # DEBUG | LIVE | DAILY

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5  # 5 минут

STATE_FILE = "last_sent_state.json"
DAILY_FILE = "daily_report_state.json"

# ===== LIMITS =====
PRICE_CHANGE_LIMIT = 1.0   # %
RSI_CHANGE_LIMIT = 2.0     # пункта

ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

RSI_PERIOD = 14

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync"]

# ===== FILE UTILS =====
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
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except Exception as e:
        print("Telegram error:", e, flush=True)

# ===== DATA =====
def get_market_data(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        data = requests.get(url, timeout=20).json()["market_data"]
        return (
            data["current_price"]["usd"],
            data["price_change_percentage_24h"]
        )
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
    diff = df["close"].diff()
    gain = diff.where(diff > 0, 0)
    loss = -diff.where(diff < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    r = 100 - (100 / (1 + rs))
    return round(float(r.dropna().iloc[-1]), 2)

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

# ===== EVENT CHECK =====
def is_event(last, current):
    if last is None:
        return True
    price_diff = abs((current["price"] - last["price"]) / last["price"]) * 100
    rsi_diff = abs(current["rsi"] - last["rsi"])
    return price_diff >= PRICE_CHANGE_LIMIT or rsi_diff >= RSI_CHANGE_LIMIT

# ===== DAILY REPORT =====
def daily_report(daily_state, summary):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if daily_state.get("date") == today:
        return daily_state

    send_telegram(
        "📊 <b>DAILY REPORT</b>\n" +
        "\n".join(summary) if summary else "📊 DAILY REPORT\nНет значимых событий."
    )

    return {"date": today}

# ===== MAIN LOOP =====
def run_bot():
    state = load_json(STATE_FILE, {})
    daily_state = load_json(DAILY_FILE, {})
    daily_summary = []

    if not state:
        send_telegram(f"✅ ЭТАП 2 АКТИВЕН. РЕЖИМ: {BOT_MODE}")

    while True:
        now = datetime.utcnow() + timedelta(hours=2)  # Польша

        for alt in ALT_TOKENS:
            market = get_market_data(alt)
            df = get_ohlc(alt)
            dex = dex_data(alt)

            if market is None or df is None or dex is None:
                continue

            price, price_chg = market
            r = rsi(df)
            liq, vol, dex_name = dex

            current = {"price": price, "rsi": r, "time": now.isoformat()}
            last = state.get(alt)

            if not is_event(last, current):
                continue

            msg = (
                f"📊 <b>{alt.upper()}</b>\n"
                f"Цена: {price}$ ({round(price_chg,2)}%)\n"
                f"RSI: {r}\n"
                f"DEX: {dex_name}\n"
                f"Ликв: {round(liq,0)}$ | Объём: {round(vol,0)}$"
            )

            if BOT_MODE in ["DEBUG", "LIVE"]:
                send_telegram(msg)

            if BOT_MODE == "DAILY":
                daily_summary.append(f"{alt.upper()} → Цена {round(price_chg,2)}%, RSI {r}")

            state[alt] = current
            save_json(STATE_FILE, state)

        if BOT_MODE == "DAILY" and now.hour == 20 and now.minute >= 30:
            daily_state = daily_report(daily_state, daily_summary)
            save_json(DAILY_FILE, daily_state)
            daily_summary.clear()

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
