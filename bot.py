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
# 1. Настройки
# -------------------------------------------------

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

# -------------------------------------------------
# 2. Команды
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
    try:
        parts = message.text.split()
        symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
        tf = parts[2] if len(parts) > 2 else "1h"
    except Exception:
        await message.answer("Формат: /signal BTCUSDT 1h")
        return

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
# 3. FASTAPI ПРИЛОЖЕНИЕ
# -------------------------------------------------

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("[DEBUG] Запуск бота")
    print("[DEBUG] WEBHOOK_URL:", WEBHOOK_URL)

    # ВАЖНО: запускаем Dispatcher
    await dp.startup(bot)

    # Устанавливаем вебхук
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
        print("[DEBUG] Webhook установлен")


@app.on_event("shutdown")
async def on_shutdown():
    print("[DEBUG] Остановка бота")
    await dp.shutdown()
    await bot.session.close()


# -------------------------------------------------
# 4. ОБРАБОТЧИК ВЕБХУКА
# -------------------------------------------------

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

# -------------------------------------------------
# 5. БОЛЬШЕ НЕТ uvicorn.run — ЗАПУСКАЕМСЯ ЧЕРЕЗ PROCFILE
# -------------------------------------------------

