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

# ================== ENV ==================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

# ================== BOT ==================

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================== DATA ==================

def get_ohlcv(symbol="BTCUSDT", tf="1h"):
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": tf, "limit": 200},
            timeout=10
        )
        data = r.json()
    except Exception as e:
        print("OHLCV REQUEST ERROR:", e)
        return None

    if not isinstance(data, list) or len(data) < 50:
        print("OHLCV EMPTY:", symbol, tf)
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
        print("DF PARSE ERROR:", e)
        return None

# ================== ANALYSIS ==================

def analyze_symbol(symbol="BTCUSDT", tf="1h"):
    df = get_ohlcv(symbol, tf)
    if df is None or len(df) < 50:
        return {"error": "Недостаточно данных"}

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
    else:
        reasons.append("RSI нейтрален")

    if volume_ratio > 1.2:
        score += 1
        reasons.append("Объём выше среднего")

    if score >= 3:
        signal = "LONG"
    elif score <= -3:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    return {
        "signal": signal,
        "strength": abs(score),
        "reasons": reasons
    }

# ================== COMMANDS ==================

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer("✅ Бот онлайн\nКоманды:\n/signal BTCUSDT 1h")

@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"

    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer(f"❌ Ошибка: {data['error']}")
        return

    text = (
        f"<b>Сигнал {symbol}</b>\nTF: {tf}\n\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила: <b>{data['strength']}</b>\n\n"
        "Причины:\n" + "\n".join(f"- {r}" for r in data["reasons"])
    )

    await message.answer(text)

# ================== AUTO LOOP ==================

async def auto_signal_loop():
    print("AUTO LOOP STARTED ✅")

    symbols = ["BTCUSDT", "ETHUSDT"]
    tf = "1h"
    htf = "4h"
    min_strength = 3

    last_sent = {}

    while True:
        print("AUTO LOOP TICK...")

        try:
            for symbol in symbols:
                ltf = analyze_symbol(symbol, tf)
                htf_data = analyze_symbol(symbol, htf)

                if "error" in ltf or "error" in htf_data:
                    continue

                if ltf["signal"] != htf_data["signal"]:
                    continue

                if ltf["strength"] < min_strength:
                    continue

                key = f"{symbol}_{ltf['signal']}"
                if key in last_sent:
                    continue

                last_sent[key] = True

                color = "🟢" if ltf["signal"] == "LONG" else "🔴"

                text = (
                    f"{color} <b>СИЛЬНЫЙ СИГНАЛ {symbol}</b>\n"
                    f"TF: {tf} | HTF: {htf}\n\n"
                    f"Направление: {ltf['signal']}\n"
                    f"Сила: {ltf['strength']}\n\n"
                    "Контекст:\n" +
                    "\n".join(f"- {r}" for r in ltf["reasons"])
                )

                print("SEND:", symbol, ltf["signal"])
                await bot.send_message(CHAT_ID, text)

            await asyncio.sleep(900)

        except Exception as e:
            print("AUTO LOOP ERROR:", e)
            await asyncio.sleep(30)

# ================== FASTAPI ==================

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

    asyncio.create_task(auto_signal_loop())

    try:
        await bot.send_message(CHAT_ID, "✅ Бот запущен. Автосигналы активны.")
    except Exception as e:
        print("START MESSAGE ERROR:", e)

@app.on_event("shutdown")
async def on_shutdown():
    print("SHUTDOWN OK")
    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}
@app.get("/")
async def health():
    return {"status": "ok"}
