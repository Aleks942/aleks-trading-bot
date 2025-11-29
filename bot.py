import asyncio
import pandas as pd

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import Router
from aiogram.filters import Command

from core.datasource import DataSource
from core.indicators import detect_impulse, detect_volume_spike
from core.divergence import find_rsi_divergence
from core.volatility import detect_volatility_breakout
from core.moneyflow import detect_money_flow_shift
from core.phases import detect_market_phase


TOKEN = 8473865365:AAH4biKKokz6Io23ZkqBu07Q0HnzTdXCT9o

CHAT_ID = 851440772

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# Инициализация источника данных
ds = DataSource()


# Команда /start
@router.message(Command("start"))
async def start_handler(message):
    await message.answer("Бот запущен! Анализ рынка каждые 60 секунд.")


# Функция анализа рынка
async def analyze():
    # Загружаем данные с биржи
    df = ds.get_klines_bybit("BTCUSDT", "15")  
    # Если данных нет
    if df is None or len(df) < 50:
        await bot.send_message(CHAT_ID, "Ошибка получения данных.")
        return

    signals = []

    # Индикаторы
    imp = detect_impulse(df)
    if imp:
        signals.append(f"🔥 Импульс: {imp}")

    vol_spike = detect_volume_spike(df)
    if vol_spike:
        signals.append(f"📊 Всплеск объёмов: {vol_spike}")

    div = find_rsi_divergence(df)
    if div:
        signals.append(f"🔃 Дивергенция: {div}")

    vola = detect_volatility_breakout(df)
    if vola:
        signals.append(f"📈 Волатильность: {vola}")

    mf = detect_money_flow_shift(df)
    if mf:
        signals.append(f"💰 MoneyFlow: {mf}")

    phase = detect_market_phase(df)
    if phase:
        signals.append(f"🌓 Фаза рынка: {phase}")

    # Отправка результата
    if signals:
        text = "📡 <b>Анализ рынка:</b>\n\n" + "\n".join(signals)
    else:
        text = "Сигналов пока нет."

    await bot.send_message(CHAT_ID, text)


# Периодическая задача
async def periodic_task():
    while True:
        await analyze()
        await asyncio.sleep(60)


# Запуск
async def main():
    asyncio.create_task(periodic_task())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())



