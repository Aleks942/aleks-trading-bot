import os
import asyncio
import requests
import pandas as pd
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.client.default import DefaultBotProperties

from fastapi import FastAPI, Request

# ================== ENV ======================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

# ================== BOT ======================

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================== BINANCE VIA PROXY =====================

PROXY_BASE = "https://round-moon-6916.aleks-aw1978.workers.dev"

def get_ohlcv(symbol="BTCUSDT", tf="1h"):
    tf_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d"
    }

    interval = tf_map.get(tf, "1h")

    url = PROXY_BASE + "/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": 200
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception as e:
        print("PROXY REQUEST ERROR:", e)
        return None

    if not isinstance(data, list):
        print("BINANCE VIA PROXY BAD RESPONSE:", data)
        return None

    if len(data) < 50:
        print("BINANCE VIA PROXY LITTLE DATA:", symbol, tf)
        return None

    try:
        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "_","_","_","_","_","_"
        ])
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return df

    except Exception as e:
        print("PROXY DF ERROR:", e)
        return None

# ================== ANALYSIS =================

def analyze_symbol(symbol="BTCUSDT", tf="1h"):
    df = get_ohlcv(symbol, tf)
    if df is None:
        return {"error": "no data"}

    close = df["close"]
    volume = df["volume"]

    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    trend = "up" if ema20 > ema50 else "down"

    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.iloc[-1]

    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    macd_hist = macd.iloc[-1]

    avg_vol = volume.rolling(20).mean().iloc[-2]
    last_vol = volume.iloc[-1]
    volume_ratio = last_vol / avg_vol if avg_vol > 0 else 1

    score = 0
    reasons = []

    if trend == "up":
        score += 1
        reasons.append("Тренд восходящий")
    else:
        score -= 1
        reasons.append("Тренд нисходящий")

    if macd_hist > 0:
        score += 1
        reasons.append("MACD бычий")
    else:
        score -= 1
        reasons.append("MACD медвежий")

    if rsi > 55:
        score += 1
        reasons.append("RSI выше 55")
    elif rsi < 45:
        score -= 1
        reasons.append("RSI ниже 45")

