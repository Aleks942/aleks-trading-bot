import os
import time
import requests
import pandas as pd
from datetime import datetime

# ============================================================
# ENV (Railway Variables)
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise Exception("BOT_TOKEN or CHAT_ID not set in environment")

# ============================================================
# CONFIG
# ============================================================

INTERVAL = 3600  # 1H
DEPOSIT = 100
RISK_PERCENT = 1

RSI_LOW = 35
RSI_HIGH = 65

MIN_LIQUIDITY = 100_000
MIN_VOLUME = 250_000

FAKE_PUMP_ATR_MULT = 3

LAST_SIGNAL = {}

SYMBOLS = {
    # majors
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
    "loopring": "LRC",
}

# ============================================================
# TELEGRAM
# ============================================================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        },
        timeout=10
    )

# ============================================================
# DATA SOURCES
# ============================================================

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days=2"
    data = requests.get(url, timeout=10).json()
    if not isinstance(data, list) or len(data) < 30:
        return None
    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
    return df.tail(30)

def get_market(symbol):
    data = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{symbol}",
        timeout=10
    ).json()

    m = data.get("market_data", {})
    price = float(m["current_price"]["usd"])
    cap = float(m["market_cap"]["usd"])
    cap_ch = float(m["market_cap_change_percentage_24h"])
    return price, cap, cap_ch

def get_dex(symbol):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    data = requests.get(url, timeout=10).json()
    pairs = data.get("pairs", [])
    if not pairs:
        return None, None, None

    p = pairs[0]
    return (
        float(p["liquidity"]["usd"]),
        float(p["volume"]["h24"]),
        p["dexId"]
    )

# ============================================================
# INDICATORS
# ============================================================

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

# ============================================================
# RISK
# ============================================================

def calc_position(entry, stop):
    risk = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)
    if dist == 0:
        return 0
    return round(risk / dist, 5)

# ============================================================
# MAIN LOOP
# ============================================================

def run():
    send("🚀 Bot started\nStrategy: RSI 35/65 + EMA + ATR\nTF: 1H | DEX + CoinGecko")

    while True:
        try:
            for cg_id, symbol in SYMBOLS.items():

                price, cap, cap_ch = get_market(cg_id)
                df = get_ohlc(cg_id)
                if df is None:
                    continue

                df["ema20"] = ema(df["close"], 20)
                df["ema50"] = ema(df["close"], 50)
                df["rsi"] = rsi(df["close"])
                df["atr"] = atr(df)

                rsi_val = df["rsi"].iloc[-1]
                atr_val = df["atr"].iloc[-1]

                liq, vol, dex_name = get_dex(symbol)
                if not liq or liq < MIN_LIQUIDITY or not vol or vol < MIN_VOLUME:
                    continue

                # Anti fake pump
                prev_close = df["close"].iloc[-2]
                if abs(price - prev_close) > atr_val * FAKE_PUMP_ATR_MULT:
                    continue

                trend_long = df["ema20"].iloc[-1] > df["ema50"].iloc[-1]
                trend_short = df["ema20"].iloc[-1] < df["ema50"].iloc[-1]

                signal = None

                if rsi_val >= RSI_HIGH and trend_short:
                    signal = "SHORT"
                    stop = price + atr_val
                    tp1 = price - atr_val
                    tp2 = price - 2 * atr_val

                elif rsi_val <= RSI_LOW and trend_long:
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

                size = calc_position(price, stop)

                msg = f"""
<b>{signal} | {symbol}</b>

Price: {round(price,4)}
RSI: {round(rsi_val,2)}
ATR: {round(atr_val,4)}

STOP: {round(stop,4)}
TP1: {round(tp1,4)}
TP2: {round(tp2,4)}

Deposit: {DEPOSIT}$
Risk: {RISK_PERCENT}%
Position size: {size}

Cap: {cap}$
Cap 24h: {cap_ch}%

DEX: {dex_name}
Liquidity: {round(liq,2)}$
Volume 24h: {round(vol,2)}$

UTC: {datetime.utcnow()}
"""
                send(msg)

            time.sleep(INTERVAL)

        except Exception as e:
            send(f"❌ BOT ERROR: {str(e)}")
            time.sleep(60)

# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run()
