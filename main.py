import requests
import time
import pandas as pd
from datetime import datetime
import threading

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

INTERVAL = 3600  # 1h timeframe
RISK_PERCENT = 1
DEPOSIT = 100

RSI_LOW = 35
RSI_HIGH = 65

VOL_FILTER = 500000
FAKE_PUMP_LIMIT = 0.03
FAKE_VOLUME_FACTOR = 2

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
    "metis-token": "METIS",
    "loopring": "LRC"
}

# ============================================================
# TELEGRAM
# ============================================================

def send(msg, parse="HTML"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": parse})

# ============================================================
# DATA
# ============================================================

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days=2"
    data = requests.get(url).json()
    if not isinstance(data, list) or len(data) < 50:
        return None
    df = pd.DataFrame(data, columns=["time","open","high","low","close"])
    return df.tail(50)

def get_market(symbol):
    data = requests.get(f"https://api.coingecko.com/api/v3/coins/{symbol}").json()
    price = float(data["market_data"]["current_price"]["usd"])
    cap = float(data["market_data"]["market_cap"]["usd"])
    cap_change = float(data["market_data"]["market_cap_change_percentage_24h"])
    return price, cap, cap_change

def dex(symbol):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    data = requests.get(url).json()
    if not data.get("pairs"):
        return None, None, None
    p = data["pairs"][0]
    return float(p["liquidity"]["usd"]), float(p["volume"]["h24"]), p["dexId"]

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
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# ============================================================
# RISK
# ============================================================

def calc_position(entry, stop):
    risk = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)
    return round(risk / dist, 5) if dist > 0 else 0

# ============================================================
# BOT LOOP
# ============================================================

def bot_loop():
    send("🚀 Bot started. RSI+EMA+ATR + AntiFakePump + L2 tokens")

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

                liq, vol, dex_name = dex(symbol)
                if vol is None or vol < VOL_FILTER:
                    continue

                rsi_val = df["rsi"].iloc[-1]
                atr_val = df["atr"].iloc[-1]

                # Anti Fake Pump
                price_prev = df["close"].iloc[-2]
                price_ch = (price - price_prev) / price_prev

                fake = (
                    price_ch > FAKE_PUMP_LIMIT or
                    abs(price - price_prev) > atr_val * 3
                )

                if fake:
                    send(f"⚠️ Fake Pump detected: {symbol}. Signal blocked.")
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
                if LAST_SIGNAL.get(key) == signal:
                    continue
                LAST_SIGNAL[key] = signal

                size = calc_position(price, stop)

                msg = f"""
<b>{signal} | {symbol}</b>

Price: {price}
RSI: {round(rsi_val,2)}
ATR: {round(atr_val,4)}

STOP: {round(stop,4)}
TP1: {round(tp1,4)}
TP2: {round(tp2,4)}

Size: {size}

Cap: {cap}$
Cap 24h: {cap_ch}%

DEX: {dex_name}
Vol24h: {vol}$

UTC: {datetime.utcnow()}
"""
                send(msg)

            time.sleep(INTERVAL)

        except Exception as e:
            send(f"❌ ERROR: {str(e)}")
            time.sleep(30)


threading.Thread(target=bot_loop).start()
