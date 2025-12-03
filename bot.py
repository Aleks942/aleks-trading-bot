import os
import asyncio
import requests
import pandas as pd

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.client.default import DefaultBotProperties

from fastapi import FastAPI, Request

# ================== ENV ==================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
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

# ================== DATA: Binance OHLCV ==================

def get_ohlcv(symbol: str = "BTCUSDT", tf: str = "1h"):
    """
    Простая загрузка свечей с Binance.
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": tf,   # например "1h", "4h"
        "limit": 200
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception as e:
        print("GET_OHLCV ERROR:", e)
        return None

    if not isinstance(data, list) or len(data) < 50:
        return None

    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "_"
    ])

    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

# ================== ANALYSIS ==================

def analyze_symbol(symbol: str = "BTCUSDT", tf: str = "1h"):
    """
    Базовый анализ: тренд, MACD, RSI, объём.
    Возвращает словарь с signal / strength / reasons.
    """
    df = get_ohlcv(symbol, tf)
    if df is None or len(df) < 50:
        return {"error": "Недостаточно данных"}

    close = df["close"]
    volume = df["volume"]

    # EMA
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    trend = "up" if ema20 > ema50 else "down"

    # "псевдо RSI": просто знак среднего изменения
    rsi_raw = close.pct_change().rolling(14).mean().iloc[-1]

    # MACD
    macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    macd_hist = macd_line.iloc[-1]

    # Объём
    avg_vol = volume.rolling(20).mean().iloc[-2]
    last_vol = volume.iloc[-1]
    volume_ratio = last_vol / avg_vol if avg_vol > 0 else 1

    score = 0
    reasons = []

    # Тренд
    if trend == "up":
        score += 1
        reasons.append("Тренд восходящий (EMA20 > EMA50)")
    else:
        score -= 1
        reasons.append("Тренд нисходящий (EMA20 < EMA50)")

    # MACD
    if macd_hist > 0:
        score += 1
        reasons.append("MACD бычий")
    else:
        score -= 1
        reasons.append("MACD медвежий")

    # RSI-подобный фильтр
    if rsi_raw > 0:
        score += 1
        reasons.append("RSI поддерживает рост")
    else:
        score -= 1
        reasons.append("RSI слабый / за шорт")

    # Объём
    if volume_ratio > 1.2:
        score += 1
        reasons.append("Объём выше среднего")
    else:
        reasons.append("Объём без аномалий")

    # Итоговый сигнал
    if score >= 3:
        signal = "LONG"
    elif score <= -3:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    return {
        "signal": signal,
        "strength": abs(score),
        "reasons": reasons,
        "volume_ratio": volume_ratio
    }


def pick_htf(tf: str) -> str:
    """
    Подбираем старший ТФ под младший.
    """
    tf = tf.lower()
    if tf == "15m":
        return "1h"
    if tf == "1h":
        return "4h"
    if tf == "4h":
        return "1d"
    return "4h"

# ================== COMMANDS ==================

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот онлайн</b>\n"
        "Команды:\n"
        "/signal BTCUSDT 1h"
    )

@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()

    symbol = parts[1].upper() if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"
    htf = pick_htf(tf)

    ltf_data = analyze_symbol(symbol, tf)
    htf_data = analyze_symbol(symbol, htf)

    if "error" in ltf_data:
        await message.answer(f"Ошибка LTF: {ltf_data['error']}")
        return
    if "error" in htf_data:
        await message.answer(f"Ошибка HTF: {htf_data['error']}")
        return

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"TF: {tf} | HTF: {htf}\n\n"
        f"LTF: <b>{ltf_data['signal']}</b> (сила {ltf_data['strength']})\n"
        f"HTF: <b>{htf_data['signal']}</b> (сила {htf_data['strength']})\n\n"
        "<b>Причины LTF:</b>\n" +
        "\n".join(f"- {r}" for r in ltf_data["reasons"])
    )

    await message.answer(text)

# ================== AUTO LOOP ==================

async def auto_signal_loop():
    """
    Авто-обзор + сильные сигналы.
    Каждые 15 минут:
      - даём обзор по BTC и ETH (1h)
      - если сила >=3 и HTF согласен — шлём отдельный мощный сигнал.
    """
    symbols = ["BTCUSDT", "ETHUSDT"]
    tf = "1h"
    htf = "4h"
    min_strength = 3

    last_strong = {}

    while True:
        try:
            for symbol in symbols:
                ltf_data = analyze_symbol(symbol, tf)
                htf_data = analyze_symbol(symbol, htf)

                if "error" in ltf_data or "error" in htf_data:
                    print("AUTO ERROR DATA:", symbol, ltf_data.get("error"), htf_data.get("error"))
                    continue

                # ---------- Обзор рынка (жёлтый) ----------
                if ltf_data["signal"] == "LONG":
                    emoji = "🟢" if ltf_data["strength"] >= min_strength else "🟡"
                elif ltf_data["signal"] == "SHORT":
                    emoji = "🔴" if ltf_data["strength"] >= min_strength else "🟡"
                else:
                    emoji = "🟡"

                status = "слабый импульс"
                if ltf_data["strength"] >= min_strength:
                    status = "сильный импульс"

                overview_text = (
                    f"{emoji} <b>Обзор рынка {symbol}</b>\n"
                    f"TF: {tf} | HTF: {htf}\n\n"
                    f"LTF: {ltf_data['signal']} (сила {ltf_data['strength']})\n"
                    f"HTF: {htf_data['signal']} (сила {htf_data['strength']})\n"
                    f"Статус: {status}\n\n"
                    "<b>Причины LTF:</b>\n" +
                    "\n".join(f"- {r}" for r in ltf_data["reasons"])
                )

                await bot.send_message(CHAT_ID, overview_text)

                # ---------- Сильный сигнал по тренду HTF ----------
                if (
                    ltf_data["signal"] in ("LONG", "SHORT") and
                    ltf_data["strength"] >= min_strength and
                    ltf_data["signal"] == htf_data["signal"]
                ):
                    key = f"{symbol}_{ltf_data['signal']}"
                    if not last_strong.get(key):
                        last_strong[key] = True

                        strong_color = "🟢" if ltf_data["signal"] == "LONG" else "🔴"

                        strong_text = (
                            f"{strong_color} <b>СИЛЬНЫЙ СИГНАЛ {symbol}</b>\n"
                            f"TF: {tf} | HTF: {htf}\n\n"
                            f"Направление: {ltf_data['signal']}\n"
                            f"Сила: {ltf_data['strength']}\n\n"
                            "<b>Причины LTF:</b>\n" +
                            "\n".join(f"- {r}" for r in ltf_data["reasons"])
                        )

                        await bot.send_message(CHAT_ID, strong_text)

            # ждём 15 минут
            await asyncio.sleep(900)

        except Exception as e:
            print("AUTO LOOP ERROR:", e)
            await asyncio.sleep(30)

# ================== FASTAPI + WEBHOOK ==================

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("[DEBUG] STARTUP")
    if WEBHOOK_URL:
        # Сначала чистим старый вебхук, потом ставим новый
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL)
        print("[DEBUG] Webhook установлен:", WEBHOOK_URL)

    # Запускаем фоновые авто-сигналы
    asyncio.create_task(auto_signal_loop())

@app.on_event("shutdown")
async def on_shutdown():
    print("[DEBUG] SHUTDOWN")
    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}
