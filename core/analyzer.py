import pandas as pd
from core.datasource import get_ohlcv
from core.indicators import (
    rsi, ema, macd, stochastic, bollinger,
    atr, adx, vwap, obv, momentum, roc, supertrend
)

def analyze_symbol(symbol: str = "BTCUSDT", timeframe: str = "1h"):

    df = get_ohlcv(symbol, timeframe)
    if df is None or len(df) < 60:
        return {"error": "Недостаточно данных"}

    # -----------------------------------------------------
    # Индикаторы высокого уровня
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Оценка сигналов
    # -----------------------------------------------------

    last = df.iloc[-1]
    reasons = []
    score = 0

    # RSI
    if last["rsi"] < 30:
        score += 2
        reasons.append("RSI перепродан (лонг)")
    elif last["rsi"] > 70:
        score -= 2
        reasons.append("RSI перекуплен (шорт)")

    # EMA20 / EMA50
    if last["ema20"] > last["ema50"]:
        score += 1
        reasons.append("EMA20 выше EMA50 (лонг тренд)")
    else:
        score -= 1
        reasons.append("EMA20 ниже EMA50 (шорт тренд)")

    # MACD
    if last["macd_hist"] > 0:
        score += 1
        reasons.append("MACD бычий")
    else:
        score -= 1
        reasons.append("MACD медвежий")

    # SuperTrend
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
    if last["obv"] > df["obv"].iloc[-5]:
        score += 1
        reasons.append("Поток объема вверх")

    # Вывод направления
    if score >= 3:
        signal = "LONG"
        # -----------------------------------------------------
    # Оценка сигналов (Исправленная секция)
    # -----------------------------------------------------

    last = df.iloc[-1]
    reasons = []
    score = 0

    # ... (Весь остальной код проверок RSI, EMA, MACD, SuperTrend, ADX остается без изменений) ...
    # ... 

    # ADX
    if last["adx"] > 25:
        reasons.append("Сильный тренд (ADX > 25)")

    # OBV (ИСПРАВЛЕННАЯ ПРОВЕРКА)
    # Сначала убедимся, что у нас есть достаточно данных (минимум 5 строк), 
    # прежде чем обращаться к df.iloc[-5]
    if len(df) >= 5:
        if last["obv"] > df["obv"].iloc[-5]:
            score += 1
            reasons.append("Поток объема вверх")
    else:
        # Если данных меньше 5 строк, мы просто пропускаем эту проверку, 
        # чтобы избежать ошибки "Length mismatch"
        reasons.append("Недостаточно данных для анализа OBV за 5 периодов.")

    # Вывод направления
    if score >= 3:
        signal = "LONG"
# ... (Остальная часть кода остается без изменений) ...

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal,
        "strength": score,
        "reasons": reasons
    }
