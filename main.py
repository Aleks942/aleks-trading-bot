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

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================== TIMEFRAMES ======================

TF_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1H", "4h": "4H", "1d": "1D",
}

# ================== OKX DATA ======================

def get_ohlcv(symbol="BTCUSDT", tf="1h"):
    try:
        inst = symbol.replace("USDT", "-USDT")
        bar = TF_MAP.get(tf, "1H")

        url = "https://www.okx.com/api/v5/market/candles"
        params = {"instId": inst, "bar": bar, "limit": 200}

        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if "data" not in data:
            return None

        df = pd.DataFrame(data["data"], columns=[
            "time", "open", "high", "low", "close",
            "volume", "volCcy", "volCcyQuote", "confirm"
        ])

        df[["open", "high", "low", "close", "volume"]] = df[
            ["open", "high", "low", "close", "volume"]
        ].astype(float)

        df = df.iloc[::-1].reset_index(drop=True)
        return df

    except:
        return None

# ================== ANALYSIS ======================

def analyze_symbol(symbol="BTCUSDT", tf="1h"):
    df = get_ohlcv(symbol, tf)
    if df is None or len(df) < 50:
        return {"error": "no data"}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    last_close = close.iloc[-1]

    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    trend = "up" if ema20 > ema50 else "down"

    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    rsi = 100 - (100 / (1 + rs))
    rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(14).mean().iloc[-1]
    if atr is None or atr <= 0:
        return {"error": "no_volatility"}

    atr_ratio = atr / last_close if last_close else 0

    avg_vol = volume.rolling(20).mean().iloc[-2]
    last_vol = volume.iloc[-1]
    volume_ratio = last_vol / avg_vol if avg_vol else 1

    score = 0
    reasons = []

    if trend == "up":
        score += 1
        reasons.append("Тренд вверх")
    else:
        score -= 1
        reasons.append("Тренд вниз")

    if rsi > 60:
        score += 1
        reasons.append("RSI > 60")
    elif rsi < 40:
        score -= 1
        reasons.append("RSI < 40")

    if volume_ratio > 1.3:
        score += 1
        reasons.append("Объём высокий")
    elif volume_ratio < 0.7:
        score -= 1
        reasons.append("Объём слабый")

    if atr_ratio < 0.003:
        score -= 1
        reasons.append("Флет")

    if score >= 3:
        signal = "LONG"
    elif score <= -3:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    entry = float(last_close)
    sl = tp1 = tp2 = None

    if signal == "LONG":
        sl = entry - 1.5 * atr
        tp1 = entry + 1.5 * atr
        tp2 = entry + 3 * atr
    elif signal == "SHORT":
        sl = entry + 1.5 * atr
        tp1 = entry - 1.5 * atr
        tp2 = entry - 3 * atr

    return {
        "signal": signal,
        "strength": abs(score),
        "reasons": reasons,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "atr": float(atr),
        "atr_ratio": float(atr_ratio),
        "rsi": float(rsi),
        "volume_ratio": float(volume_ratio)
    }

# ================== BTC HEARTBEAT 15m ======================

async def btc_heartbeat():
    await asyncio.sleep(15)
    while True:
        try:
            data = analyze_symbol("BTCUSDT", "15m")

            if "error" in data:
                await asyncio.sleep(900)
                continue

            if data["signal"] == "LONG":
                mood = "🟢 Рынок под ЛОНГ"
            elif data["signal"] == "SHORT":
                mood = "🔴 Рынок под ШОРТ"
            else:
                mood = "⚪ Флет / ожидание"

            text = (
                f"⏱ <b>BTC контроль 15m</b>\n\n"
                f"{mood}\n\n"
                f"Сигнал: {data['signal']}\n"
                f"Сила: {data['strength']}\n\n"
                f"RSI: {round(data['rsi'],2)}\n"
                f"ATR: {round(data['atr_ratio']*100,2)}%\n"
                f"Объём: {round(data['volume_ratio'],2)}x\n\n"
                "Причины:\n" +
                "\n".join(f"- {r}" for r in data["reasons"])
            )

            await bot.send_message(CHAT_ID, text)

            await asyncio.sleep(900)

        except Exception as e:
            print("BTC HEARTBEAT ERROR:", e)
            await asyncio.sleep(60)

# ================== COMMAND ======================

@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"
    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer("❌ Нет данных")
        return

    levels = ""
    if data.get("sl") is not None:
        levels = (
            "Уровни:\n"
            f"- Вход: <b>{round(data['entry'], 6)}</b>\n"
            f"- SL: <b>{round(data['sl'], 6)}</b>\n"
            f"- TP1: <b>{round(data['tp1'], 6)}</b>\n"
            f"- TP2: <b>{round(data['tp2'], 6)}</b>\n\n"
        )

    extra = (
        f"ATR: {round(data['atr'], 6)} ({round(data['atr_ratio']*100,2)}%)\n"
        f"RSI: {round(data['rsi'],2)}\n"
        f"Объём: {round(data['volume_ratio'],2)}x\n\n"
    )

    text = (
        f"<b>Сигнал {symbol}</b>\nTF: {tf}\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила: <b>{data['strength']}</b>\n\n"
        f"{levels}{extra}"
        "Причины:\n" + "\n".join(f"- {r}" for r in data["reasons"])
    )

    await message.answer(text)

# ================== FASTAPI ======================

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("STARTUP ✅")

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

    asyncio.create_task(btc_heartbeat())

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "ok"}
