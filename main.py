import os
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 300  # 5 минут

REPORT_HOUR = 20
REPORT_MINUTE = 30  # 20:30 UTC+2

START_DEPOSIT = 100.0
RISK_PERCENT = 1.0
RISK_USD = START_DEPOSIT * (RISK_PERCENT / 100.0)

ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

RSI_PERIOD = 14
ATR_PERIOD = 14

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync-era"]

STATE_FILE = "state.json"
TRADES_FILE = "trades.json"
REPORT_FILE = "report_state.json"

# ---------- УТИЛИТЫ ----------
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

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

# ---------- COINGECKO ----------
def get_market_data(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        d = requests.get(url, timeout=20).json()["market_data"]

        return {
            "price": float(d["current_price"]["usd"]),
            "cap": float(d["market_cap"]["usd"]),
            "cap_change": float(d["market_cap_change_percentage_24h"]),
            "price_change": float(d["price_change_percentage_24h"])
        }
    except:
        return None

def get_ohlc(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        r = requests.get(url, params={"vs_currency": "usd", "days": 3}, timeout=20).json()
        prices = r.get("prices", [])
        if len(prices) < 50:
            return None
        return pd.DataFrame({"close": [x[1] for x in prices]})
    except:
        return None

# ---------- ИНДИКАТОРЫ ----------
def rsi(df):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    return round(float(100 - (100 / (1 + rs))).iloc[-1], 2)

def atr(df):
    tr = df["close"].diff().abs()
    return round(float(tr.rolling(ATR_PERIOD).mean().iloc[-1]), 6)

# ---------- DEX ----------
def dex_data(query):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        r = requests.get(url, timeout=15).json()
        pairs = r.get("pairs", [])
        if not pairs:
            return None

        best = max(pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0))

        liq = float(best.get("liquidity", {}).get("usd", 0))
        vol = float(best.get("volume", {}).get("h24", 0))
        dex = best.get("dexId")

        if liq < ALT_MIN_LIQUIDITY or vol < ALT_MIN_VOLUME:
            return None

        return liq, vol, dex
    except:
        return None

# ---------- ЛИКВИДАЦИИ ----------
def get_liquidations(symbol="BTC"):
    try:
        url = f"https://fapi.coinglass.com/api/futures/liquidation_snapshot?symbol={symbol}"
        r = requests.get(url, timeout=20).json()["data"]

        return float(r["longVolUsd"]), float(r["shortVolUsd"])
    except:
        return None, None

# ---------- ДНЕВНОЙ ОТЧЁТ ----------
def send_daily_report():
    trades = load_json(TRADES_FILE, [])
    today = datetime.utcnow().date()

    today_trades = [t for t in trades if datetime.fromisoformat(t["time"]).date() == today]

    day_pnl = sum(t["pnl"] for t in today_trades)
    total_pnl = sum(t["pnl"] for t in trades)

    deposit = START_DEPOSIT + total_pnl

    msg = (
        f"📊 ДНЕВНОЙ ОТЧЁТ\n\n"
        f"Дата: {today}\n"
        f"Сделок за день: {len(today_trades)}\n"
        f"Дневной PnL: {round(day_pnl,2)}$\n\n"
        f"Всего сделок: {len(trades)}\n"
        f"Общий PnL: {round(total_pnl,2)}$\n"
        f"Депозит: {round(deposit,2)}$"
    )

    send_telegram(msg)

# ---------- ОСНОВНОЙ ЦИКЛ ----------
def run_bot():
    send_telegram("✅ ШАГ 12 активирован. Капитализация + ликвидации + отчёт 20:30.")

    report_state = load_json(REPORT_FILE, {"last_date": None})

    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=2)

            # Ликвидации BTC
            long_liq, short_liq = get_liquidations()
            if long_liq and short_liq:
                send_telegram(
                    f"💥 ЛИКВИДАЦИИ BTC\n"
                    f"LONG: {round(long_liq,2)}$\n"
                    f"SHORT: {round(short_liq,2)}$"
                )

            # Альты + капа
            for alt in ALT_TOKENS:
                df = get_ohlc(alt)
                market = get_market_data(alt)
                dex = dex_data(alt)

                if df is None or df.empty or market is None or dex is None:
                    continue

                r = rsi(df)
                a = atr(df)

                price = market["price"]
                cap = market["cap"]
                cap_change = market["cap_change"]
                price_change = market["price_change"]

                liq, vol, dex_name = dex

                send_telegram(
                    f"📊 {alt.upper()}\n"
                    f"Цена: {price}$\n"
                    f"Cap: {round(cap,0)}$\n"
                    f"Cap 24ч: {round(cap_change,2)}%\n"
                    f"Цена 24ч: {round(price_change,2)}%\n"
                    f"RSI: {r}\n"
                    f"ATR: {a}\n"
                    f"DEX: {dex_name}\n"
                    f"Ликв: {round(liq,0)}$ | Объём: {round(vol,0)}$"
                )

            # Дневной отчёт в 20:30
            today_str = now.date().isoformat()
            if (
                now.hour == REPORT_HOUR
                and now.minute >= REPORT_MINUTE
                and report_state.get("last_date") != today_str
            ):
                send_daily_report()
                report_state["last_date"] = today_str
                save_json(REPORT_FILE, report_state)

        except Exception as e:
            send_telegram(f"❌ BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
