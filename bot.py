import asyncio
import datetime
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

from core.indicators import detect_impulse, detect_volume_spike
from core.divergence import find_rsi_divergence
from core.volatility import detect_volatility_breakout
from core.moneyflow import detect_money_flow_shift
from core.phases import detect_market_phase

TOKEN = "8473865365:AAH4biKKokz6Io23ZkqBuO7Q0HnzTdXCT9o"
CHAT_ID = "851440772"

bot = Bot(token=TOKEN)
dp = Dispatcher()


# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Бот запущен! Я готов анализировать рынок.")


# Симуляция свечей
def load_candles():
    data = {
        "close": [100 + i*0.5 for i in range(50)],
        "high":  [100 + i*0.6 for i in range(50)],
        "low":   [100 + i*0.4 for i in range(50)],
        "volume": [1000 + i*30 for i in range(50)]
    }
    return pd.DataFrame(data)


async def analyze():
    df = load_candles()
    signals = []

    imp = detect_impulse(df)
    if imp:
        signals.append(f"🔥 Импульс: {imp}")

    vol_spike = detect_volume_spike(df)
    if vol_spike:
        signals.append(f"📊 Объемный всплеск: {vol_spike}")

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

    if not signals:
        message = "Сигналов пока нет."
    else:
        message = "\n".join(signals)

    await bot.send_message(CHAT_ID, f"📈 Анализ рынка:\n\n{message}")


async def main():
    asyncio.create_task(periodic_task())
    await dp.start_polling(bot)


async def periodic_task():
    while True:
        await analyze()
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())

