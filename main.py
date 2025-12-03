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

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "_","_","_","_","_","_"
    ])
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

# ================== ANALYSIS ======================

def analyze_symbol(symbol="BTCUSDT", tf="1h"):
    df = get_ohlcv(symbol, tf)
    if df is None:
        return {"error": "no data"}

    close = df["close"]
    volume = df["volume"]

    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    trend = "up" if ema20 > ema50 else "down"

    score = 0
    reasons = []

    if trend == "up":
        score += 1
        reasons.append("Тренд восходящий")
    else:
        score -= 1
        reasons.append("Тренд нисходящий")

    if score >= 1:
        signal = "LONG"
    elif score <= -1:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    return {
        "signal": signal,
        "strength": abs(score),
        "reasons": reasons
    }

# ================== COMMANDS ======================

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer("✅ Бот онлайн\nКоманда:\n/signal BTCUSDT 1h")

@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"

    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer("❌ Нет данных")
        return

    text = (
        f"<b>Сигнал {symbol}</b>\nTF: {tf}\n\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила: <b>{data['strength']}</b>\n\n"
        "Причины:\n" + "\n".join(f"- {r}" for r in data["reasons"])
    )

    await message.answer(text)

# ================== AUTO LOOP ======================

async def auto_loop():
    print("AUTO LOOP STARTED ✅")
    while True:
        data = analyze_symbol("BTCUSDT", "1h")
        if "error" not in data:
            print("AUTO:", data)
        await asyncio.sleep(900)

# ================== FASTAPI APP ======================

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("STARTUP OK ✅")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL)
        print("WEBHOOK SET ✅")
    except Exception as e:
        print("WEBHOOK ERROR:", e)

    asyncio.create_task(auto_loop())

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "ok"}
