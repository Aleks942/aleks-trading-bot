import os
import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from core.analyzer import analyze_symbol

# Забираем токен из переменной окружения Render
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")   # создадим позже

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
dp.include_router(router)


@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот запущен</b>\n"
        "Используй:\n"
        "/signal BTCUSDT 1h"
    )


@router.message(Command("signal"))
async def signal_cmd(message: Message):
    try:
        parts = message.text.split()
        symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
        tf = parts[2] if len(parts) > 2 else "1h"
    except:
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
        "<b>Причины:</b>\n" +
        "\n".join(f"• {r}" for r in data["reasons"])
    )

    await message.answer(text)


async def periodic_task():
    while True:
        try:
            data = analyze_symbol("BTCUSDT", "1h")
            if "error" not in data:
                text = (
                    "<b>Авто-сигнал (BTCUSDT 1h)</b>\n\n"
                    f"Направление: <b>{data['signal']}</b>\n"
                    f"Сила: <b>{data['strength']}</b>\n\n"
                    "<b>Причины:</b>\n" +
                    "\n".join(f"• {r}" for r in data["reasons"])
                )
                await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("Ошибка в авто-задаче:", e)

        await asyncio.sleep(60)


async def main():
    asyncio.create_task(periodic_task())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH


@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)


@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    await bot.send_message(os.getenv("CHAT_ID"), str(data))
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
