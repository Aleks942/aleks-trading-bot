import requests
import time
from datetime import datetime
import pandas as pd
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

INTERVAL = 3600  # 1 ЧАС
RISK_PERCENT = 1
DEPOSIT = 100

RSI_LOW = 35
RSI_HIGH = 65

LAST_SIGNAL = {}

SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",

    # L2
    "arbitrum": "ARB",
    "optimism": "OP",
    "polygon": "MATIC",
    "immutable-x": "IMX",
    "starknet": "STRK",
    "zksync": "ZK",
    "metis-token": "METIS",
    "loopring": "LRC"
}


def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})


def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days=2"
    data = requests.get(url, timeout=20).json()

    if not isinstance(data, list) or len(data) < 20:
        return None

    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
    return df.tail(20)


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return true_range.rolling(period).mean()


def get_market(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}"
    data = requests.get(url, timeout=20).json()

    md = data.get("market_data")
    if not md:
        return None

    price = float(md["current_price"]["usd"])
    cap = float(md["market_cap"]["usd"])
    cap_change = float(md["market_cap_change_percentage_24h"])
    price_change = float(md["price_change_percentage_24h"])

    return price, cap, cap_change, price_change


def dex(symbol):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    data = requests.get(url, timeout=20).json()

    pairs = data.get("pairs")
    if not pairs:
        return None, None, None

    p = pairs[0]
    liq = float(p["liquidity"]["usd"])
    vol = float(p["volume"]["h24"])
    dex_name = p["dexId"]

    return liq, vol, dex_name


def calc_position(entry, stop):
    risk = DEPOSIT * RISK_PERCENT / 100
    distance = abs(entry - stop)

    if distance == 0:
        return 0

    size = risk / distance
    return round(size, 5)


send("Bot started. Strategy: RSI 35/65 + Risk 1% + TP1/TP2 | TF = 1H | DEX + CoinGecko")

while True:
    try:
        for cg_id, symbol in SYMBOLS.items():

            market = get_market(cg_id)
            if not market:
                continue

            price, cap, cap_ch, price_ch = market

            df = get_ohlc(cg_id)
            if df is None:
                continue

            rsi_series = rsi(df["close"])
            atr_series = atr(df)

            if len(rsi_series.dropna()) == 0 or len(atr_series.dropna()) == 0:
                continue

            rsi_val = float(rsi_series.iloc[-1])
            atr_val = float(atr_series.iloc[-1])

            if atr_val == 0:
                continue

            liq, vol, dex_name = dex(symbol)
            if not liq or liq < 100000:
                continue

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

            key = f"{symbol}_{signal}"
            last_price = LAST_SIGNAL.get(key)

            if last_price and abs(last_price - price) < atr_val:
                continue

            LAST_SIGNAL[key] = price

            size = calc_position(price, stop)

            msg = f"""
SIGNAL: {signal} | {symbol}

Price: {round(price, 4)}
RSI: {round(rsi_val, 2)}
ATR: {round(atr_val, 5)}

Entry: {round(price, 4)}
STOP: {round(stop, 4)}
TP1: {round(tp1, 4)}
TP2: {round(tp2, 4)}

Deposit: {DEPOSIT}$
Risk: {RISK_PERCENT}%
Position size: {size}

Cap: {int(cap)}$
Cap 24h: {round(cap_ch, 2)}%

DEX: {dex_name}
Liquidity: {int(liq)}$
Volume 24h: {int(vol)}$

Time UTC: {datetime.utcnow()}
"""
            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send(f"BOT ERROR: {str(e)}")
        time.sleep(120)
