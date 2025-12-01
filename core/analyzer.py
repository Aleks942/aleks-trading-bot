import pandas as pd
from core.datasource import get_ohlcv
from core.indicators import (
    rsi, ema, macd, stochastic, bollinger,
    atr, adx, vwap, obv, momentum, roc, supertrend
)

def analyze_symbol(symbol: str = "BTCUSDT", timeframe: str = "1h"):

    # Загружаем свечи
    df = get_ohlcv(symbol, timeframe)

    # БЕЗОПАСНАЯ ЗАЩИТА (исправляет ошибку Length Mismatch)
    if df is None or df.empty or len(df) < 60:
        return {
            "error": "Недостаточно данных",
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": "NEUTRAL",
            "strength": 0,
            "reasons": ["Нет или мало данных (меньше 60 свечей)"]
        }

    # Индикаторы
    df["rsi"] = rsi(df["close"])
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)

    macd_line, signal_line, hist = macd(df["close"])
    df["macd_hist"] = hist

    df["stoch_k"], df["stoch_d"] = stochastic(df)
    df["middle_bb"], df["upper_bb"], df["lower_bb"] = bollinger(df["close"])
    df["atr"] = atr(df, 14)
    df["adx"] = adx(df, 14)
    df["vwap"] = vwap(df)
    df["obv"] = obv(df)
    df["momentum"] = momentum(df["close"], 10)
    df["roc"] = roc(df["close"], 12)
    df["supertrend"] = supertrend(df)

    last = df.iloc[-1]
    score = 0
    reasons = []

    # RSI
    if last["rsi"] < 30:
        score += 2
        reasons.append("RSI перепродан (лонг)")
    elif last["rsi"] > 70:
        score -= 2
        reasons.append("RSI перекуплен (шорт)")

    # EMA-тренд
    if last["ema20"] > last["ema50"]:
        score += 1
        reasons.append("EMA20 выше EMA50 (лонг)")
    else:
        score -= 1
        reasons.append("EMA20 ниже EMA50 (шорт)")

    # MACD
    if last["macd_hist"] > 0:
        score += 1
        reasons.append("MACD бычий")
    else:
        score -= 1
        reasons.append("MACD медвежий")

    # Supertrend
    if last["close"] > last["supertrend"]:
        score += 2
        reasons.append("Цена выше SuperTrend (лонг)")
    else:
        score -= 2
        reasons.append("Цена ниже SuperTrend (шорт)")

    # ADX
    if last["adx"] > 25:
        reasons.append("Сильный тренд (ADX > 25)")

    # OBV
    if len(df) >= 5:
        if last["obv"] > df["obv"].iloc[-5]:
            score += 1
            reasons.append("Рост объёмов (OBV)")
        else:
            reasons.append("OBV не растёт")
    else:
        reasons.append("Недостаточно данных для OBV")

    # Итоговый сигнал
    if score >= 3:
        signal = "LONG"
    elif score <= -3:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    # Финальный ответ
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal,
        "strength": score,
        "reasons": reasons
    }

