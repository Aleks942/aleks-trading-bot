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

# ================== PROXY (COINGECKO) ======================
PROXY_BASE = "https://round-moon-6916.aleks-aw1978.workers.dev"

SYMBOL_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum"
}

def get_ohlcv(symbol="BTCUSDT", tf="1h"):
    coin = SYMBOL_MAP.get(symbol.upper())
    if not coin:
        print("UNKNOWN SYMBOL:", symbol)
        return None

    url = f"{PROXY_BASE}/?symbol={coin}&days=2"

    try:
        r = requests.get(url, timeout=15)
        data = r.json()
    except Exception as e:
        print("PROXY REQUEST ERROR:", e)
        return None

    if "prices" not in data or "total_volumes" not in data:
        print("BAD PROXY DATA:", data)
        return None

    try:
        prices = data["prices"]
        volumes = data["total_volumes"]

        df = pd.DataFrame({
            "close": [p[1] for p in prices],
            "volume": [v[1] for v in volumes]
        })

        return df

    except Exception as e:
        print("DF PARSE ERROR:", e)
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
    symbols = ["BTCUSDT", "ETHUSDT"]
    min_strength = 3
    last_sent = {}

    while True:
        try:
            for symbol in symbols:
                data = analyze_symbol(symbol, "1h")

                if "error" in data:
                    continue

                if data["strength"] < min_strength:
                    continue

                key = f"{symbol}_{data['signal']}"
                if key in last_sent:
                    continue

                last_sent[key] = True

                color = "🟢" if data["signal"] == "LONG" else "🔴"

                text = (
                    f"{color} <b>СИЛЬНЫЙ СИГНАЛ {symbol}</b>\n\n"
                    f"Направление: {data['signal']}\n"
                    f"Сила: {data['strength']}\n\n"
                    "Контекст:\n" +
                    "\n".join(f"- {r}" for r in data["reasons"])
                )

                await bot.send_message(CHAT_ID, text)

            await asyncio.sleep(900)

        except Exception as e:
            print("AUTO LOOP ERROR:", e)
            await asyncio.sleep(30)

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
