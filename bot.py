import os
import asyncio
from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.client.default import DefaultBotProperties

from fastapi import FastAPI, Request

from core.analyzer import analyze_symbol

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

AUTO_TASK = None  # ✅ защита от дублей

# =========================
# COMMANDS
# =========================
@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n"
        "Команды:\n"
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

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"TF: <b>{tf}</b>\n\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила: <b>{data['strength']}</b>\n\n"
        "<b>Причины:</b>\n" + "\n".join(f"- {r}" for r in data["reasons"])
    )

    await message.answer(text)

# =========================
# AUTO MARKET OVERVIEW
# =========================
async def auto_signal_loop():
    symbols = ["BTCUSDT", "ETHUSDT"]
    tf = "1h"

    while True:
        for symbol in symbols:
            data = analyze_symbol(symbol, tf)

            if "error" in data:
                continue

            strength = data["strength"]
            signal = data["signal"]

            # Статус по силе
            if strength >= 3:
                icon = "🟢" if signal == "LONG" else "🔴"
                status = "сильный импульс"
            else:
                icon = "🟡"
                status = "слабый импульс"

            text = (
                f"{icon} <b>Обзор рынка {symbol}</b>\n"
                f"TF: {tf}\n\n"
                f"Направление: {signal}\n"
                f"Сила: {strength}\n"
                f"Статус: {status}\n\n"
                "<b>Контекст:</b>\n"
                + "\n".join(f"- {r}" for r in data["reasons"])
            )

            try:
                await bot.send_message(CHAT_ID, text)
            except Exception as e:
                print("SEND ERROR:", e)

        await asyncio.sleep(900)  # ✅ 15 минут

# =========================
# FASTAPI
# =========================
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    global AUTO_TASK

    print("[DEBUG] Запуск бота")
    print("[DEBUG] WEBHOOK_URL:", WEBHOOK_URL)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("[DEBUG] Старый webhook удалён")
    except:
        pass

    await bot.set_webhook(WEBHOOK_URL)
    print("[DEBUG] Новый webhook установлен")

    # ✅ запуск авто-цикла только один раз
    if AUTO_TASK is None:
        print("[DEBUG] Запуск авто-аналитики")
        AUTO_TASK = asyncio.create_task(auto_signal_loop())
    else:
        print("[DEBUG] Авто-аналитика уже запущена")

@app.on_event("shutdown")
async def on_shutdown():
    global AUTO_TASK
    print("[DEBUG] Остановка бота")

    if AUTO_TASK:
        AUTO_TASK.cancel()
        AUTO_TASK = None

    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

        
