import requests
import time
import pandas as pd
from datetime import datetime

# =========================
# CONFIG
# =========================

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

INTERVAL = 3600  # 1H
DEPOSIT = 100
RISK_PERCENT = 1

RSI_LOW = 35
RSI_HIGH = 65

MIN_LIQUIDITY = 100_000
MIN_VOLUME = 250_000

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
    "metis-token": "METIS",
    "loopring": "LRC"
}

# =========================
# TELEGRAM
# =========================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# =========================
# DATA
# =========================

def get_market(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}"
    data = requests.get(url, timeout=20).json()
    md = data.get("market_data", {})

    price = md.get("current_price", {}).get("usd")
    cap = md.get("market_cap", {}).get("usd")
    cap_ch = md.get("market_cap_change_percentage_24h")

    if price is None or cap is None:
        return None

    return float(price), float(cap), float(cap_ch or 0)

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days=2"
    data = requests.get(url, timeout=20).json()

    if not isinstance(data, list) or len(data) < 30:
        return None

    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
    return df.tail(30)

def dex(symbol):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    data = requests.get(url, timeout=20).json()

    pairs = data.get("pairs", [])
    if not pairs:
        return None

    p = pairs[0]
    liq = float(p.get("liquidity", {}).get("usd", 0))
    vol = float(p.get("volume", {}).get("h24", 0))
    dex_name = p.get("dexId", "unknown")

    return liq, vol, dex_name

# =========================
# INDICATORS
# =========================

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# =========================
# RISK
# =========================

def position_size(entry, stop):
    risk_usd = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)
    if dist == 0:
        return 0
    return round(risk_usd / dist, 6)

# =========================
# START
# =========================

send("🚀 Bot started\nStrategy: RSI 35/65 + EMA50 + ATR\nTF: 1H | DEX + CoinGecko")

while True:
    try:
        for cg_id, symbol in SYMBOLS.items():

            market = get_market(cg_id)
            if market is None:
                continue

            price, cap, cap_ch = market

            df = get_ohlc(cg_id)
            if df is None:
                continue

            df["ema50"] = ema(df["close"], 50)
            df["rsi"] = rsi(df["close"])
            df["atr"] = atr(df)

            rsi_val = df["rsi"].iloc[-1]
            atr_val = df["atr"].iloc[-1]
            ema50 = df["ema50"].iloc[-1]

            liq_data = dex(symbol)
            if liq_data is None:
                continue

            liq, vol, dex_name = liq_data
            if liq < MIN_LIQUIDITY or vol < MIN_VOLUME:
                continue

            signal = None

            if rsi_val >= RSI_HIGH and price < ema50:
                signal = "SHORT"
                stop = price + atr_val
                tp1 = price - atr_val
                tp2 = price - atr_val * 2

            elif rsi_val <= RSI_LOW and price > ema50:
                signal = "LONG"
                stop = price - atr_val
                tp1 = price + atr_val
                tp2 = price + atr_val * 2

            if not signal:
                continue

            key = f"{symbol}_{signal}"
            if LAST_SIGNAL.get(key) == signal:
                continue
            LAST_SIGNAL[key] = signal

            size = position_size(price, stop)

            msg = (
                f"{signal} | {symbol}\n\n"
                f"Price: {round(price,4)}\n"
                f"RSI: {round(rsi_val,2)}\n"
                f"ATR: {round(atr_val,4)}\n\n"
                f"STOP: {round(stop,4)}\n"
                f"TP1: {round(tp1,4)}\n"
                f"TP2: {round(tp2,4)}\n\n"
                f"Risk: {RISK_PERCENT}% | Size: {size}\n\n"
                f"Cap: {int(cap)}$\n"
                f"Cap 24h: {round(cap_ch,2)}%\n"
                f"DEX: {dex_name}\n"
                f"Liq: {int(liq)}$ | Vol 24h: {int(vol)}$\n\n"
                f"UTC: {datetime.utcnow()}"
            )

            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send(f"❌ BOT ERROR: {e}")
        time.sleep(60)
