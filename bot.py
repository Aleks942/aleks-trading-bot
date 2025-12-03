import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.client.default import DefaultBotProperties

from core.analyzer import analyze_symbol

# ---------------------------------
# ENV
# ---------------------------------

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

# ---------------------------------
# BOT
# ---------------------------------

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# ---------------------------------
# COMMANDS
# ---------------------------------

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n"
        "Команда:\n"
        "/signal BTCUSDT 1h"
    )


@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()

    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"

    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer(f"Ошибка: {data['error']}")
        return

    text = format_signal_text(symbol, tf, data)
    await message.answer(text)


# ---------------------------------
# FORMATTERS
# ---------------------------------

def format_signal_text(symbol, tf, data, htf_used=False):
    direction = data["signal"]
    strength = int(data.get("strength", 0))

    if direction == "LONG":
        emoji = "🟢"
    elif direction == "SHORT":
        emoji = "🔴"
    else:
        emoji = "🟡"

    reasons = "\n".join(f"- {r}" for r in data["reasons"])

    htf_note = "\nHTF: подтверждён ✅" if htf_used else ""

    text = (
        f"{emoji} <b>Сигнал {symbol}</b>\n"
        f"TF: {tf}\n\n"
        f"Направление: <b>{direction}</b>\n"
        f"Сила: <b>{strength}</b>\n"
        f"{htf_note}\n\n"
        f"<b>Причины:</b>\n{reasons}"
    )

    return text


def format_overview_text(symbol, tf, data):
    strength = int(data.get("strength", 0))
    direction = data["signal"]

    if strength >= 3:
        emoji = "🟢" if direction == "LONG" else "🔴"
        status = "сильный импульс"
    else:
        emoji = "🟡"
        status = "слабый импульс"

    reasons = "\n".join(f"- {r}" for r in data["reasons"])

    text = (
        f"{emoji} <b>Обзор рынка {symbol}</b>\n"
        f"TF: {tf}\n\n"
        f"Направление: <b>{direction}</b>\n"
        f"Сила: <b>{strength}</b>\n"
        f"Статус: {status}\n\n"
        f"<b>Контекст:</b>\n{reasons}"
    )

    return text


# ---------------------------------
# HTF FILTER (4H)
# ---------------------------------

def htf_allows_trade(symbol, data, htf="4h"):
    htf_data = analyze_symbol(symbol, htf)

    if "error" in htf_data:
        return False

    return htf_data["signal"] == data["signal"]


# ---------------------------------
# AUTO OVERVIEW LOOP (BTC + ETH)
# ---------------------------------

last_overview_sent = {}

async def market_overview_loop():
    await asyncio.sleep(90)

    symbols = ["BTCUSDT", "ETHUSDT"]
    tf = "1h"

    while True:
        try:
            for symbol in symbols:
                data = analyze_symbol(symbol, tf)

                if "error" in data:
                    continue

                strength = int(data.get("strength", 0))
                direction = data.get("signal")

                key = f"{symbol}_{tf}_{direction}_{strength}"

                if last_overview_sent.get(symbol) == key:
                    continue

                last_overview_sent[symbol] = key

                text = format_overview_text(symbol, tf, data)

                if CHAT_ID != 0:
                    await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("[OVERVIEW ERROR]", e)

        await asyncio.sleep(900)  # 15 минут


# ---------------------------------
# STRONG SIGNAL LOOP (≥ 3 + HTF)
# ---------------------------------

last_strong_signal = None

async def auto_signal_loop():
    global last_strong_signal

    await asyncio.sleep(120)

    while True:
        try:
            symbol = "BTCUSDT"
            tf = "1h"

            data = analyze_symbol(symbol, tf)

            if "error" in data:
                await asyncio.sleep(3600)
                continue

            strength = int(data.get("strength", 0))

            if strength < 3:
                await asyncio.sleep(3600)
                continue

            if not htf_allows_trade(symbol, data, htf="4h"):
                await asyncio.sleep(3600)
                continue

            direction = data.get("signal")
            key = f"{symbol}_{tf}_{direction}_{strength}"

            if key == last_strong_signal:
                await asyncio.sleep(3600)
                continue

            last_strong_signal = key

            text = (
                ("🟢" if direction == "LONG" else "🔴") +
                " <b>СИЛЬНЫЙ СИГНАЛ</b>\n\n" +
                format_signal_text(symbol, tf, data, htf_used=True)
            )

            if CHAT_ID != 0:
                await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("[AUTO SIGNAL ERROR]", e)

        await asyncio.sleep(3600)


# ---------------------------------
# FASTAPI
# ---------------------------------

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("[START] Webhook:", WEBHOOK_URL)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

    asyncio.create_task(market_overview_loop())
    asyncio.create_task(auto_signal_loop())


@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

        
