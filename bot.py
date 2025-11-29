import asyncio
import datetime
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from core.indicators import (
    detect_impulse,
    detect_volume_spike,
    detect_volatility_breakout,
    detect_money_flow_shift,
    detect_market_phase
)

TOKEN = "8473865365:AAH4biKKokz6Io23ZkqBuO7Q0HnzTdXCT9o"
CHAT_ID = 851440772

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Бот запущен! Я готов анализировать рынок.")


def load_candles():
    data = {
        "close": [100 + i * 0.5 for i in range(50)],
        "high":  [100 + i * 0.6 for i in range(50)],
        "low":   [100 + i * 0.4 for i in range(50)],
        "volume": [1000 + i * 30 for i in range(50)]
    }
    return pd.DataFrame(data)


async def analyze():
    df = load_candles()
    signals = []

  imp = None

    if imp:
        signals.append(f"🔥 Импульс: {imp}")

    vol_spike = detect_volume_spike(df)
    if vol_spike:
        signals.append(f"📊 Всплеск объёмов: {vol_spike}")

    div = find_rsi_divergence(df)
    if div:
        signals.append(f"📉 Дивергенция: {div}")

    vola = detect_volatility_breakout(df)
    if vola:
        signals.append(f"⚡ Волатильность: {vola}")

    mf = detect_money_flow_shift(df)
    if mf:
        signals.append(f"💰 MoneyFlow: {mf}")

    phase = detect_market_phase(df)
    if phase:
        signals.append(f"📌 Фаза рынка: {phase}")

    if signals:
        text = "📈 Анализ рынка:\n\n" + "\n".join(signals)
    else:
        text = "Сигналов пока нет."

    await bot.send_message(CHAT_ID, text)


async def periodic_task():
    while True:
        await analyze()
        await asyncio.sleep(60)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(periodic_task())
    executor.start_polling(dp, skip_updates=True)
