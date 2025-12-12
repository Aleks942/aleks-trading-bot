import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT BOOT STARTED (STEP 12 — MARKET CAP + LIQUIDATIONS) ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5  # 5 минут

# ===== FILES =====
STATE_FILE = "last_states.json"
POSITIONS_FILE = "open_positions.json"
TRADES_LOG_FILE = "trades_log.json"

# ===== RISK =====
START_DEPOSIT = 100.0
RISK_PERCENT = 1.0
RISK_USD = START_DEPOSIT * (RISK_PERCENT / 100.0)

# ===== FILTERS =====
ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

# ===== INDICATORS =====
RSI_PERIOD = 14
ATR_PERIOD = 14

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
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print("Telegram error:", e, flush=True)

# ===== COINGECKO MARKET DATA =====
def get_market_data(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        r = requests.get(url, timeout=20)
        data = r.json()["market_data"]

        price = data["current_price"]["usd"]
        cap = data["market_cap"]["usd"]
        cap_change = data["market_cap_change_percentage_24h"]
        price_change = data["price_change_percentage_24h"]

        return price, cap, cap_change, price_change
    except Exception as e:
        print("Market data error:", e, flush=True)
        return None

# ===== COINGECKO PRICE HISTORY =====
def get_ohlc(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {
            "vs_currency": "usd",
            "days": 3
        }
        r = requests.get(url, params=params, timeout=20)
        data = r.json()

        prices = data.get("prices", [])
        if len(prices) < 60:
            return None

        return pd.DataFrame({"close": [p[1] for p in prices]})
    except Exception as e:
        print("OHLC error:", e, flush=True)
        return None

# ===== INDICATORS =====
def rsi(df):
    d = df["close"].diff()
    gain = d.where(d > 0, 0)
    loss = -d.where(d < 0, 0)

    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()

    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return round(float(rsi_val.dropna().iloc[-1]), 2)

# ===== DEXSCREENER =====
def dex_data(query):
    try:
        url = "https://api.dexscreener.com/latest/dex/search"
        params = {"q": query}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

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
    except Exception as e:
        print("DEX error:", e, flush=True)
        return None

# ===== LIQUIDATIONS =====
def get_liquidations(symbol="BTC"):
    try:
        url = f"https://fapi.coinglass.com/api/futures/liquidation_snapshot?symbol={symbol}"
        r = requests.get(url, timeout=20)
        data = r.json()["data"]

        return round(data["longVolUsd"], 2), round(data["shortVolUsd"], 2)
    except Exception as e:
        print("Liquidation error:", e, flush=True)
        return None, None

# ===== MAIN LOOP =====
def run_bot():
    send_telegram("✅ ШАГ 12 активирован. Капитализация и ликвидации работают.")

    while True:
        try:
            # --- BTC LIQUIDATIONS ---
            btc_long, btc_short = get_liquidations("BTC")
            if btc_long is not None and btc_short is not None:
                send_telegram(
                    f"💥 <b>ЛИКВИДАЦИИ BTC (24ч)</b>\n"
                    f"LONG: {btc_long}$\n"
                    f"SHORT: {btc_short}$"
                )

            # --- ALT DATA ---
            for alt in ALT_TOKENS:
                df = get_ohlc(alt)
                market = get_market_data(alt)
                dex = dex_data(alt)

                if df is None or df.empty:
                    continue
                if market is None or dex is None:
                    continue

                price, cap, cap_change, price_change = market
                r = rsi(df)
                liq, vol, dex_name = dex

                send_telegram(
                    f"📊 <b>{alt.upper()}</b>\n"
                    f"Цена: {price}$\n"
                    f"Cap: {round(cap, 0)}$\n"
                    f"Cap 24ч: {round(cap_change, 2)}%\n"
                    f"Цена 24ч: {round(price_change, 2)}%\n"
                    f"RSI: {r}\n"
                    f"DEX: {dex_name}\n"
                    f"Ликв: {round(liq,0)}$ | Объём: {round(vol,0)}$"
                )

        except Exception as e:
            send_telegram(f"❌ BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
