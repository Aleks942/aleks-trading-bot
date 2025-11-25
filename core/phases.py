import pandas as pd
import numpy as np


def atr(df, period=14):
    """ATR — волатильность рынка."""
    high_low = df.high - df.low
    high_close = np.abs(df.high - df.close.shift())
    low_close = np.abs(df.low - df.close.shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean()


def market_phase(df):
    """
    Возвращает фазу рынка:
    - consolidation  (флэт)
    - expansion      (начало движения)
    - trend_up       (тренд вверх)
    - trend_down     (тренд вниз)
    - exhaustion     (перегрев)
    """

    close = df.close
    ma_fast = close.rolling(20).mean()
    ma_slow = close.rolling(50).mean()

    atr_val = atr(df)

    # ФЛЭТ
    if atr_val.iloc[-1] < atr_val.mean() * 0.7:
        return "consolidation"

    # НАЧАЛО ДВИЖЕНИЯ
    if atr_val.iloc[-1] > atr_val.mean() * 1.2:
        return "expansion"

    # ТРЕНД ВВЕРХ
    if ma_fast.iloc[-1] > ma_slow.iloc[-1]:
        return "trend_up"

    # ТРЕНД ВНИЗ
    if ma_fast.iloc[-1] < ma_slow.iloc[-1]:
        return "trend_down"

    # ПЕРЕГРЕВ
    if abs(close.iloc[-1] - ma_fast.iloc[-1]) > atr_val.iloc[-1] * 2:
        return "exhaustion"

    return "consolidation"
