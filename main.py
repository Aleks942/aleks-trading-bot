import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT STARTED — BTC CONTEXT → ALT SIGNALS ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10  # 10 минут
LIQ_RATIO = 1.5

STATE_FILE = "btc_alt_state.json"

ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

RSI_PERIOD = 14
RSI_LONG_LEVEL = 40
RSI_SHORT_LEVEL = 60

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync"]

# ===== TELEGRAM =====
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except:
        pass

# ===== UTILS =====
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

# ===== BTC LIQUIDATIONS =====
def get_liquidations():
    try:
        url = "https://fapi.coinglass.com/api/futures/liquidation_snapshot?symbol=BTC"
        data = requests.get(url, timeout=20).json()["data"]
        return float(data["longVolUsd"]), float(data["shortVolUsd"])
    except:
        return None, None

# ===== RSI =====
def get_rsi(prices):
    diff = prices.diff()
    gain = diff.where(diff > 0, 0)
    loss = -diff.where(diff < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-2]), float(rsi.iloc[-1])

def get_ohlc(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        prices = requests.get(url, params=params, timeout=20).json().get("prices", [])
        if len(prices) < 60:
            return None
        return pd.Series([p[1] for p in prices])
    except:
        return None

# ===== DEX =====
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
        if liq < ALT_MIN_LIQUIDITY or vol < ALT_MIN_VOLUME:
            return None
        return pair.get("dexId", "unknown")
    except:
        return None

# ===== MAIN =====
def run_bot():
    state = load_state()
    send_telegram("✅ BTC-контекст управляет сигналами по альтам")

    while True:
        long_liq, short_liq = get_liquidations()

        btc_prices = get_ohlc("bitcoin")
        if btc_prices is None or long_liq is None:
            time.sleep(CHECK_INTERVAL)
            continue

        btc_rsi_prev, btc_rsi_now = get_rsi(btc_prices)

        btc_context = "WAIT"
        if long_liq > short_liq * LIQ_RATIO and btc_rsi_prev < 40 and btc_rsi_now > btc_rsi_prev:
            btc_context = "LONG"
        elif short_liq > long_liq * LIQ_RATIO and btc_rsi_prev > 60 and btc_rsi_now < btc_rsi_prev:
            btc_context = "SHORT"

        if state.get("btc_context") != btc_context:
            send_telegram(f"🔄 BTC КОНТЕКСТ: <b>{btc_context}</b>")
            state["btc_context"] = btc_context
            save_state(state)

        if btc_context == "WAIT":
            time.sleep(CHECK_INTERVAL)
            continue

        for alt in ALT_TOKENS:
            prices = get_ohlc(alt)
            dex = dex_data(alt)
            if prices is None or dex is None:
                continue

            rsi_prev, rsi_now = get_rsi(prices)
            price_now = prices.iloc[-1]

            if btc_context == "LONG" and rsi_prev < RSI_LONG_LEVEL and rsi_now > rsi_prev:
                send_telegram(
                    f"🚀 <b>{alt.upper()} LONG</b>\n"
                    f"Цена: {round(price_now,4)}\n"
                    f"RSI: {round(rsi_prev,1)} → {round(rsi_now,1)}\n"
                    f"Контекст: BTC LONG"
                )

            if btc_context == "SHORT" and rsi_prev > RSI_SHORT_LEVEL and rsi_now < rsi_prev:
                send_telegram(
                    f"🔻 <b>{alt.upper()} SHORT</b>\n"
                    f"Цена: {round(price_now,4)}\n"
                    f"RSI: {round(rsi_prev,1)} → {round(rsi_now,1)}\n"
                    f"Контекст: BTC SHORT"
                )

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
