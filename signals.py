import os
import pandas as pd


def _get_rb_params():
    """
    Переключение режима без правки кода:
    RB_TEST=1  -> ослабленные параметры (для контрольного теста)
    RB_TEST=0  -> боевые параметры (наш план)
    """
    test = os.getenv("RB_TEST", "0").strip() == "1"

    if test:
        # TEST — чтобы быстрее увидеть 🔵 и подтвердить, что канал работает
        return {
            "FLAT_CANDLES": 15,
            "MAX_RANGE_PCT": 4.0,
            "MIN_CANDLE_MOVE": 0.6,
            "MAX_CANDLE_MOVE": 5.0,
            "VOL_MULT": 1.2,
        }

    # PROD — боевые параметры по договорённости
    return {
        "FLAT_CANDLES": 20,
        "MAX_RANGE_PCT": 2.5,
        "MIN_CANDLE_MOVE": 1.2,
        "MAX_CANDLE_MOVE": 3.0,  # фильтр "не после +3%"
        "VOL_MULT": 1.8,
    }


def range_breakout_5m(df: pd.DataFrame):
    """
    Range → Breakout (5m)
    INFO ONLY — не вход

    Ожидаемые колонки:
    open, high, low, close, volume
    """
    if df is None or len(df) < 21:
        return None

    p = _get_rb_params()

    flat_candles = int(p["FLAT_CANDLES"])
    max_range_pct = float(p["MAX_RANGE_PCT"])
    min_candle_move = float(p["MIN_CANDLE_MOVE"])
    max_candle_move = float(p["MAX_CANDLE_MOVE"])
    vol_mult = float(p["VOL_MULT"])

    if len(df) < flat_candles + 1:
        return None

    recent = df.iloc[-flat_candles:]

    high = float(recent["high"].max())
    low = float(recent["low"].min())
    mid = (high + low) / 2.0
    if mid == 0:
        return None

    range_pct = (high - low) / mid * 100.0
    if range_pct > max_range_pct:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    prev_close = float(prev["close"])
    if prev_close == 0:
        return None

    candle_move = abs((float(last["close"]) - prev_close) / prev_close * 100.0)
    if candle_move < min_candle_move or candle_move > max_candle_move:
        return None

    avg_volume = float(recent["volume"].mean())
    if avg_volume <= 0:
        return None

    volume_x = float(last["volume"]) / avg_volume
    if volume_x < vol_mult:
        return None

    # Пробой диапазона (вверх/вниз)
    last_close = float(last["close"])
    if last_close > high or last_close < low:
        return {
            "type": "RANGE_BREAKOUT",
            "range_pct": round(range_pct, 2),
            "candle_move": round(candle_move, 2),
            "volume_x": round(volume_x, 2),
        }

    return None
import statistics

def wave3_setup(prices, volumes):
    """
    INFO-сигнал: подготовка к 3-й волне.
    НЕ вход.
    """

    if prices is None or volumes is None:
        return None

    if len(prices) < 100:
        return None

    # ---- 1-я волна (импульс) ----
    base = prices[-90]
    peak = max(prices[-90:-50])

    if peak <= base:
        return None

    impulse_pct = (peak - base) / base * 100
    if impulse_pct < 6:
        return None

    # ---- откат ----
    pullback_low = min(prices[-50:-30])
    pullback_pct = (peak - pullback_low) / (peak - base)

    if pullback_pct > 0.5:
        return None

    # ---- флет после отката ----
    flat = prices[-30:]
    hi, lo = max(flat), min(flat)
    mid = (hi + lo) / 2

    range_pct = abs((hi - lo) / mid * 100)
    if range_pct > 2.5:
        return None

    # ---- объём ----
    avg_vol = statistics.mean(volumes[-90:-30])
    last_vol = volumes[-1]

    if avg_vol == 0 or last_vol / avg_vol < 1.8:
        return None

    return {
        "impulse_pct": round(impulse_pct, 2),
        "range_pct": round(range_pct, 2),
        "volume_x": round(last_vol / avg_vol, 2)
    }
