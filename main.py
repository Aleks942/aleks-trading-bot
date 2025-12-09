import os
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT"
}

RISK_PERCENT = 1.0
RSI_LOW = 35
RSI_HIGH = 65
CHECK_INTERVAL = 60

last_signals = {}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def get_ohlc(symbol):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "5m", "limit": 100}
    data = requests.get(url, params=params).json()
    df = pd.DataFrame(data, columns=["t","o","h","l","c","v","x","q","n","tb","tq","i"])
    df = df[["o","h","l","c"]].astype(float)
    return df

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    high = df["h"]
    low = df["l"]
    close = df["c"]
    ranges = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1)
    tr = ranges.max(axis=1)
    return tr.rolling(period).mean()

def ema(series, period=50):
    return series.ewm(span=period, adjust=False).mean()

def coingecko(symbol):
    ids = {"BTC":"bitcoin","ETH":"ethereum","SOL":"solana"}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ids[symbol],
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_change": "true"
    }
    data = requests.get(url, params=params).json()[ids[symbol]]
    return data["usd"], data["usd_market_cap"], data["usd_24h_change"]

def calc_position(balance, risk_pct, entry, stop):
    risk = balance * risk_pct / 100
    size = risk / abs(entry - stop)
    return round(size, 6), round(risk, 2)

def check_duplicate(symbol, side, price):
    prev = last_signals.get(symbol)
    if not prev:
        return False
    old_side, old_price = prev
    if old_side == side:
        if abs(price - old_price) / old_price < 0.004:
            return True
    return False

def run():
    send_telegram("Bot started. Strategy: RSI 35/65 + EMA50 + Risk 1% + TP1/TP2")

    while True:
        try:
            for name, sym in SYMBOLS.items():
                df = get_ohlc(sym)
                close = df["c"]
                last_price = close.iloc[-1]

                rsi_val = rsi(close).iloc[-1]
                atr_val = atr(df).iloc[-1]
                ema50 = ema(close).iloc[-1]

                price_cg, cap, cap_change = coingecko(name)

                signal = None

                if rsi_val < RSI_LOW and last_price > ema50:
                    signal = "LONG"
                elif rsi_val > RSI_HIGH and last_price < ema50:
                    signal = "SHORT"

                if not signal:
                    continue

                if check_duplicate(name, signal, last_price):
                    continue

                if signal == "LONG":
                    entry = last_price
                    stop = entry - atr_val
                    tp1 = entry + atr_val
                    tp2 = entry + atr_val * 2
                else:
                    entry = last_price
                    stop = entry + atr_val
                    tp1 = entry - atr_val
                    tp2 = entry - atr_val * 2

                size, risk = calc_position(100, RISK_PERCENT, entry, stop)

                text = f"""
SIGNAL: {signal} | {name}

Price: {round(last_price,2)}
RSI: {round(rsi_val,2)}
ATR: {round(atr_val,2)}
EMA50: {round(ema50,2)}

Entry: {round(entry,2)}
STOP: {round(stop,2)}
TP1: {round(tp1,2)}
TP2: {round(tp2,2)}

Deposit: 100.0$
Risk: {risk}$
Position size: {size}

Cap: {round(cap,0)}
Cap 24h: {round(cap_change,2)}%

Time UTC: {datetime.utcnow()}
"""
                send_telegram(text)
                last_signals[name] = (signal, last_price)

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            send_telegram(f"BOT ERROR: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run()

