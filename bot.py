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

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

BASE_TF = "1h"
HTF_TF = "4h"

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

AUTO_TASK = None  # защита от дублей

# =========================
# COMMANDS
# =========================
@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "<b>Бот работает (HTF активен)</b>\n"
        "Команды:\n"
        "/signal BTCUSDT 1h"
    )


@router.message(Command("signal"))
async def signal_cmd(message: Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"

    base = analyze_symbol(symbol, BASE_TF)
    htf = analyze_symbol(symbol, HTF_TF)

    if "error" in base:
        await message.answer(f"Ошибка: {base['error']}")
        return
    if "error" in htf:
        await message.answer(f"Ошибка HTF: {htf['error']}")
        return

    htf_trend = htf["signal"]
    blocked = False

    if base["signal"] == "LONG" and htf_trend != "LONG":
        blocked = True
    if base["signal"] == "SHORT" and htf_trend != "SHORT":
        blocked = True

    block_text = "❌ Заблокирован HTF" if blocked else "✅ Подтверждён HTF"

    reasons = base["reasons"] + [f"HTF (4h): {htf_trend}", block_text]

    text = (
        f"<b>Сигнал {symbol}</b>\n"
        f"TF: {BASE_TF} | HTF: {HTF_TF}\n\n"
        f"Направление: <b>{base['signal']}</b>\n"
        f"Сила: <b>{base['strength']}</b>\n\n"
        "<b>Контекст:</b>\n" + "\n".join(f"- {r}" for r in reasons)
    )

    await message.answer(text)

# =========================
# AUTO LOOP WITH HTF
# =========================
async def auto_signal_loop():
    symbols = ["BTCUSDT", "ETHUSDT"]

    while True:
        for symbol in symbols:
            base = analyze_symbol(symbol, BASE_TF)
            htf = analyze_symbol(symbol, HTF_TF)

            if "error" in base or "error" in htf:
                continue

            strength = base["strength"]
            signal = base["signal"]
            htf_trend = htf["signal"]

            htf_ok = (
                (signal == "LONG" and htf_trend == "LONG") or
                (signal == "SHORT" and htf_trend == "SHORT")
            )

            # Цвет и статус
            if strength >= 3 and htf_ok:
                icon = "🟢" if signal == "LONG" else "🔴"
                status = "сильный импульс (HTF подтверждён)"
            else:
                icon = "🟡"
                status = "слабый импульс / без HTF"

            text = (
                f"{icon} <b>Обзор рынка {symbol}</b>\n"
                f"TF: {BASE_TF} | HTF: {HTF_TF}\n\n"
                f"Направление: {signal}\n"
                f"Сила: {strength}\n"
                f"Статус: {status}\n\n"
                "<b>Контекст:</b>\n"
                + "\n".join(f"- {r}" for r in base["reasons"])
                + f"\n- HTF (4h): {htf_trend}"
            )

            try:
                await bot.send_message(CHAT_ID, text)
            except Exception as e:
                print("SEND ERROR:", e)

        await asyncio.sleep(900)  # 15 минут

# =========================
# FASTAPI
# =========================
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    global AUTO_TASK

    print("[DEBUG] Запуск бота (HTF)")
    print("[DEBUG] WEBHOOK_URL:", WEBHOOK_URL)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("[DEBUG] Старый webhook удалён")
    except:
        pass

    await bot.set_webhook(WEBHOOK_URL)
    print("[DEBUG] Новый webhook установлен")

    if AUTO_TASK is None:
        print("[DEBUG] Запуск авто-аналитики")
        AUTO_TASK = asyncio.create_task(auto_signal_loop())

@app.on_event("shutdown")
async def on_shutdown():
    global AUTO_TASK
    print("[DEBUG] Остановка бота")

    if AUTO_TASK:
        AUTO_TASK.cancel()
        AUTO_TASK = None

    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}


        
