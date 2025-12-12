import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT STARTED — SIGNAL STRENGTH 1–5 ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10

LIQ_RATIO_BASE = 1.5
LIQ_RATIO_STRONG = 2.0

ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

RSI_PERIOD = 14
RSI_LONG_LEVEL = 40
RSI_LONG_STRONG = 35
RSI_SHORT_LEVEL = 60
RSI_SHORT_STRONG = 65

STATE_FILE = "signal_strength_state.json"

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync"]

# ===== TELEGRAM =====
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=15)
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

# ===== DATA =====
def get_liquidations():
    try:
        url = "https://fapi.coinglass.com/api/futures/liquidation_snapshot?symbol=BTC"
        data = requests.get(url, timeout=20).json()["data"]
        return float(data["longVolUsd"]), float(data["shortVolUsd"])
    except:
        return None, None

def get_prices(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        prices = requests.get(url, params=params, timeout=20).json().get("prices", [])
        if len(prices) < 60:
            return None
        return pd.Series([p[1] for p in prices])
    except:
        return None

def rsi(series):
    diff = series.diff()
    gain = diff.where(diff > 0, 0)
    loss = -diff.where(diff < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-2]), float(rsi.iloc[-1])

def dex_liquidity(coin):
    try:
        url = "https://api.dexscreener.com/latest/dex/search"
        pairs = requests.get(url, params={"q": coin}, timeout=15).json().get("pairs", [])
        if not pairs:
            return None
        pair = max(pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0))
        return pair.get("liquidity", {}).get("usd", 0), pair.get("dexId", "unknown")
    except:
        return None

# ===== MAIN =====
def run_bot():
    state = load_state()
    send_telegram("✅ Сила сигнала 1–5 активирована")

    while True:
        long_liq, short_liq = get_liquidations()
        btc_prices = get_prices("bitcoin")

        if None in (long_liq, short_liq, btc_prices):
            time.sleep(CHECK_INTERVAL)
            continue

        btc_rsi_prev, btc_rsi_now = rsi(btc_prices)

        btc_context = "WAIT"
        strength_liq = 0

        if long_liq > short_liq * LIQ_RATIO_BASE:
            btc_context = "LONG"
            if long_liq > short_liq * LIQ_RATIO_STRONG:
                strength_liq = 1

        elif short_liq > long_liq * LIQ_RATIO_BASE:
            btc_context = "SHORT"
            if short_liq > long_liq * LIQ_RATIO_STRONG:
                strength_liq = 1

        for alt in ALT_TOKENS:
            prices = get_prices(alt)
            dex = dex_liquidity(alt)

            if prices is None or dex is None:
                continue

            liq, dex_name = dex
            rsi_prev, rsi_now = rsi(prices)

            score = 0
            reasons = []

            # 1. BTC контекст
            if btc_context in ["LONG", "SHORT"]:
                score += 1
                reasons.append("BTC контекст")

            # 2. Сильные ликвидации
            if strength_liq:
                score += 1
                reasons.append("Сильные ликвидации")

            # 3–4. RSI альта
            if btc_context == "LONG" and rsi_prev < RSI_LONG_STRONG:
                score += 1
                reasons.append("RSI перепродан")

            if btc_context == "SHORT" and rsi_prev > RSI_SHORT_STRONG:
                score += 1
                reasons.append("RSI перекуплен")

            if btc_context == "LONG" and rsi_now > rsi_prev:
                score += 1
                reasons.append("RSI разворачивается")

            if btc_context == "SHORT" and rsi_now < rsi_prev:
                score += 1
                reasons.append("RSI разворачивается")

            # 5. Ликвидность
            if liq > ALT_MIN_LIQUIDITY * 2:
                score += 1
                reasons.append("Высокая ликвидность")

            if score < 3:
                continue  # слабые сигналы не шлём

            price_now = prices.iloc[-1]

            send_telegram(
                f"{'🚀' if btc_context=='LONG' else '🔻'} <b>{alt.upper()} {btc_context}</b>\n"
                f"Цена: {round(price_now,4)}\n"
                f"RSI: {round(rsi_prev,1)} → {round(rsi_now,1)}\n"
                f"DEX: {dex_name}\n\n"
                f"🔥 <b>СИЛА СИГНАЛА: {score} / 5</b>\n"
                f"Причины:\n• " + "\n• ".join(reasons)
            )

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
