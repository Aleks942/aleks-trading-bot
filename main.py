import requests
import time
import pandas as pd
from datetime import datetime

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

INTERVAL = 3600  # 1 час
RISK_PERCENT = 1
DEPOSIT = 100

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
    "metis-token": "METIS",
    "loopring": "LRC"
}


# =====================================================================
#  Telegram Sender
# =====================================================================
def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg})
    except:
        pass


# =====================================================================
#   OHLC from CoinGecko
# =====================================================================
def get_ohlc(symbol):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days=2"
        data = requests.get(url, timeout=10).json()

        if not isinstance(data, list) or len(data) < 20:
            return None  # недостаточно данных

        df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
        return df.tail(20)

    except Exception:
        return None


# =====================================================================
#   Indicators
# =====================================================================
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


# =====================================================================
#   Market Info (CoinGecko)
# =====================================================================
def get_market(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}"
    data = requests.get(url).json()

    price = float(data["market_data"]["current_price"]["usd"])
    cap = float(data["market_data"]["market_cap"]["usd"])
    cap_change = float(data["market_data"]["market_cap_change_percentage_24h"])

    return price, cap, cap_change


# =====================================================================
#   Dex Info
# =====================================================================
def dex(symbol):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
        data = requests.get(url, timeout=10).json()

        if not data.get("pairs"):
            return None, None, None

        p = data["pairs"][0]
        return (
            float(p["liquidity"]["usd"]),
            float(p["volume"]["h24"]),
            p["dexId"]
        )

    except:
        return None, None, None


# =====================================================================
#   Position calculator
# =====================================================================
def calc_position(entry, stop):
    risk = DEPOSIT * RISK_PERCENT / 100
    dist = abs(entry - stop)

    if dist == 0:
        return 0

    size = risk / dist
    return round(size, 5)


# =====================================================================
#   Start Message
# =====================================================================
send("Bot started. Strategy: RSI 35/65 + Risk 1% + TP1/TP2 | TF = 1H | DEX + CoinGecko")


# =====================================================================
#   MAIN LOOP
# =====================================================================
while True:
    try:
        for cg_id, symbol in SYMBOLS.items():

            # === Market Data ===
            price, cap, cap_ch = get_market(cg_id)

            # === OHLC Data ===
            df = get_ohlc(cg_id)
            if df is None:
                continue

            rsi_val = rsi(df["close"]).iloc[-1]
            atr_val = atr(df).iloc[-1]

            if pd.isna(rsi_val) or pd.isna(atr_val):
                continue

            # === DEX Data ===
            liq, vol, dex_name = dex(symbol)
            if liq is None or liq < 100000:
                continue

            # === SIGNAL LOGIC ===
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

            # === Anti-duplicate ===
            key = f"{symbol}_{signal}"
            if LAST_SIGNAL.get(key) == signal:
                continue
            LAST_SIGNAL[key] = signal

            # === Position size ===
            size = calc_position(price, stop)

            # === MESSAGE ===
            msg = f"""
SIGNAL: {signal} | {symbol}

Price: {price}
RSI: {round(rsi_val,2)}
ATR: {round(atr_val,4)}

Entry: {price}
STOP: {round(stop,4)}
TP1: {round(tp1,4)}
TP2: {round(tp2,4)}

Deposit: {DEPOSIT}$
Risk: {RISK_PERCENT}%
Position size: {size}

Cap: {cap}$
Cap 24h: {cap_ch}%

DEX: {dex_name}
Liquidity: {liq}$
Volume 24h: {vol}$

Time UTC: {datetime.utcnow()}
"""

            send(msg)

        time.sleep(INTERVAL)

    except Exception as e:
        send(f"BOT ERROR: {str(e)}")
        time.sleep(60)
