def range_breakout_5m(candles):
    """
    candles: pandas DataFrame
    columns: open, high, low, close, volume
    TF: 5m (аппроксимация, если данные не свечные)
    """

    if candles is None or len(candles) < 21:
        return None

    range_candles = candles.iloc[-21:-1]  # 20 свечей флета
    last = candles.iloc[-1]

    high = range_candles["high"].max()
    low = range_candles["low"].min()

    if low == 0:
        return None

    range_pct = (high - low) / low * 100

    # 1) флет ≤ 2.5%
    if range_pct > 2.5:
        return None

    # 2) параметры пробоя
    if last["open"] == 0:
        return None

    candle_move = (last["close"] - last["open"]) / last["open"] * 100
    avg_volume = range_candles["volume"].mean()

    if not avg_volume or avg_volume <= 0:
        return None

    # Пробой вверх: close выше верхней границы + свеча >= 1.2% + объём >= x1.8
    if (
        last["close"] > high
        and candle_move >= 1.2
        and last["volume"] >= avg_volume * 1.8
    ):
        return {
            "type": "RANGE_BREAKOUT",
            "tf": "5m",
            "range_pct": round(range_pct, 2),
            "candle_move": round(candle_move, 2),
            "volume_x": round(last["volume"] / avg_volume, 2),
        }

    return None
