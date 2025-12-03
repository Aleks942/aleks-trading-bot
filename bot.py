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
# Вспомогательная функция форматирования сигнала
# -----------------------------
def format_signal_text(symbol: str, tf: str, data: dict, htf_used: bool = False) -> str:
    """
    Собирает текст сигнала для отправки в Telegram.
    Если htf_used=True — добавляем пометку, что учтён старший ТФ.
    """
    if "error" in data:
        return f"Ошибка: {data['error']}"

    header_tf = tf
    if htf_used:
        header_tf = f"{tf} + 4h"

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"TF: <b>{header_tf}</b>\n\n"
        f"Направление: <b>{data.get('signal', 'нет данных')}</b>\n"
        f"Сила: <b>{data.get('strength', 0)}</b>\n\n"
        "<b>Причины:</b>\n" +
        "\n".join(f"- {r}" for r in data.get("reasons", []))
    )

    return text


# -----------------------------
# Команды
# -----------------------------
@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает</b>\n"
        "Команды:\n"
        "/signal BTCUSDT 1h\n\n"
        "Автосигналы: BTCUSDT 1h, сила ≥ 3, только по тренду 4h."
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


# -----------------------------
# FastAPI + webhook
# -----------------------------
app = FastAPI()


@app.on_event("startup")
async def on_startup():
    print("[DEBUG] Запуск бота")
    print("[DEBUG] WEBHOOK_URL:", WEBHOOK_URL)

    # Удаляем старый webhook и дропаем накопившиеся апдейты
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("[DEBUG] Старый webhook удалён")
    except Exception as e:
        print("[DEBUG] Ошибка при удалении webhook:", e)

    # Ставим новый webhook
    try:
        await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message"])
        print("[DEBUG] Новый webhook установлен")
    except Exception as e:
        print("[DEBUG] Ошибка при установке webhook:", e)

    # Запускаем цикл авто-сигналов
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


# -----------------------------
# Фильтр по старшему ТФ (4h)
# -----------------------------
def htf_allows_trade(symbol: str, tf_signal: dict, htf: str = "4h") -> bool:
    """
    Разрешает авто-сделку только если сигнал на старшем ТФ совпадает по направлению.
    tf_signal — результат analyze_symbol(symbol, "1h")
    """
    try:
        htf_data = analyze_symbol(symbol, htf)

        if not htf_data or "signal" not in htf_data:
            print("[HTF] Нет данных старшего ТФ")
            return False

        tf_dir = tf_signal.get("signal")
        htf_dir = htf_data.get("signal")

        if tf_dir == htf_dir and tf_dir in ("LONG", "SHORT"):
            print(f"[HTF] Подтверждение: 1h={tf_dir}, 4h={htf_dir}")
            return True

        print(f"[HTF] Блокировка: 1h={tf_dir}, 4h={htf_dir}")
        return False

    except Exception as e:
        print("[HTF] Ошибка:", e)
        return False


# -----------------------------
# Авто-сигналы (BTCUSDT 1h, сила ≥ 3, только по тренду 4h)
# -----------------------------
async def auto_signal_loop():
    # Ждём 1 час до первого авто-сигнала, чтобы не спамить сразу после запуска
    await asyncio.sleep(3600)

    while True:
        try:
            symbol = "BTCUSDT"
            tf = "1h"

            data = analyze_symbol(symbol, tf)
            if "error" in data:
                print(f"[AUTO] Ошибка анализа: {data['error']}")
                await asyncio.sleep(3600)
                continue

            # --- ФИЛЬТР ПО СИЛЕ ---
            strength = int(data.get("strength", 0))
            if strength < 3:
                print(f"[AUTO] Пропуск по силе, сила={strength}")
                await asyncio.sleep(3600)
                continue

            # --- ФИЛЬТР ПО СТАРШЕМУ ТФ (4h) ---
            if not htf_allows_trade(symbol, data, htf="4h"):
                print("[AUTO] Пропуск по HTF (4h не подтверждает направление)")
                await asyncio.sleep(3600)
                continue

            # Формируем текст сигнала с пометкой, что учтён 4h
            text = "<b>[AUTO]</b>\n" + format_signal_text(symbol, tf, data, htf_used=True)

            if CHAT_ID != 0:
                await bot.send_message(CHAT_ID, text)

        except Exception as e:
            print("AUTO SIGNAL ERROR:", e)

        # Интервал авто-сигналов = 1 час
        await asyncio.sleep(3600)
