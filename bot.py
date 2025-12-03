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

# =============================
# Загрузка переменных
# =============================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

# =============================
# Инициализация бота
# =============================
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# =============================
# Форматирование текста сигналов
# =============================
def format_signal_text(symbol: str, tf: str, data: dict, htf_used: bool = False) -> str:
    if "error" in data:
        return f"Ошибка: {data['error']}"

    header_tf = tf
    if htf_used:
        header_tf = f"{tf} + 4h"

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"TF: <b>{header_tf}</b>\n\n"
        f"Направление: <b>{data.get('signal')}</b>\n"
        f"Сила: <b>{data.get('strength')}</b>\n\n"
        "<b>Причины:</b>\n" +
        "\n".join(f"- {r}" for r in data.get("reasons", []))
    )
    return text


def format_overview_text(symbol: str, tf: str, data: dict) -> str:
    strength = int(data.get("strength", 0))
    direction = data.get("signal", "NEUTRAL")

    if strength >= 3:
        emoji = "🟠"
        status = "усиливается, наблюдать"
    elif strength == 2:
        emoji = "🟡"
        status = "слабый импульс"
    else:
        emoji = "⚪"
        status = "флет / неопределённость"

    text = (
        f"{emoji} <b>Обзор рынка {symbol}</b>\n"
        f"TF: <b>{tf}</b>\n\n"
        f"Направление: <b>{direction}</b>\n"
        f"Сила: <b>{strength}</b>\n"
        f"Статус: <b>{status}</b>\n\n"
        "<b>Контекст:</b>\n" +
        "\n".join(f"- {r}" for r in data.get("reasons", []))
    )
    return text


# =============================
# Команды
# =============================
@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n\n"
        "Команды:\n"
        "/signal BTCUSDT 1h\n\n"
        "Авто-режим:\n"
        "• Обзор BTC + ETH каждые 15 минут\n"
        "• Сильные сигналы: сила ≥ 3 + подтверждение 4h"
    )


@router.message(Command("signal"))
async def signal_cmd(message: Message):
    try:
        parts = message.text.split()
        symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
        tf = parts[2] if len(parts) > 2 else "1h"

        data = analyze_symbol(symbol, tf)
        text = format_signal_text(symbol, tf, data, htf_used=False)
        await message.answer(text)

    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# =============================
# FastAPI + Webhook
# =============================
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("[DEBUG] Запуск бота")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("[DEBUG] Старый webhook удалён")
    except Exception:
        pass

    await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message"])
    print("[DEBUG] Новый webhook установлен")

    asyncio.create_task(auto_signal_loop())
    asyncio.create_task(market_overview_loop())


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


# =============================
# Фильтр по старшему ТФ (4h)
# =============================
def htf_allows_trade(symbol: str, tf_signal: dict, htf: str = "4h") -> bool:
    try:
        htf_data = analyze_symbol(symbol, htf)

        if not htf_data or "signal" not in htf_data:
            print("[HTF] Нет данных")
            return False

        tf_dir = tf_signal.get("signal")
        htf_dir = htf_data.get("signal")

        if tf_dir == htf_dir and tf_dir in ("LONG", "SHORT"):
            print(f"[HTF] Подтверждение {tf_dir}")
            return True

        print(f"[HTF] Блокировка: 1h={tf_dir}, 4h={htf_dir}")
        return False

    except Exception as e:
        print("[HTF] Ошибка:", e)
        return False


# =============================
# Сильные авто-сигналы (сила ≥ 3 + 4h)
# =============================
async def auto_signal_loop():
    await asyncio.sleep(60)

    while True:
        try:
            symbol = "BTCUSDT"
            tf = "1h"

            data = analyze_symbol(symbol, tf)

            if "error" in data:
                print("[AUTO] Ошибка:", data["error"])
                await asyncio.sleep(3600)
                continue

            strength = int(data.get("strength", 0))

            if strength < 3:
                print(f"[AUTO] Пропуск по силе: {strength}")
                await asyncio.sleep(3600)
                continue

            if not htf_allows_trade(symbol, data, htf="4h"):
                print("[AUTO] Пропуск по HTF")
                await asyncio.sleep(3600)
                continue

            direction = data.get("signal")
            emoji = "🟢" if direction == "LONG" else "🔴"

            text = (
                f"{emoji} <b>[STRONG {direction}]</b>\n" +
                format_signal_text(symbol, tf, data, htf_used=True)
            )

            if CHAT_ID != 0:
                await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("AUTO SIGNAL ERROR:", e)

        await asyncio.sleep(3600)


# =============================
# Обзор рынка каждые 15 минут (BTC + ETH)
# =============================
async def market_overview_loop():
    await asyncio.sleep(60)

    symbols = ["BTCUSDT", "ETHUSDT"]
    tf = "1h"

    while True:
        try:
            for symbol in symbols:
                data = analyze_symbol(symbol, tf)

                if "error" in data:
                    print(f"[OVERVIEW] Ошибка {symbol}: {data['error']}")
                    continue

                text = format_overview_text(symbol, tf, data)

                if CHAT_ID != 0:
                    await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("[OVERVIEW] ERROR:", e)

        await asyncio.sleep(900)  # 15 минут
