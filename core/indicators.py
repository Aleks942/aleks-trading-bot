import pandas as pd
import numpy as np


def EMA(series, period):
    """Exponential Moving Average"""
    return series.ewm(span=period).mean()


def SMA(series, period):
    """Simple Moving Average"""
    return series.rolling(period).mean()


def volume_spike(df, multiplier=1.8):
    """Обнаружение всплеска объема"""
    last = df.volume.iloc[-1]
    avg = df.volume.iloc[-20:].mean()
    return last > avg * multiplier


def candle_range(df):
    """Диапазон свечи"""
    return df.high - df.low


def volatility(df, period=20):
    """Стандартное отклонение цены"""
    return df.close.rolling(period).std().iloc[-1]


def long_wick(df):
    """Проверка длинного хвоста"""
    c = df.close.iloc[-1]
    h = df.high.iloc[-1]
    l = df.low.iloc[-1]

    upper = h - max(c, df.open.iloc[-1])
    lower = min(c, df.open.iloc[-1]) - l

    if upper > (h - l) * 0.5:
        return "upper"
    if lower > (h - l) * 0.5:
        return "lower"
    return None


def body_size(df):
    """Размер тела свечи"""
    return abs(df.close.iloc[-1] - df.open.iloc[-1])
