import requests
import time
import pandas as pd
from datetime import datetime

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

INTERVAL = 900     # 15 минут
DEPOSIT = 100
RISK_PERCENT = 1

RSI_LOW = 35
RSI_HIGH = 65

LAST_SIGNAL = {}

SYMBOLS = {
    "bitcoin":    {"ticker": "BTC",  "query": "btc"},
    "ethereum":   {"ticker": "ETH",  "query": "eth"},
    "solana":     {"ticker": "SOL",  "query": "sol"},
    "arbitrum":   {"ticker": "ARB",  "query": "arb"},
    "optimism":   {"ticker": "OP",   "query": "op"},
    "polygon":    {"ticker": "MATIC","query": "matic"},
    "immutable-x":{"ticker": "IMX",  "query": "imx"},
    "starknet":   {"ticker": "STRK", "query": "strk"},
    "zksync":     {"ticker": "ZK",   "query": "zk"}
}

def send(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg})
    except:
        pass


# ---------- OHLC DEX ----------
def get_ohlc_from_dex(symbol, tf="1h"):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    data = requests.get(url).json()

    if not data or "pairs" not in data or not data["pairs"]:
        return None, None, None

    pair = data["pairs"][0]

    try:
        liq = float(pair["liquidity"]["usd"])
        vol = float(pair["volume"]["h24"])
    except:
        liq = None
        vol = None

    chain = pair["chainId"]
    pair_id = pair["pairAddress"]

    candles_url = f"https://api.dexscreener.com/latest/dex/candles/{chain}/{pair_id}?tf={tf}"
    cdata = requests.get(candles_url).json()

    if "candles" not in cdata:
        return None, liq, vol

    df = pd.DataFrame(cdata["candles"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df, liq, vol


# ---------- INDICATORS ----------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return (100 - (100 / (1 + rs))).iloc[-1]

def atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean().iloc[-1]


# ---------- MARKET DATA ----------
def get_market(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}"
    data = requests.get(url).json()
    price = float(data["market_data"]["current_price"]["usd"])
    cap = float(data["market_data"]["market_cap"]["usd"])
    cap_change = float(data["market_data"]["market_cap_change_percentage_24h"])
    return price, cap, cap_change


# ---------- POSITION SIZE ----------
def calc_position(entry, stop):
    risk = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)
    if dist == 0:
        return 0
    return round(risk / dist, 5)


# ---------- START MESSAGE ----------
send("Bot started. 1h+15m + RSI 35/65 + EMA50/200 Trend Filter + ATR + TP1/TP2")


# ============================================================
# ========================= MAIN LOOP =========================
# ============================================================

while True:
    try:
        for cg, rules in SYMBOLS.items():
            ticker = rules["ticker"]
            query = rules["query"]

            price, cap, cap_ch = get_market(cg)

            # ----------------- 1H OHLC -----------------
            df1h, liq, vol = get_ohlc_from_dex(query, tf="1h")
            if df1h is None or len(df1h) < 50:
                continue

            if liq is None or liq < 100000:
                continue

            rsi1h = rsi(df1h["close"])
            atr1h = atr(df1h)
            ema50 = ema(df1h["close"], 50)
            ema200 = ema(df1h["close"], 200)

            # ----------------- 15M OHLC -----------------
            df15, _, _ = get_ohlc_from_dex(query, tf="15m")
            if df15 is None or len(df15) < 50:
                continue

            rsi15 = rsi(df15["close"])

            # ----------------- TREND -----------------
            trend = "UP" if ema50 > ema200 else "DOWN"

            # ----------------- SIGNAL -----------------
            signal = None

            # LONG logic
            if rsi1h <= RSI_LOW and rsi15 <= RSI_LOW and trend == "UP":
                signal = "LONG"
                stop = price - atr1h
                tp1 = price + atr1h
                tp2 = price + atr1h * 2

            # SHORT logic
            if rsi1h >= RSI_HIGH and rsi15 >= RSI_HIGH and trend == "DOWN":
                signal = "SHORT"
                stop = price + atr1h
                tp1 = price - atr1h
                tp2 = price - atr1h * 2

            if not signal:
                continue

            sig_key = f"{ticker}_{signal}"
            if LAST_SIGNAL.get(sig_key) == signal:
                continue
            LAST_SIGNAL[sig_key] = signal

            size = calc_position(price, stop)

            msg = f"""
SIGNAL: {signal} | {ticker}

Price: {price}
RSI H1: {round(rsi1h,2)}
RSI 15m: {round(rsi15,2)}
ATR H1: {round(atr1h,4)}

Trend: {trend}
EMA50: {round(ema50,2)}
EMA200: {round(ema200,2)}

Entry: {price}
STOP: {round(stop,4)}
TP1: {round(tp1,4)}
TP2: {round(tp2,4)}

Position size: {size}
Liquidity: {liq}$
Volume: {vol}$

Cap: {cap}
Cap 24h: {cap_ch}%

Time: {datetime.utcnow()}
"""

            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send("BOT ERROR: " + str(e))
        time.sleep(60)
