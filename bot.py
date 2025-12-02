import os
import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update

from fastapi import FastAPI, Request
import uvicorn

from core.analyzer import analyze_symbol

# -------------------------------------------------
# 1. Настройки
# -------------------------------------------------

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")     # https://....railway.app/webhook
WEBHOOK_PATH = "/webhook"

# Инициализация aiogram
bot = Bot(token=TOKEN, default=ParseMode.HTML)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# -------------------------------------------------
# 2. Команда /start
# -------------------------------------------------

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n"
        "Доступные команды:\n"
        "/signal BTCUSDT 1h"
    )

# -------------------------------------------------
# 3. Команда /signal
# -------------------------------------------------

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
# 4. Автосигналы (каждые 60 сек)
# -------------------------------------------------

async def periodic_task():
    while True:
        try:
            data = analyze_symbol("BTCUSDT", "1h")
            if "error" not in data:
                text = (
                    "<b>Авто-сигнал (BTCUSDT 1h)</b>\n\n"
                    f"Направление: <b>{data['signal']}</b>\n"
                    f"Сила: <b>{data['strength']}</b>\n\n"
                    "<b>Причины:</b>\n" + "\n".join(f"- {r}" for r in data["reasons"])
                )
                await bot.send_message(CHAT_ID, text)
        except Exception as e:
            print("Ошибка в авто-задаче:", e)

        await asyncio.sleep(60)

# -------------------------------------------------
# 5. FastAPI + Webhook
# -------------------------------------------------

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print(f"[DEBUG] Starting bot with webhook: {WEBHOOK_URL}")

    # Запустить авто-таск
    asyncio.create_task(periodic_task())

    # Установить вебхук — критично!
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
        print("[DEBUG] Webhook установлен")
    else:
        print("ERROR: WEBHOOK_URL не установлен!")

# Приём webhook от Telegram
@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"status": "ok"}

# -------------------------------------------------
# 6. Запуск (Railway)
# -------------------------------------------------

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8080))
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, reload=False)

