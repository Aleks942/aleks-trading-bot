import os
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.client.default import DefaultBotProperties

from fastapi import FastAPI, Request

from core.analyzer import analyze_symbol

# -----------------------------
# Загрузка переменных окружения
# -----------------------------
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

# -----------------------------
# Инициализация бота
# -----------------------------
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# -----------------------------
# КОМАНДЫ
# -----------------------------

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n"
        "Команды:\n"
        "/signal BTCUSDT 1h"
    )

@router.message(Command("signal"))
async def signal_cmd(message: Message):
    try:
        parts = message.text.split()
        symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
        tf = parts[2] if len(parts) > 2 else "1h"

        data = analyze_symbol(symbol, tf)

        text = (
            f"<b>Сигнал {symbol}</b>\n"
            f"TF: <b>{tf}</b>\n\n"
            f"Направление: <b>{data['signal']}</b>\n"
            f"Сила: <b>{data['strength']}</b>\n\n"
            "<b>Причины:</b>\n" +
            "\n".join(f"- {r}" for r in data["reasons"])
        )

        await message.answer(text)

    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# -----------------------------
# FASTAPI
# -----------------------------
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("[DEBUG] Запуск бота")

    # Удаляем старый webhook
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("[DEBUG] Старый webhook удалён")
    except Exception:
        pass

    # Ставим новый webhook
    await bot.set_webhook(WEBHOOK_URL)
    print("[DEBUG] Новый webhook установлен")

    # Запуск авто-сигналов
    asyncio.create_task(auto_signal_loop())

@app.on_event("shutdown")
async def on_shutdown():
    print("[DEBUG] Остановка бота")
    await bot.delete_webhook()
    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

# -----------------------------
# АВТО-СИГНАЛЫ (ТОЛЬКО СИЛА >= 3)
# -----------------------------

async def auto_signal_loop():
    # Ждём 1 час до первого авто-сигнала
    await asyncio.sleep(3600)

    while True:
        try:
            symbol = "BTCUSDT"
            tf = "1h"

            data = analyze_symbol(symbol, tf)
            strength = int(data.get("strength", 0))

            # --- ФИЛЬТР ПО СИЛЕ ---
            if strength < 3:
                print(f"[AUTO] Пропуск сигнала, сила={strength}")
                await asyncio.sleep(3600)
                continue

            text = (
                "<b>[AUTO]</b>\n"
                f"<b>Сигнал {symbol}</b>\n"
                f"TF: <b>{tf}</b>\n\n"
                f"Направление: <b>{data['signal']}</b>\n"
                f"Сила: <b>{data['strength']}</b>\n\n"
                "<b>Причины:</b>\n" +
                "\n".join(f"- {r}" for r in data["reasons"])
            )

            if CHAT_ID != 0:
                await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("AUTO SIGNAL ERROR:", e)

        # Интервал авто-сигналов = 1 час
        await asyncio.sleep(3600)
