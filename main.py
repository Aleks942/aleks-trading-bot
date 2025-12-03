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

# ================== OKX DATA SOURCE ======================

TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
}

def get_ohlcv(symbol="BTCUSDT", tf="1h"):
    try:
        inst = symbol.replace("USDT", "-USDT")
        bar = TF_MAP.get(tf, "1H")

        url = "https://www.okx.com/api/v5/market/candles"
        params = {
            "instId": inst,
            "bar": bar,
            "limit": 200
        }

        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if "data" not in data:
            print("OKX BAD RESPONSE:", data)
            return None

        candles = data["data"]

        df = pd.DataFrame(candles, columns=[
            "time", "open", "high", "low", "close",
            "volume", "volCcy", "volCcyQuote", "confirm"
        ])

        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        return df.iloc[::-1]

    except Exception as e:
        print("OKX ERROR:", e)
        return None

# ================== ANALYSIS ======================

def analyze_symbol(symbol="BTCUSDT", tf="1h"):
    df = get_ohlcv(symbol, tf)
    if df is None or len(df) < 50:
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

    if rsi > 55:
        score += 1
        reasons.append("RSI выше 55")
    elif rsi < 45:
        score -= 1
        reasons.append("RSI ниже 45")

    if volume_ratio > 1.2:
        score += 1
        reasons.append("Объём выше среднего")

    if score >= 2:
        signal = "LONG"
    elif score <= -2:
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
        await message.answer("❌ Нет данных с OKX")
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
    last_sent = ""

    while True:
        data = analyze_symbol("BTCUSDT", "1h")

        if "error" not in data:
            key = f"{data['signal']}_{data['strength']}"

            if key != last_sent and data["signal"] != "NEUTRAL":
                last_sent = key

                color = "🟢" if data["signal"] == "LONG" else "🔴"

                text = (
                    f"{color} <b>AUTO BTC SIGNAL</b>\n\n"
                    f"Направление: {data['signal']}\n"
                    f"Сила: {data['strength']}\n\n"
                    "Причины:\n" +
                    "\n".join(f"- {r}" for r in data["reasons"])
                )

                await bot.send_message(CHAT_ID, text)

        await asyncio.sleep(900)

# ================== FASTAPI ======================

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

    await bot.send_message(CHAT_ID, "✅ Бот запущен. Источник: OKX")
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
