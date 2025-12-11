import requests
import time
import pandas as pd
from datetime import datetime

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

INTERVAL = 900     # 15 минут, не перегружает Dexter API
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
    "zksync":     {"ticker": "ZK",   "query": "zk"},
}

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ------------------ OHLC FROM DEX SCREENER ------------------

def get_ohlc_from_dex(symbol, tf="1h"):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    data = requests.get(url).json()

    if not data or "pairs" not in data or not data["pairs"]:
        return None, None, None

    pair = data["pairs"][0]

    # Liquidity & volume
    try:
        liq = float(pair["liquidity"]["usd"])
        vol = float(pair["volume"]["h24"])
    except:
        liq = None
        vol = None

    # Fetch OHLC candles
    # DexScreener candle endpoint:
    # /candles/{chain}/{pairId}?tf=1h
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

# ------------------ RSI ------------------

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    r = 100 - (100 / (1 + rs))
    return r.iloc[-1]

# ------------------ ATR ------------------

def atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

# ------------------ MARKET VIA CG ------------------

def get_market(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}"
    data = requests.get(url).json()
    price = float(data["market_data"]["current_price"]["usd"])
    cap = float(data["market_data"]["market_cap"]["usd"])
    cap_change = float(data["market_data"]["market_cap_change_percentage_24h"])
    return price, cap, cap_change

# ------------------ POSITION SIZE ------------------

def calc_position(entry, stop):
    risk = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)
    if dist == 0:
        return 0
    return round(risk / dist, 5)

# ---------------------------------------------------
# ------------------ MAIN LOOP ----------------------
# ---------------------------------------------------

send("Bot started. RSI 35/65 + ATR + Risk 1% + TP1/TP2 | TF = 1h + 15m | DexScreener + CoinGecko")

while True:
    try:
        for cg, rules in SYMBOLS.items():
            ticker = rules["ticker"]
            query = rules["query"]

            # ---- MARKET ----
            price, cap, cap_ch = get_market(cg)

            # ---- OHLC DEX ----
            df, liq, vol = get_ohlc_from_dex(query, tf="1h")
            if df is None or len(df) < 20:
                continue

            if liq is None or liq < 100000:
                continue

            rsi_val = rsi(df["close"])
            atr_val = atr(df)

            # --------- SIGNAL LOGIC ---------
            signal = None

            if rsi_val >= RSI_HIGH:
                signal = "SHORT"
                stop = price + atr_val
                tp1 = price - atr_val
                tp2 = price - atr_val * 2

            elif rsi_val <= RSI_LOW:
                signal = "LONG"
                stop = price - atr_val
                tp1 = price + atr_val
                tp2 = price + atr_val * 2

            if not signal:
                continue

            # --------- ANTI DUPLICATES ---------
            sig_key = f"{ticker}_{signal}"
            if LAST_SIGNAL.get(sig_key) == signal:
                continue
            LAST_SIGNAL[sig_key] = signal

            # --------- POSITION ---------
            size = calc_position(price, stop)

            # --------- SEND ---------
            msg = f"""
SIGNAL: {signal} | {ticker}

Price: {price}
RSI: {round(rsi_val,2)}
ATR: {round(atr_val,4)}

Entry: {price}
STOP: {round(stop,4)}
TP1: {round(tp1,4)}
TP2: {round(tp2,4)}

Risk: {RISK_PERCENT}%
Position size: {size}

Cap: {cap}
Cap 24h: {cap_ch}%
Liquidity: {liq}$
Volume 24h: {vol}$

TF: 1h (Dex OHLC)
Time: {datetime.utcnow()}
"""
            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send("BOT ERROR: " + str(e))
        time.sleep(60)
