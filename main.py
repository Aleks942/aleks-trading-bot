import requests
import time
import pandas as pd
from datetime import datetime

# ================== CONFIG ==================

BOT_TOKEN = "ВСТАВЬ_СЮДА_ТОКЕН"
CHAT_ID = "ВСТАВЬ_СЮДА_CHAT_ID"

INTERVAL = 3600  # 1H
DEPOSIT = 100
RISK_PERCENT = 1

RSI_LOW = 35
RSI_HIGH = 65

MIN_LIQUIDITY = 300_000

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

LAST_SIGNAL = {}

# ================== TELEGRAM ==================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ================== DATA ==================

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc"
    params = {"vs_currency": "usd", "days": 2}
    r = requests.get(url, params=params, timeout=10)

    if r.status_code != 200:
        return None

    data = r.json()
    if not isinstance(data, list) or len(data) < 30:
        return None

    df = pd.DataFrame(data, columns=["time","open","high","low","close"])
    return df.tail(30)

def get_price_from_dex(symbol):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    r = requests.get(url, timeout=10)
    data = r.json()

    if not data.get("pairs"):
        return None, None, None

    p = data["pairs"][0]
    return (
        float(p["priceUsd"]),
        float(p["liquidity"]["usd"]),
        p["dexId"]
    )

# ================== INDICATORS ==================

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

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# ================== RISK ==================

def position_size(entry, stop):
    risk = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)
    return round(risk / dist, 5) if dist > 0 else 0

# ================== BOT ==================

send("🚀 Bot started\nStrategy: RSI 35/65 + EMA + ATR\nTF: 1H | DEX + CoinGecko")

while True:
    try:
        for cg_id, symbol in SYMBOLS.items():

            df = get_ohlc(cg_id)
            if df is None:
                continue

            price, liquidity, dex_name = get_price_from_dex(symbol)
            if price is None or liquidity < MIN_LIQUIDITY:
                continue

            df["ema20"] = ema(df["close"], 20)
            df["ema50"] = ema(df["close"], 50)
            df["rsi"] = rsi(df["close"])
            df["atr"] = atr(df)

            rsi_val = df["rsi"].iloc[-1]
            atr_val = df["atr"].iloc[-1]

            signal = None

            if rsi_val >= RSI_HIGH and df["ema20"].iloc[-1] < df["ema50"].iloc[-1]:
                signal = "SHORT"
                stop = price + atr_val
                tp1 = price - atr_val
                tp2 = price - 2 * atr_val

            elif rsi_val <= RSI_LOW and df["ema20"].iloc[-1] > df["ema50"].iloc[-1]:
                signal = "LONG"
                stop = price - atr_val
                tp1 = price + atr_val
                tp2 = price + 2 * atr_val

            if not signal:
                continue

            key = f"{symbol}_{signal}"
            if LAST_SIGNAL.get(key):
                continue
            LAST_SIGNAL[key] = True

            size = position_size(price, stop)

            msg = f"""
SIGNAL: {signal} | {symbol}

Price: {round(price,4)}
RSI: {round(rsi_val,2)}
ATR: {round(atr_val,4)}

STOP: {round(stop,4)}
TP1: {round(tp1,4)}
TP2: {round(tp2,4)}

Position size: {size}

DEX: {dex_name}
Liquidity: {round(liquidity,2)}$

UTC: {datetime.utcnow()}
"""
            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send(f"❌ BOT ERROR: {str(e)}")
        time.sleep(60)
