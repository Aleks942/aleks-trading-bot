# update test
import asyncio
import datetime

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from core.analyzer import analyze_symbol

TOKEN = "8473865365:AAH4biKKokz6Io23ZkqBuO7Q0HnzTdXCT9o"
CHAT_ID = "851440772"

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# /start
@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот запущен.</b>\n"
        "Используй:\n"
        "<b>/signal BTCUSDT 1h</b>"
    )

# /signal BTCUSDT 1h
@router.message(Command("signal"))
async def signal_cmd(message: Message):
    try:
        parts = message.text.split()
        symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
        tf = parts[2] if len(parts) > 2 else "1h"
    except:
        await message.answer("Ошибка формата. Пример: /signal BTCUSDT 1h")
        return

    data = analyze_symbol(symbol, tf)

    if "error" in data:
        await message.answer(f"❌ Ошибка: {data['error']}")
        return

    text = (
        f"<b>Сигнал по {symbol}</b>\n"
        f"Таймфрейм: <b>{tf}</b>\n\n"
        f"Направление: <b>{data['signal']}</b>\n"
        f"Сила сигнала: <b>{data['strength']}</b>\n\n"
        "<b>Причины:</b>\n"
        + "\n".join(f"• {r}" for r in data["reasons"])
    )

    await message.answer(text)

# Периодический авто-анализ BTCUSDT 1h
async def periodic_task():
    while True:
        try:
            data = analyze_symbol("BTCUSDT", "1h")

            if "error" not in data:
                text = (
                    f"<b>Авто-сигнал (BTCUSDT 1h)</b>\n\n"
                    f"Направление: <b>{data['signal']}</b>\n"
                    f"Сила: <b>{data['strength']}</b>\n\n"
                    "<b>Причины:</b>\n"
                    + "\n".join(f"• {r}" for r in data["reasons"])
                )
                await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("Ошибка:", e)

        await asyncio.sleep(60)

async def main():
    asyncio.create_task(periodic_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
