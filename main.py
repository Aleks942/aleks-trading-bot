import requests
import time
import pandas as pd
from datetime import datetime

# ================== CONFIG ==================

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

INTERVAL = 3600  # 1 HOUR
DEPOSIT = 100
RISK_PERCENT = 1

RSI_LOW = 35
RSI_HIGH = 65

MIN_LIQ = 100_000
MIN_VOL = 250_000

LAST_SIGNAL = {}

SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",

    # L2
    "arbitrum": "ARB",
    "optimism": "OP",
    "polygon": "MATIC",
    "immutable-x": "IMX",
    "starknet": "STRK",
    "loopring": "LRC",
    "metis-token": "METIS"
}

# ================== TELEGRAM ==================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg
    })

# ================== DATA ==================

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc"
    params = {"vs_currency": "usd", "days": 2}
    r = requests.get(url, params=params).json()

    if not isinstance(r, list) or len(r) < 20:
        return None

    df = pd.DataFrame(r, columns=["time", "open", "high", "low", "close"])
    return df.tail(50)

def get_market(symbol):
    r = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{symbol}",
        params={"localization": "false"}
    ).json()

    md = r.get("market_data")
    if not md:
        return None

    price = md["current_price"]["usd"]
    cap = md["market_cap"]["usd"]
    cap_ch = md["market_cap_change_percentage_24h"]

    return price, cap, cap_ch

def get_dex(symbol):
    r = requests.get(
        f"https://api.dexscreener.com/latest/dex/search",
        params={"q": symbol}
    ).json()

    pairs = r.get("pairs")
    if not pairs:
        return None, None, None

    p = pairs[0]
    return (
        float(p["liquidity"]["usd"]),
        float(p["volume"]["h24"]),
        p["dexId"]
    )

# ================== INDICATORS ==================

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# ================== RISK ==================

def position_size(entry, stop):
    risk_usd = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)
    return round(risk_usd / dist, 5) if dist > 0 else 0

# ================== BOT ==================

send("🚀 Bot started\nTF: 1H\nRSI 35/65 + EMA + ATR\nDEX + CoinGecko")

while True:
    try:
        for cg_id, symbol in SYMBOLS.items():

            market = get_market(cg_id)
            if not market:
                continue

            price, cap, cap_ch = market

            df = get_ohlc(cg_id)
            if df is None:
                continue

            df["rsi"] = rsi(df["close"])
            df["atr"] = atr(df)
            df["ema20"] = ema(df["close"], 20)
            df["ema50"] = ema(df["close"], 50)

            rsi_val = df["rsi"].iloc[-1]
            atr_val = df["atr"].iloc[-1]

            liq, vol, dex_name = get_dex(symbol)
            if not liq or liq < MIN_LIQ or vol < MIN_VOL:
                continue

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
            if LAST_SIGNAL.get(key) == price:
                continue
            LAST_SIGNAL[key] = price

            size = position_size(price, stop)

            msg = (
                f"{signal} | {symbol}\n\n"
                f"Price: {price}\n"
                f"RSI: {round(rsi_val,2)}\n"
                f"ATR: {round(atr_val,4)}\n\n"
                f"STOP: {round(stop,4)}\n"
                f"TP1: {round(tp1,4)}\n"
                f"TP2: {round(tp2,4)}\n\n"
                f"Size: {size}\n\n"
                f"Cap: {cap}$\n"
                f"Cap 24h: {cap_ch}%\n"
                f"DEX: {dex_name}\n"
                f"Liquidity: {liq}$\n"
                f"Volume 24h: {vol}$\n\n"
                f"UTC: {datetime.utcnow()}"
            )

            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send(f"ERROR: {e}")
        time.sleep(60)
