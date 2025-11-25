import asyncio
import datetime
import pandas as pd
from aiogram import Bot, Dispatcher

# Импорт модулей
from core.indicators import detect_impulse, detect_volume_spike
from core.divergence import find_rsi_divergence
from core.volatility import detect_volatility_breakout
from core.moneyflow import detect_money_flow_shift
from core.phases import detect_market_phase

# TOKEN твоего бота
TOKEN = "8473865365:AAH4biKKokz6Io23ZKqBuO70Q0HnzTdXCT9o"
CHAT_ID = "851440772"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Заглушка – данные свечей (позже подключим биржу)
def load_candles():
    data = {
        "close": [100 + i*0.5 for i in range(50)],
        "high": [100 + i*0.6 for i in range(50)],
        "low":  [100 + i*0.4 for i in range(50)],
        "volume": [1000 + i*30 for i in range(50)]
    }
    return pd.DataFrame(data)

# ---------------------------- АНАЛИЗ ----------------------------
async def analyze():
    df = load_candles()
    signals = []

    # Импульсы
    imp = detect_impulse(df)
    if imp:
        signals.append(f"🔥 Импульс: {imp}")

    # Объёмный всплеск
    vol_spike = detect_volume_spike(df)
    if vol_spike:
        signals.append(f"📊 Объёмный всплеск: {vol_spike}")

    # Дивергенции
    div = find_rsi_divergence(df)
    if div:
        signals.append(f"⚠️ Дивергенция: {div}")

    # Волатильность
    vola = detect_volatility_breakout(df)
    if vola:
        signals.append(f"📉 Волатильность: {vola}")

    # Денежный поток
    mf = detect_money_flow_shift(df)
    if mf:
        signals.append(f"💰 MoneyFlow: {mf}")

    # Рыночные фазы
    phase = detect_market_phase(df)
    if phase:
        signals.append(f"📌 Фаза рынка: {phase}")

    # Итоговое сообщение
    if not signals:
        message = "Сигналов пока нет."
    else:
        message = "\n".join(signals)

    await bot.send_message(CHAT_ID, f"📈 Анализ рынка:\n\n{message}")

# ---------------------------- ЦИКЛ ----------------------------
async def main():
    while True:
        await analyze()
        await asyncio.sleep(60)  # анализ каждые 60 секунд

if __name__ == "__main__":
    asyncio.run(main())
