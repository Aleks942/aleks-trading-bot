import pandas as pd

def range_breakout_5m(df: pd.DataFrame):
    """
    Range → Breakout (5m)
    INFO ONLY — не вход

    df columns:
    open, high, low, close, volume
    """

    if df is None or len(df) < 20:
        return None

    # параметры
    FLAT_CANDLES = 20
    MAX_RANGE_PCT = 2.5
    MIN_CANDLE_MOVE = 1.2
    MAX_CANDLE_MOVE = 3.0      # фильтр "не после +3%"
    VOL_MULT = 1.8

    recent = df.iloc[-FLAT_CANDLES:]
    high = recent["high"].max()
    low = recent["low"].min()
    mid = (high + low) / 2

    if mid == 0:
        return None

    range_pct = (high - low) / mid * 100

    # это не флет
    if range_pct > MAX_RANGE_PCT:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # движение последней свечи
    candle_move = abs((last["close"] - prev["close"]) / prev["close"] * 100)

    if candle_move < MIN_CANDLE_MOVE or candle_move > MAX_CANDLE_MOVE:
        return None

    avg_volume = recent["volume"].mean()
    if avg_volume <= 0:
        return None

    volume_x = last["volume"] / avg_volume

    if volume_x < VOL_MULT:
        return None

    # пробой вверх или вниз
    if last["close"] > high or last["close"] < low:
        return {
            "type": "RANGE_BREAKOUT",
            "range_pct": round(range_pct, 2),
            "candle_move": round(candle_move, 2),
            "volume_x": round(volume_x, 2),
        }

    return None
