# Пробой вверх: close выше верхней границы + свеча >= 1.2% + объём >= x1.8
# ФИЛЬТР: не после +3%
if (
    last["close"] > high
    and candle_move >= 1.2
    and candle_move <= 3.0      # <-- ВАЖНО: не после +3%
    and last["volume"] >= avg_volume * 1.8
):
    return {
        "type": "RANGE_BREAKOUT",
        "tf": "5m",
        "range_pct": round(range_pct, 2),
        "candle_move": round(candle_move, 2),
        "volume_x": round(last["volume"] / avg_volume, 2),
    }
