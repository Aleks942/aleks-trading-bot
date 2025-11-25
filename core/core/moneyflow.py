import pandas as pd
import numpy as np


def mfi(df, period=14):
    """Money Flow Index"""
    typical_price = (df.high + df.low + df.close) / 3
    money_flow = typical_price * df.volume

    positive_flow = []
    negative_flow = []

    for i in range(1, len(typical_price)):
        if typical_price.iloc[i] > typical_price.iloc[i - 1]:
            positive_flow.append(money_flow.iloc[i])
            negative_flow.append(0)
        else:
            positive_flow.append(0)
            negative_flow.append(money_flow.iloc[i])

    pos_mf = pd.Series(positive_flow).rolling(period).sum()
    neg_mf = pd.Series(negative_flow).rolling(period).sum()

    mfi = 100 - (100 / (1 + pos_mf / neg_mf))
    return mfi


def vwap(df):
    """VWAP — средневзвешенная цена по объёму"""
    tp = (df.high + df.low + df.close) / 3
    vwap = (tp * df.volume).cumsum() / df.volume.cumsum()
    return vwap


def money_pressure(df, period=20):
    """
    Возвращает давление покупателей/продавцов:
    - positive → покупатели доминируют
    - negative → продавцы доминируют
    - neutral → равновесие
    """

    vol = df.volume
    close = df.close

    flow = (close.diff() * vol).rolling(period).sum()

    if flow.iloc[-1] > 0:
        return "positive"
    elif flow.iloc[-1] < 0:
        return "negative"
    else:
        return "neutral"


def moneyflow_signal(df):
    """
    Интегрированный сигнал:
    - buy_signal
    - sell_signal
    - weak_buy
    - weak_sell
    - neutral
    """

    mfi_val = mfi(df).iloc[-1]
    vwap_val = vwap(df).iloc[-1]
    price = df.close.iloc[-1]
    mp = money_pressure(df)

    # Сильный сигнал на покупку
    if mfi_val > 60 and price > vwap_val and mp == "positive":
        return "buy_signal"

    # Сильный сигнал на продажу
    if mfi_val < 40 and price < vwap_val and mp == "negative":
        return "sell_signal"

    # Слабые сигналы
    if mfi_val > 50 and price > vwap_val:
        return "weak_buy"

    if mfi_val < 50 and price < vwap_val:
        return "weak_sell"

    return "neutral"
