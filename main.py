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
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL"
}

TIMEFRAME_MINUTES = 5
CANDLES_LIMIT = 100
CHECK_INTERVAL = 60

DEPOSIT = 100.0
RISK_PERCENT = 1.0

RSI_LONG = 35
RSI_SHORT = 65

LAST_SIGNAL_FILE = "last_signal.txt"


# ---------- TELEGRAM ----------
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})


# ---------- COINGECKO OHLC ----------
def get_ohlc(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": 1}
    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    if not isinstance(data, list) or len(data) == 0:
        return None

    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
    return df.tail(CANDLES_LIMIT).reset_index(drop=True)


# ---------- INDICATORS ----------
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss

    return float((100 - (100 / (1 + rs))).iloc[-1])


def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return float(true_range.rolling(period).mean().iloc[-1])


# ---------- RISK ----------
def calc_trade(price, atr):
    risk_usd = DEPOSIT * (RISK_PERCENT / 100)
    position_size = risk_usd / atr
    stop_long = price - atr
    stop_short = price + atr
    tp1 = price + atr
    tp2 = price + atr * 2

    return risk_usd, position_size, stop_long, stop_short, tp1, tp2


# ---------- ANTI-DUPLICATE ----------
def load_last_signal():
    if not os.path.exists(LAST_SIGNAL_FILE):
        return None
    return open(LAST_SIGNAL_FILE).read().strip()


def save_last_signal(sig):
    open(LAST_SIGNAL_FILE, "w").write(sig)


# ---------- MAIN LOOP ----------
def run():
    send_telegram("Bot started. Strategy active: RSI 35/65, Risk 1%, TP1/TP2")

    while True:
        try:
            for coin_id, name in SYMBOLS.items():
                df = get_ohlc(coin_id)
                if df is None or len(df) < 30:
                    continue

                price = float(df["close"].iloc[-1])
                rsi = calculate_rsi(df["close"])
                atr = calculate_atr(df)

                signal = None
                if rsi < RSI_LONG:
                    signal = "LONG"
                elif rsi > RSI_SHORT:
                    signal = "SHORT"

                if not signal:
                    continue

                risk_usd, size, stop_long, stop_short, tp1, tp2 = calc_trade(price, atr)

                last = load_last_signal()
                sig_key = f"{name}-{signal}"

                if last == sig_key:
                    continue

                if signal == "LONG":
                    stop = stop_long
                else:
                    stop = stop_short

                msg = (
                    f"SIGNAL: {signal} | {name}\n\n"
                    f"Price: {round(price, 2)}\n"
                    f"RSI: {round(rsi, 2)}\n"
                    f"ATR: {round(atr, 4)}\n\n"
                    f"Entry: {round(price, 2)}\n"
                    f"STOP: {round(stop, 2)}\n"
                    f"TP1: {round(tp1, 2)}\n"
                    f"TP2: {round(tp2, 2)}\n\n"
                    f"Deposit: {DEPOSIT}$\n"
                    f"Risk: {risk_usd}$\n"
                    f"Position size: {round(size, 5)}\n\n"
                    f"Time UTC: {datetime.utcnow()}"
                )

                send_telegram(msg)
                save_last_signal(sig_key)

        except Exception as e:
            send_telegram(f"BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)


# ---------- START ----------
if __name__ == "__main__":
    print("BOOT OK: Strategy module started")
    run()

