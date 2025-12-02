import pandas as pd

def detect_market_phase(df):
    """
    Определяем фазу рынка:
    - uptrend
    - downtrend
    - accumulation
    - distribution
    """

    close = df["close"]

    # Скользящие средние
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()

    last = len(close) - 1

    # Тренд вверх
    if sma20.iloc[last] > sma50.iloc[last]:
        return "uptrend"

    # Тренд вниз
    if sma20.iloc[last] < sma50.iloc[last]:
        return "downtrend"

    # Боковик / накопление
    if abs(sma20.iloc[last] - sma50.iloc[last]) / close.iloc[last] < 0.01:
        return "accumulation"

    return "distribution"
