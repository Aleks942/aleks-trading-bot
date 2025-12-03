import os
from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.client.default import DefaultBotProperties

from fastapi import FastAPI, Request

from core.analyzer import analyze_symbol

# -------------------------------------------------
# Конфигурация
# -------------------------------------------------

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

WEBHOOK_URL = os.getenv("WEBHOOK_URL")     # Полный URL Railway
WEBHOOK_PATH = "/webhook"                  # Путь FastAPI

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# -------------------------------------------------
# Команды Telegram
# -------------------------------------------------

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n"
        "Доступные команды:\n"
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

# -------------------------------------------------
# FastAPI + Webhook
# -------------------------------------------------

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("[DEBUG] Запуск бота")
    print("[DEBUG] Удаляю старый webhook...")
    await bot.delete_webhook(drop_pending_updates=True)

    print("[DEBUG] Ставлю новый webhook:", WEBHOOK_URL)
    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=["message"]
    )
    print("[DEBUG] Webhook установлен!")

@app.on_event("shutdown")
async def on_shutdown():
    print("[DEBUG] Остановка бота")
    await bot.delete_webhook()
    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

