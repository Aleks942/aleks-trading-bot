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
            return None

        candles = data["data"]
        if not candles or len(candles) < 50:
            return None

        df = pd.DataFrame(candles, columns=[
            "time", "open", "high", "low", "close",
            "volume", "volCcy", "volCcyQuote", "confirm"
        ])

        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        df = df.iloc[::-1].reset_index(drop=True)
        return df

    except:
        return None

# ================== ANALYSIS ======================

def analyze_symbol(symbol="BTCUSDT", tf="1h"):
    df = get_ohlcv(symbol, tf)
    if df is None:
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

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.iloc[-1]

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(14).mean().iloc[-1]
    if atr is None or atr <= 0:
        return {"error": "no volatility"}

    atr_ratio = atr / last_close if last_close > 0 else 0

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

    if rsi > 60:
        score += 1
        reasons.append("RSI выше 60")
    elif rsi < 40:
        score -= 1
        reasons.append("RSI ниже 40")

    if volume_ratio > 1.3:
        score += 1
        reasons.append("Объём выше среднего")

    if atr_ratio < 0.003:
        score -= 1
        reasons.append("Флет")

    if score >= 3:
        signal = "LONG"
    elif score <= -3:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    risk_mult = 1.5
    entry = last_close

    sl = tp1 = tp2 = None
    if signal == "LONG":
        sl = entry - risk_mult * atr
        tp1 = entry + risk_mult * atr
        tp2 = entry + 2 * risk_mult * atr
    elif signal == "SHORT":
        sl = entry + risk_mult * atr
        tp1 = entry - risk_mult * atr
        tp2 = entry - 2 * risk_mult * atr

    return {
        "signal": signal,
        "strength": abs(score),
        "reasons": reasons,
        "entry": float(entry),
        "sl": float(sl) if sl else None,
        "tp1": float(tp1) if tp1 else None,
        "tp2": float(tp2) if tp2 else None,
        "atr": float(atr),
        "atr_ratio": float(atr_ratio),
        "rsi": float(rsi),
        "volume_ratio": float(volume_ratio),
    }

# ================== СТАТУС ВХОДА ======================

def entry_status(data):
    rsi = data["rsi"]
    atr_ratio = data["atr_ratio"]
    volume_ratio = data["volume_ratio"]

    if rsi >= 70 or rsi <= 30:
        return "❌ ОПАСНО — возможен разворот"

    if rsi > 60 or rsi < 40:
        return "⚠️ ПОЗДНО — ждать откат"

    if 40 <= rsi <= 55 and atr_ratio >= 0.003 and volume_ratio >= 1:
        return "✅ МОЖНО — вход от отката"

    return "⚠️ НЕОПРЕДЕЛЁННО"

# ================== COMMANDS ======================

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "✅ Бот онлайн\nИсточник: OKX\n\n"
        "/signal BTCUSDT 1h\n\n"
        "Авто-пары: BTC ETH SOL BNB STRK ZK NEAR 1INCH NOT"
    )

@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"

    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer("❌ Нет данных")
        return

    status = entry_status(data)

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"TF: {tf}\n\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила: <b>{data['strength']}</b>\n"
        f"Статус: <b>{status}</b>\n\n"
        f"Вход: {data['entry']:.4f}\n"
        f"SL: {data['sl']:.4f}\n"
        f"TP1: {data['tp1']:.4f}\n"
        f"TP2: {data['tp2']:.4f}\n\n"
        f"RSI: {data['rsi']:.1f}\n"
        f"ATR%: {data['atr_ratio']*100:.2f}%\n"
        f"VOL x: {data['volume_ratio']:.2f}\n\n"
        "Причины:\n" +
        "\n".join(f"- {r}" for r in data["reasons"])
    )

    await message.answer(text)

# ================== AUTO LOOP ======================

async def auto_loop():
    symbols = [
        "BTCUSDT", "ETHUSDT",
        "SOLUSDT", "BNBUSDT",
        "STRKUSDT", "ZKUSDT",
        "NEARUSDT", "1INCHUSDT", "NOTUSDT"
    ]

    tf = "1h"
    min_strength = 3
    min_atr_ratio = 0.003
    last_sent = {}

    while True:
        for symbol in symbols:
            data = analyze_symbol(symbol, tf)
            if "error" in data:
                continue

            if data["signal"] == "NEUTRAL":
                continue

            if data["strength"] < min_strength:
                continue

            if data["atr_ratio"] < min_atr_ratio:
                continue

            status = entry_status(data)
            if "ОПАСНО" in status:
                continue

            key = f"{symbol}_{data['signal']}"
            if key in last_sent:
                continue

            last_sent[key] = True
            color = "🟢" if data["signal"] == "LONG" else "🔴"

            text = (
                f"{color} <b>СИГНАЛ {symbol}</b>\n"
                f"TF: {tf}\n\n"
                f"Направление: {data['signal']}\n"
                f"Сила: {data['strength']}\n"
                f"Статус: {status}\n\n"
                f"Вход: {data['entry']:.4f}\n"
                f"SL: {data['sl']:.4f}\n"
                f"TP1: {data['tp1']:.4f}\n"
                f"TP2: {data['tp2']:.4f}\n"
            )

            await bot.send_message(CHAT_ID, text)

        await asyncio.sleep(900)

# ================== FASTAPI ======================

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(auto_loop())

@app.post("/webhook")
async def webhook(request: Request):
    update = Update(**await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "ok"}
