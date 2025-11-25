import numpy as np
import pandas as pd


def atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean()


def volatility_state(df):
    """
    Определяет состояние волатильности:
    - low      -> рынок сжат (готовится к импульсу)
    - medium   -> нормальная волатильность
    - high     -> рынок опасен, широкие свечи
    - extreme  -> хаос, лучше не торговать
    """

    atr_val = atr(df)
    last_atr = atr_val.iloc[-1]
    avg_atr = atr_val.mean()

    if last_atr < avg_atr * 0.7:
        return "low"         # сжатие → скоро импульс

    if last_atr < avg_atr * 1.2:
        return "medium"      # нормальный рынок

    if last_atr < avg_atr * 2:
        return "high"        # усиление волатильности

    return "extreme"         # хаос → НЕ входить


def volatility_expansion(df):
    """
    Определяет момент начала расширения (импульса).
    """

    atr_val = atr(df)
    if atr_val.iloc[-1] > atr_val.iloc[-2] * 1.2:
        return True  # резкое расширение диапазона
    return False


def safe_stop_range(df):
    """
    Рассчитывает безопасный диапазон стопа.
    """

    a = atr(df)
    stop = a.iloc[-1] * 1.5   # рекомендованный диапазон
    return stop
