import requests
import time
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify
import threading
import matplotlib.pyplot as plt
import io

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

INTERVAL = 3600  # таймфрейм 1 час
RISK_PERCENT = 1
DEPOSIT = 100

RSI_LOW = 35
RSI_HIGH = 65

VOL_FILTER = 500000  # минимальный объём с Dex
FAKE_PUMP_LIMIT = 0.03  # 3% рост за час
FAKE_VOLUME_FACTOR = 2  # рост объёма в 2 раза

LAST_SIGNAL = {}
LAST_STATUS = {}

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

def send_photo(img_bytes):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {"photo": img_bytes}
    requests.post(url, data={"chat_id": CHAT_ID}, files=files)

# ============================================================
# DATA SOURCES
# ============================================================

def get_ohlc(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days=2"
    data = requests.get(url).json()
    if not isinstance(data, list) or len(data) < 50:
        return None
    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
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
# GRAPH GENERATOR
# ============================================================

def make_chart(df, symbol):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)

    # Price + EMA
    ax1.plot(df["close"], label="Close")
    ax1.plot(df["ema20"], label="EMA20")
    ax1.plot(df["ema50"], label="EMA50")
    ax1.set_title(f"{symbol} Price Chart")
    ax1.legend()

    # RSI
    ax2.plot(df["rsi"], label="RSI", color="purple")
    ax2.axhline(35, color="green", linestyle="--")
    ax2.axhline(65, color="red", linestyle="--")
    ax2.legend()

    img = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img, format="png")
    img.seek(0)
    plt.close()
    return img

# ============================================================
# BOT LOGIC
# ============================================================

def bot_loop():
    send("🚀 Bot started with GRAPH + ANTI-FAKE-PUMP")

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

                # ==========================
                # ANTI-FAKE-PUMP FILTER
                # ==========================
                price_prev = df["close"].iloc[-2]
                price_change = (price - price_prev) / price_prev

                avg_vol = vol / 24  # условное среднее

                fake_pump = (
                        price_change > FAKE_PUMP_LIMIT or
                        vol > avg_vol * FAKE_VOLUME_FACTOR or
                        abs(price - price_prev) > atr_val * 3
                )

                if fake_pump:
                    send(f"⚠️ Fake Pump detected! Signal for {symbol} blocked.")
                    continue

                # ==========================
                # TREND FILTER
                # ==========================

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

                # avoid duplicates
                key = f"{symbol}_{signal}"
                if LAST_SIGNAL.get(key) == signal:
                    continue
                LAST_SIGNAL[key] = signal

                # position size
                size = calc_position(price, stop)

                color = "🟩" if signal == "LONG" else "🟥"

                msg = f"""
{color} <b>{signal} | {symbol}</b>

<b>Price:</b> {price}
<b>RSI:</b> {round(rsi_val,2)}
<b>ATR:</b> {round(atr_val,4)}

<b>STOP:</b> {round(stop,4)}
<b>TP1:</b> {round(tp1,4)}
<b>TP2:</b> {round(tp2,4)}

<b>Size:</b> {size}
<b>Cap:</b> {cap}$
<b>Cap 24h:</b> {cap_ch}%

<b>DEX:</b> {dex_name}
<b>Vol 24h:</b> {vol}$

⏱ UTC: {datetime.utcnow()}
"""

                send(msg)

                # send chart
                img = make_chart(df, symbol)
                send_photo(img)

            time.sleep(INTERVAL)

        except Exception as e:
            send(f"❌ BOT ERROR: {str(e)}")
            time.sleep(30)

# ============================================================
# SIMPLE WEB STATUS
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "RUNNING", "time": str(datetime.utcnow())})

def web_thread():
    app.run(host="0.0.0.0", port=8000)

# ============================================================
# RUN
# ============================================================

threading.Thread(target=web_thread).start()
threading.Thread(target=bot_loop).start()
