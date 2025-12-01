import os
import asyncio

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update
from core.analyzer import analyze_symbol
from fastapi import FastAPI, Request
import uvicorn

# -------------------------------------------------
# 1. Настройки и инициализация
# -------------------------------------------------

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# -------------------------------------------------
# 2. Команда /start
# -------------------------------------------------

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот запущен</b>\n"
        "Используй:\n"
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
        await message.answer("Неверный формат. Пример: /signal BTCUSDT 1h")
        return

    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer(f"Ошибка: {data['error']}")
        return

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"Таймфрейм: <b>{tf}</b>\n\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила: <b>{data['strength']}</b>\n\n"
        f"<b>Причины:</b>\n"
        + "\n".join(f"- {r}" for r in data["reasons"])
    )

    await message.answer(text)

# -------------------------------------------------
# 4. Автозадача (периодические сигналы)
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
                    "<b>Причины:</b>\n"
                    + "\n".join(f"- {r}" for r in data["reasons"])
                )
                await bot.send_message(CHAT_ID, text)
        except Exception as e:
            print("Ошибка в авто-задаче:", e)

        # раз в 60 секунд (можешь потом поменять)
        await asyncio.sleep(60)

# -------------------------------------------------
# 5. Webhook + FastAPI (Render)
# -------------------------------------------------

app = FastAPI()

# Используем ТОЛЬКО ОДНУ переменную окружения WEBHOOK_URL
WEBHOOK_URL = os.getenv("WEBHOOK_URL") 
WEBHOOK_PATH = "/webhook" # Оставляем путь как константу

@app.on_event("startup")
async def on_startup():
    # Мы можем добавить отладочный print, чтобы убедиться в правильности URL
    print(f"DEBUG: Setting webhook to URL: {WEBHOOK_URL}")

    # запускаем фоновую авто-задачу
    asyncio.create_task(periodic_task())
    
    # устанавливаем webhook для Telegram
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
    else:
        # Если URL не установлен, мы выводим ошибку и не пытаемся установить вебхук
        print("ERROR: WEBHOOK_URL environment variable not set. Webhook will not be set.")

@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    """
    Telegram шлёт сюда апдейты.
    Мы превращаем JSON в объект Update и
    отдаём его в Dispatcher, чтобы сработали /start и /signal.
    """
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"status": "ok"}

# -------------------------------------------------
# 6. Запуск сервера (для Docker / Render)
# -------------------------------------------------

if __name__ == "__main__":
    # Также убедитесь, что переменная PORT правильно считывается здесь
    PORT = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=PORT)
