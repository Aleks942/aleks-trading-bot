import pandas as pd
from core.datasource import get_ohlcv
from core.divergence import calculate_divergence
from core.impulse import detect_impulse
from core.indicators import rsi, ema
from core.phases import market_phase
from core.volatility import volatility_level
from core.moneyflow import money_flow_index


def analyze_symbol(symbol: str = "BTCUSDT", timeframe: str = "1h"):
    """
    Главный анализатор. Собирает все данные и делает общий вывод.
    """

    # 1. Берём данные OHLCV
    df = get_ohlcv(symbol, timeframe)
    if df is None or len(df) < 50:
        return {"error": "недостаточно данных"}

    # 2. Индикаторы
    df["rsi"] = rsi(df["close"])
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["mfi"] = money_flow_index(df)

    # 3. Импульсы
    impulse = detect_impulse(df)

    # 4. Дивергенции
    diverg = calculate_divergence(df)

    # 5. Фазы рынка
    phase = market_phase(df)

    # 6. Волатильность
    vol = volatility_level(df)

    # 7. Итоговый вывод
    signal_strength = 0
    reasons = []

    if impulse == "bullish":
        signal_strength += 2
        reasons.append("Импульс вверх")

    if diverg == "bullish":
        signal_strength += 2
        reasons.append("Бычья дивергенция")

    if df["rsi"].iloc[-1] < 30:
        signal_strength += 1
        reasons.append("RSI перепродан")

    if df["close"].iloc[-1] > df["ema20"].iloc[-1] > df["ema50"].iloc[-1]:
        signal_strength += 1
        reasons.append("Цена выше EMA → тренд вверх")

    if vol == "high":
        reasons.append("Высокая волатильность (осторожно)")

    # Финальная классификация:
    if signal_strength >= 4:
        final = "STRONG BUY"
    elif 2 <= signal_strength < 4:
        final = "BUY"
    elif -1 <= signal_strength < 2:
        final = "NEUTRAL"
    else:
        final = "SELL"

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": final,
        "strength": signal_strength,
        "reasons": reasons,
        "phase": phase,
        "volatility": vol
    }
