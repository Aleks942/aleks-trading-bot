import os
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60
RISK_PERCENT = 1
DEPOSIT = 100
RSI_LOW = 35
RSI_HIGH = 65
ATR_MULT = 1

SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL"
}

DEX_SYMBOLS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana"
}

LAST_SIGNAL_FILE = "last_signal.txt"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass

def load_last():
    if not os.path.exists(LAST_SIGNAL_FILE):
        return ""
    with open(LAST_SIGNAL_FILE, "r") as f:
        return f.read()

def save_last(sig):
    with open(LAST_SIGNAL_FILE, "w") as f:
        f.write(sig)

def get_market_data():
    ids = ",".join(SYMBOLS.keys())
    url = f"https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ids,
        "price_change_percentage": "24h"
    }
    r = requests.get(url, params=params, timeout=10).json()
    return r

def get_dex(symbol):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    r = requests.get(url, timeout=10).json()
    if "pairs" not in r or not r["pairs"]:
        return None, None, None
    p = r["pairs"][0]
    return p.get("dexId"), float(p.get("liquidity", {}).get("usd", 0)), float(p.get("volume", {}).get("h24", 0))

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc"
    r = requests.get(url, params={"vs_currency": "usd", "days": 1}, timeout=10).json()
    df = pd.DataFrame(r, columns=["time", "open", "high", "low", "close"])
    return df

def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def calculate_atr(df, period=14):
    df["tr"] = df["high"] - df["low"]
    atr = df["tr"].rolling(period).mean()
    return float(atr.iloc[-1])

def calc_position(atr):
    risk = DEPOSIT * RISK_PERCENT / 100
    size = risk / atr
    return round(size, 5)

send_telegram("Bot started. Strategy: RSI 35/65 + Risk 1% + TP1/TP2")

while True:
    try:
        market = get_market_data()
        last = load_last()

        for item in market:
            name = item["id"]
            symbol = SYMBOLS[name]
            price = float(item["current_price"])
            cap = float(item["market_cap"])
            cap_ch = float(item.get("market_cap_change_percentage_24h", 0))

            df = get_ohlc(name)
            rsi = calculate_rsi(df)
            atr = calculate_atr(df)

            dex, liq, vol = get_dex(symbol)

            signal = None
            if rsi >= RSI_HIGH:
                signal = "SHORT"
            elif rsi <= RSI_LOW:
                signal = "LONG"

            if signal:
                uid = f"{symbol}_{signal}"
                if uid != last:
                    stop = price + atr if signal == "SHORT" else price - atr
                    tp1 = price - atr if signal == "SHORT" else price + atr
                    tp2 = price - atr * 2 if signal == "SHORT" else price + atr * 2
                    size = calc_position(atr)

                    msg = (
                        f"SIGNAL: {signal} | {symbol}\n\n"
                        f"Price: {round(price,5)}\n"
                        f"RSI: {round(rsi,2)}\n"
                        f"ATR: {round(atr,5)}\n\n"
                        f"Entry: {round(price,5)}\n"
                        f"STOP: {round(stop,5)}\n"
                        f"TP1: {round(tp1,5)}\n"
                        f"TP2: {round(tp2,5)}\n\n"
                        f"Deposit: {DEPOSIT}$\n"
                        f"Risk: {RISK_PERCENT}%\n"
                        f"Position size: {round(size,5)}\n\n"
                        f"Cap: {int(cap)}$\n"
                        f"Cap 24h: {round(cap_ch,2)}%\n"
                        f"DEX: {dex}\n"
                        f"Liquidity: {liq}$\n"
                        f"Volume 24h: {vol}$\n"
                        f"Time UTC: {datetime.utcnow()}"
                    )

                    send_telegram(msg)
                    save_last(uid)

    except Exception as e:
        send_telegram(f"BOT ERROR: {e}")

    time.sleep(CHECK_INTERVAL)
