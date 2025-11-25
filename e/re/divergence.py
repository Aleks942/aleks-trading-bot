import numpy as np
import pandas as pd


def RSI(series, period=14):
    """Стандартный RSI"""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)

    ma_up = up.rolling(period).mean()
    ma_down = down.rolling(period).mean()

    rsi = 100 - (100 / (1 + ma_up / ma_down))
    return rsi


def OBV(df):
    """On-Balance Volume"""
    obv = [0]
    for i in range(1, len(df)):
        if df.close.iloc[i] > df.close.iloc[i - 1]:
            obv.append(obv[-1] + df.volume.iloc[i])
        elif df.close.iloc[i] < df.close.iloc[i - 1]:
            obv.append(obv[-1] - df.volume.iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=df.index)


def detect_divergence(df):
    """
    Возвращает:
    - 'bullish' — бычья дивергенция
    - 'bearish' — медвежья дивергенция
    - None — нет сигнала
    """

    close = df.close
    rsi = RSI(close)
    obv = OBV(df)

    # проверяем последние 5 свечей
    window = 5

    # цена делает минимум, индикаторы растут → бычья дивергенция
    price_low = close.iloc[-window:].min()
    rsi_low = rsi.iloc[-window:].min()
    obv_low = obv.iloc[-window:].min()

    if close.iloc[-1] < price_low * 1.01 and rsi.iloc[-1] > rsi_low and obv.iloc[-1] > obv_low:
        return "bullish"

    # цена делает максимум, индикаторы падают → медвежья дивергенция
    price_high = close.iloc[-window:].max()
    rsi_high = rsi.iloc[-window:].max()
    obv_high = obv.iloc[-window:].max()

    if close.iloc[-1] > price_high * 0.99 and rsi.iloc[-1] < rsi_high and obv.iloc[-1] < obv_high:
        return "bearish"

    return None
