import pandas as pd
import numpy as np

# ==========================
#   СКОЛЬЗЯЩИЕ СРЕДНИЕ
# ==========================

def EMA(series, period):
    """Exponential Moving Average"""
    return series.ewm(span=period).mean()

def SMA(series, period):
    """Simple Moving Average"""
    return series.rolling(period).mean()


# ==========================
#   ИНДИКАТОР: "ИМПУЛЬС"
# ==========================

def detect_impulse(df, threshold=1.5):
    """
    Выявление импульса по изменению цены
    threshold — процент изменения (1.5 = 1.5%)
    """
    last = df.close.iloc[-1]
    prev = df.close.iloc[-2]
    change = (last - prev) / prev * 100

    if abs(change) >= threshold:
        return round(change, 2)

    return None


# ==========================
#   ВСПЛЕСК ОБЪЁМА
# ==========================

def detect_volume_spike(df, multiplier=1.8):
    """
    Обнаружение всплеска объёма
    multiplier — коэффициент отклонения
    """
    last = df.volume.iloc[-1]
    avg = df.volume.iloc[-20:].mean()

    if last > avg * multiplier:
        return int(last)

    return None


# ==========================
#   ДЛИННЫЙ ХВОСТ
# ==========================

def long_wick(df):
    """Проверка длинного хвоста"""
    c = df.close.iloc[-1]
    h = df.high.iloc[-1]
    l = df.low.iloc[-1]
    o = df.open.iloc[-1]

    upper = h - max(c, o)
    lower = min(c, o) - l

    if upper > (h - l) * 0.5:
        return "upper"

    if lower > (h - l) * 0.5:
        return "lower"

    return None


# ==========================
#   ОТКЛОНЕНИЕ (волатильность)
# ==========================

def detect_volatility_breakout(df, period=20, multiplier=2):
    """
    Пробой волатильности: цена выходит за пределы std * multiplier
    """
    std = df.close.rolling(period).std().iloc[-1]
    avg = df.close.rolling(period).mean().iloc[-1]
    last = df.close.iloc[-1]

    if last > avg + std * multiplier:
        return "up"

    if last < avg - std * multiplier:
        return "down"

    return None


# ==========================
#   MONEY FLOW SHIFT
# ==========================

def detect_money_flow_shift(df):
    """
    Money Flow = (close - low) / (high - low)
    """
    h = df.high.iloc[-1]
    l = df.low.iloc[-1]
    c = df.close.iloc[-1]

    if h == l:
        return None

    mf = (c - l) / (h - l)

    if mf > 0.7:
        return "buy"

    if mf < 0.3:
        return "sell"

    return None


# ==========================
#   ФАЗА РЫНКА
# ==========================

def detect_market_phase(df):
    """
    Определение фазы рынка по EMA
    """
    ema_fast = EMA(df.close, 20).iloc[-1]
    ema_slow = EMA(df.close, 50).iloc[-1]

    if ema_fast > ema_slow:
        return "bull"

    if ema_fast < ema_slow:
        return "bear"

    return "flat"

