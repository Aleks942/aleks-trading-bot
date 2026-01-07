import os
import pandas as pd
import statistics


def _get_rb_params():
    test = os.getenv("RB_TEST", "0").strip() == "1"

    if test:
        return {
            "FLAT_CANDLES": 15,
            "MAX_RANGE_PCT": 4.0,
            "MIN_CANDLE_MOVE": 0.6,
            "MAX_CANDLE_MOVE": 5.0,
            "VOL_MULT": 1.2,
        }

    return {
        "FLAT_CANDLES": 20,
        "MAX_RANGE_PCT": 2.5,
        "MIN_CANDLE_MOVE": 1.2,
        "MAX_CANDLE_MOVE": 3.0,
        "VOL_MULT": 1.8,
    }


def range_breakout_5m(df: pd.DataFrame):
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

    last_close = float(last["close"])
    if last_close > high or last_close < low:
        return {
            "type": "RANGE_BREAKOUT",
            "range_pct": round(range_pct, 2),
            "candle_move": round(candle_move, 2),
            "volume_x": round(volume_x, 2),
        }

    return None


def wave3_setup(
    prices,
    volumes,
    impulse_min_pct=6.0,
    pullback_max=0.5,
    flat_max_range=2.5,
    flat_range_max=None,   # совместимость
    volume_mult=1.8,
    **_ignored,            # игнор лишних kwargs
):
    if flat_range_max is not None:
        flat_max_range = flat_range_max

    if prices is None or volumes is None:
        return None

    if len(prices) < 100 or len(volumes) < 100:
        return None

    base = prices[-90]
    peak = max(prices[-90:-50])
    if peak <= base or base == 0:
        return None

    impulse_pct = (peak - base) / base * 100.0
    if impulse_pct < impulse_min_pct:
        return None

    pullback_low = min(prices[-50:-30])
    denom = (peak - base)
    if denom <= 0:
        return None

    pullback_pct = (peak - pullback_low) / denom
    if pullback_pct > pullback_max:
        return None

    flat = prices[-30:]
    hi, lo = max(flat), min(flat)
    mid = (hi + lo) / 2.0
    if mid == 0:
        return None

    range_pct = abs((hi - lo) / mid * 100.0)
    if range_pct > flat_max_range:
        return None

    avg_vol = statistics.mean(volumes[-90:-30])
    last_vol = volumes[-1]
    if avg_vol <= 0:
        return None

    volume_x = last_vol / avg_vol
    if volume_x < volume_mult:
        return None

    return {
        "impulse_pct": round(impulse_pct, 2),
        "range_pct": round(range_pct, 2),
        "volume_x": round(volume_x, 2),
    }
