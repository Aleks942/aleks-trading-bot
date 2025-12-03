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

# -------------------------------------------------
# Конфиг
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
# Хелпер: форматирование сигнала
# -------------------------------------------------

def format_signal_text(symbol: str, tf: str, data: dict) -> str:
    if "error" in data:
        return f"Ошибка: {data['error']}"

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"TF: <b>{tf}</b>\n\n"
        f"Направление: <b>{data.get('signal', 'нет данных')}</b>\n"
        f"Сила: <b>{data.get('strength', 0)}</b>\n\n"
        "<b>Причины:</b>\n" + "\n".join(f"- {r}" for r in data.get("reasons", []))
    )

    levels = data.get("levels")
    if levels:
        text += (
            "\n\n<b>Уровни:</b>\n"
            f"Вход: <b>{levels['entry']:.2f}</b>\n"
            f"Стоп: <b>{levels['stop_loss']:.2f}</b>\n"
            f"TP1: <b>{levels['take_profit_1']:.2f}</b>\n"
            f"TP2: <b>{levels['take_profit_2']:.2f}</b>\n"
        )

    return text


# -------------------------------------------------
# Команды
# -------------------------------------------------

@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n"
        "Доступные команды:\n"
        "/signal BTCUSDT 1h\n"
        "(автосигналы по BTCUSDT 1h включены для владельца бота)"
    )


@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()

    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    tf = parts[2] if len(parts) > 2 else "1h"

    data = analyze_symbol(symbol, tf)
    text = format_signal_text(symbol, tf, data)
    await message.answer(text)


# -------------------------------------------------
# Автосигналы BTCUSDT 1h
# -------------------------------------------------

async def auto_signal_loop():
    # небольшая задержка после старта
    await asyncio.sleep(5)
    if CHAT_ID != 0:
        try:
            await bot.send_message(CHAT_ID, "Автосигналы BTCUSDT 1h запущены.")
        except Exception:
            pass

    while True:
        try:
            symbol = "BTCUSDT"
            tf = "1h"
            data = analyze_symbol(symbol, tf)
            text = "<b>[AUTO]</b> " + format_signal_text(symbol, tf, data)
            if CHAT_ID != 0:
                await bot.send_message(CHAT_ID, text)
        except Exception as e:
            # можно логировать, если захочешь
            print("AUTO SIGNAL ERROR:", e)

        # раз в час
        await asyncio.sleep(3600)


# -------------------------------------------------
# FastAPI + Webhook
# -------------------------------------------------

app = FastAPI()


@app.on_event("startup")
async def on_startup():
    print("[DEBUG] Запуск бота")
    print("[DEBUG] WEBHOOK_URL:", WEBHOOK_URL)

    # Аккуратно ставим webhook, чтобы не ловить flood
    if WEBHOOK_URL:
        try:
            info = await bot.get_webhook_info()
            if info.url != WEBHOOK_URL:
                print("[DEBUG] Ставлю новый webhook...")
                await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message"])
                print("[DEBUG] Webhook установлен!")
            else:
                print("[DEBUG] Webhook уже установлен, пропускаю set_webhook")
        except Exception as e:
            print("[DEBUG] Ошибка при установке webhook:", e)

    # Запускаем автосигналы
    asyncio.create_task(auto_signal_loop())


@app.on_event("shutdown")
async def on_shutdown():
    print("[DEBUG] Остановка бота")
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    await bot.session.close()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}
