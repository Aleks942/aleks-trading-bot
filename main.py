import requests
import time
import pandas as pd
from datetime import datetime

# ================= CONFIG =================

BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN"
CHAT_ID = "PASTE_YOUR_CHAT_ID"

INTERVAL = 3600  # 1H
DEPOSIT = 100
RISK_PERCENT = 1

RSI_LOW = 35
RSI_HIGH = 65

LAST_SIGNAL = {}

SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "arbitrum": "ARB",
    "optimism": "OP",
    "polygon": "MATIC",
    "immutable-x": "IMX",
    "starknet": "STRK",
    "loopring": "LRC"
}

# ================= TELEGRAM =================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ================= DATA =================

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days=2"
    r = requests.get(url, timeout=20)
    data = r.json()
    if not isinstance(data, list) or len(data) < 30:
        return None
    df = pd.DataFrame(data, columns=["time","open","high","low","close"])
    return df.tail(30)

def get_market(symbol):
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": symbol,
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_change": "true"
    }
    data = requests.get(url, params=params, timeout=20).json()
    d = data[symbol]
    return float(d["usd"]), float(d["usd_market_cap"]), float(d["usd_24h_change"])

# ================= INDICATORS =================

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ================= BOT =================

send("🚀 Bot started. RSI 35/65 | TF 1H | CoinGecko only")

while True:
    try:
        for cg_id, symbol in SYMBOLS.items():

            price, cap, cap_ch = get_market(cg_id)
            df = get_ohlc(cg_id)
            if df is None:
                continue

            rsi_val = rsi(df["close"]).iloc[-1]
            atr_val = atr(df).iloc[-1]

            signal = None

            if rsi_val >= RSI_HIGH:
                signal = "SHORT"
                stop = price + atr_val
                tp1 = price - atr_val
                tp2 = price - 2 * atr_val

            elif rsi_val <= RSI_LOW:
                signal = "LONG"
                stop = price - atr_val
                tp1 = price + atr_val
                tp2 = price + 2 * atr_val

            if not signal:
                continue

            key = f"{symbol}_{signal}"
            if LAST_SIGNAL.get(key) == signal:
                continue
            LAST_SIGNAL[key] = signal

            risk = DEPOSIT * RISK_PERCENT / 100
            size = round(risk / abs(price - stop), 5)

            msg = f"""
{signal} | {symbol}

Price: {price}
RSI: {round(rsi_val,2)}
ATR: {round(atr_val,4)}

STOP: {round(stop,4)}
TP1: {round(tp1,4)}
TP2: {round(tp2,4)}

Size: {size}

Cap: {cap}
Cap 24h: {round(cap_ch,2)}%

UTC: {datetime.utcnow()}
"""
            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send(f"❌ ERROR: {e}")
        time.sleep(60)
