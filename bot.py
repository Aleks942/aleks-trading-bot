import asyncio
import datetime
import pandas as pd

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import Router
from aiogram.filters import Command

from core.indicators import detect_impulse, detect_volume_spike
from core.divergence import find_rsi_divergence
from core.volatility import detect_volatility_breakout
from core.moneyflow import detect_money_flow_shift
from core.phases import detect_market_phase
from core.datasource import DataSource

TOKEN = 8173288900:AAH_XKitzdmIAryk-g7eko08yAcecgKkhlw
CHAT_ID = 851440772

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# =====================================================
# Загрузка данных с бирж через DataSource
# =====================================================

async def load_candles():
    ds = DataSource()
    df = ds.get_klines_bybit("BTCUSDT", "1h")
    return df


# =====================================================
# Команда /start
# =====================================================
@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Бот запущен! Я готов анализировать рынок и выдавать сигналы!")


# =====================================================
# Основная функция анализа
# =====================================================
async def analyze():
    df = await load_candles()
    if df is None:
        await bot.send_message(CHAT_ID, "Ошибка: нет данных с биржи.")
        return

    signals = []

    imp = detect_impulse(df)
    if imp:
        signals.append(f"🔥 Импульс: {imp}")

    vol_spike = detect_volume_spike(df)
    if vol_spike:
        signals.append(f"📈 Всплеск объёма: {vol_spike}")

    div = find_rsi_divergence(df)
    if div:
        signals.append(f"📉 Дивергенция: {div}")

    vola = detect_volatility_breakout(df)
    if vola:
        signals.append(f"📊 Волатильность: {vola}")

    mf = detect_money_flow_shift(df)
    if mf:
        signals.append(f"💰 MoneyFlow: {mf}")

    phase = detect_market_phase(df)
    if phase:
        signals.append(f"📍 Фаза рынка: {phase}")

    if signals:
        text = "📊 <b>Анализ рынка</b>:\n\n" + "\n".join(signals)
    else:
        text = "Сигналов пока нет."

    await bot.send_message(CHAT_ID, text)


# =====================================================
# Циклический запуск
# =====================================================
async def periodic():
    while True:
        await analyze()
        await asyncio.sleep(60)


# =====================================================
# Запуск бота
# =====================================================
async def main():
    asyncio.create_task(periodic())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())



