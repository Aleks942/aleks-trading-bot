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

def get_ohlcv(symbol: str = "BTCUSDT", tf: str = "1h"):
    """
    Берём свечи с OKX: instId = BTC-USDT, ETH-USDT и т.п.
    Возвращаем DataFrame с колонками: time, open, high, low, close, volume.
    """
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
        if not candles or len(candles) < 50:
            print("OKX LITTLE DATA:", symbol, tf, len(candles))
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

        # OKX отдаёт от последней к первой, разворачиваем
        df = df.iloc[::-1].reset_index(drop=True)

        return df

    except Exception as e:
        print("OKX ERROR:", e)
        return None

# ================== ANALYSIS ======================

def analyze_symbol(symbol: str = "BTCUSDT", tf: str = "1h"):
    df = get_ohlcv(symbol, tf)
    if df is None or len(df) < 50:
        return {"error": "no data"}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    last_close = close.iloc[-1]

    # -------- ТРЕНД (EMA20 / EMA50) --------
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    trend = "up" if ema20 > ema50 else "down"

    # -------- RSI 14 --------
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))
    rsi = rsi_series.iloc[-1]

    # если RSI ещё не посчитался по окну — нейтраль
    if pd.isna(rsi):
        rsi = 50.0

    # -------- ATR 14 --------
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_series = tr.rolling(14).mean()
    atr = atr_series.iloc[-1]

    if pd.isna(atr) or atr <= 0:
        return {"error": "no_volatility"}

    atr_ratio = atr / last_close if last_close > 0 else 0.0  # относительная волатильность

    # -------- ОБЪЁМ --------
    avg_vol = volume.rolling(20).mean().iloc[-2]
    last_vol = volume.iloc[-1]
    volume_ratio = last_vol / avg_vol if avg_vol > 0 else 1

    # -------- СКОРАЯ ОЦЕНКА (score) --------
    score = 0
    reasons = []

    # тренд
    if trend == "up":
        score += 1
        reasons.append("Тренд восходящий (EMA20 > EMA50)")
    else:
        score -= 1
        reasons.append("Тренд нисходящий (EMA20 < EMA50)")

    # RSI
    if rsi > 60:
        score += 1
        reasons.append("RSI выше 60 (сильные покупатели)")
    elif rsi < 40:
        score -= 1
        reasons.append("RSI ниже 40 (сильные продавцы)")
    else:
        reasons.append("RSI в балансе")

    # объём
    if volume_ratio > 1.3:
        score += 1
        reasons.append("Объём значительно выше среднего")
    elif volume_ratio < 0.7:
        score -= 1
        reasons.append("Объём ниже среднего (интерес слабый)")

    # волатильность (анти-флет)
    if atr_ratio < 0.003:
        # очень узкий диапазон (<0.3%)
        reasons.append("Волатильность очень низкая (флет)")
        # зафлэченный рынок — штрафуем
        score -= 1
    else:
        reasons.append(f"Волатильность достаточная (ATR ≈ {atr_ratio*100:.2f}% от цены)")

    # -------- ИТОГОВЫЙ СИГНАЛ --------
    if score >= 3:
        signal = "LONG"
    elif score <= -3:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    strength = abs(score)

    # -------- РАСЧЁТ УРОВНЕЙ (ENTRY / SL / TP) --------
    risk_mult = 1.5  # множитель ATR
    entry = last_close

    sl = None
    tp1 = None
    tp2 = None

    if signal == "LONG":
        sl = entry - risk_mult * atr
        tp1 = entry + risk_mult * atr
        tp2 = entry + 2 * risk_mult * atr
    elif signal == "SHORT":
        sl = entry + risk_mult * atr
        tp1 = entry - risk_mult * atr
        tp2 = entry - 2 * risk_mult * atr

    # -------- КАТЕГОРИЯ СИЛЫ --------
    if strength >= 4:
        strength_label = "сильный"
    elif strength == 3:
        strength_label = "выше среднего"
    elif strength == 2:
        strength_label = "умеренный"
    else:
        strength_label = "слабый/нейтральный"

    return {
        "signal": signal,
        "strength": strength,
        "strength_label": strength_label,
        "reasons": reasons,
        "entry": float(entry),
        "sl": float(sl) if sl is not None else None,
        "tp1": float(tp1) if tp1 is not None else None,
        "tp2": float(tp2) if tp2 is not None else None,
        "atr": float(atr),
        "atr_ratio": float(atr_ratio),
        "rsi": float(rsi),
        "volume_ratio": float(volume_ratio),
    }

# ================== COMMANDS ======================

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "✅ Бот онлайн\n"
        "Источник данных: OKX (свечи)\n\n"
        "Команда:\n"
        "/signal BTCUSDT 1h\n\n"
        "Доступные пары в авто-режиме: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT (1h)"
    )

@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"

    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer("❌ Нет данных или слишком мало волатильности (флет)")
        return

    base = (
        f"<b>Сигнал {symbol}</b>\nTF: {tf}\n\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила: <b>{data['strength']} ({data['strength_label']})</b>\n\n"
    )

    levels = ""
    if data["signal"] != "NEUTRAL" and data["sl"] is not None:
        levels = (
            "Уровни:\n"
            f"- Вход: <b>{data['entry']:.2f}</b>\n"
            f"- SL: <b>{data['sl']:.2f}</b>\n"
            f"- TP1: <b>{data['tp1']:.2f}</b>\n"
            f"- TP2: <b>{data['tp2']:.2f}</b>\n\n"
        )

    extra = (
        f"ATR: {data['atr']:.2f} (~{data['atr_ratio']*100:.2f}% от цены)\n"
        f"RSI: {data['rsi']:.1f}\n"
        f"Объём / средний: {data['volume_ratio']:.2f}x\n\n"
    )

    reasons_txt = "Причины:\n" + "\n".join(f"- {r}" for r in data["reasons"])

    await message.answer(base + levels + extra + reasons_txt)

# ================== AUTO LOOP (BTC, ETH, SOL, BNB) ======================

async def auto_loop():
    print("AUTO LOOP STARTED ✅")

    symbols = [
    "BTCUSDT", "ETHUSDT",          # ориентиры
    "SOLUSDT", "BNBUSDT",
    "OPUSDT", "ARBUSDT",
    "DOGEUSDT", "XRPUSDT", "AVAXUSDT",
    "STRKUSDT", "ZKUSDT",
    "NEARUSDT", "1INCHUSDT", "NOTUSDT"
]

    tf = "1h"
    min_strength = 3          # фильтр по силе
    min_atr_ratio = 0.003     # фильтр по волатильности (~0.3% и выше)
    last_sent = {}

    while True:
        try:
            for symbol in symbols:
                data = analyze_symbol(symbol, tf)

                if "error" in data:
                    continue

                if data["signal"] == "NEUTRAL":
                    continue

                if data["strength"] < min_strength:
                    continue

                if data.get("atr_ratio", 0) < min_atr_ratio:
                    continue

                key = f"{symbol}_{data['signal']}"
                if key in last_sent:
                    continue

                last_sent[key] = True

                color = "🟢" if data["signal"] == "LONG" else "🔴"

                levels = ""
                if data["sl"] is not None:
                    levels = (
                        "Уровни:\n"
                        f"- Вход: <b>{data['entry']:.2f}</b>\n"
                        f"- SL: <b>{data['sl']:.2f}</b>\n"
                        f"- TP1: <b>{data['tp1']:.2f}</b>\n"
                        f"- TP2: <b>{data['tp2']:.2f}</b>\n\n"
                    )

                extra = (
                    f"ATR: {data['atr']:.2f} (~{data['atr_ratio']*100:.2f}% от цены)\n"
                    f"RSI: {data['rsi']:.1f}\n"
                    f"Объём / средний: {data['volume_ratio']:.2f}x\n\n"
                )

                text = (
                    f"{color} <b>СИЛЬНЫЙ СИГНАЛ {symbol}</b>\n"
                    f"TF: {tf}\n\n"
                    f"Направление: <b>{data['signal']}</b>\n"
                    f"Сила: <b>{data['strength']} ({data['strength_label']})</b>\n\n"
                    f"{levels}"
                    f"{extra}"
                    "Причины:\n" +
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

    # без стартового сообщения здесь, чтобы не было дублей при рестартах
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
