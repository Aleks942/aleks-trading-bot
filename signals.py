def wave3_setup(
    prices,
    volumes,
    impulse_min_pct=6.0,
    pullback_max=0.5,
    flat_max_range=2.5,
    volume_mult=1.8
):
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
    if impulse_pct < impulse_min_pct:
        return None

    # ---- откат ----
    pullback_low = min(prices[-50:-30])
    pullback_pct = (peak - pullback_low) / (peak - base)

    if pullback_pct > pullback_max:
        return None

    # ---- флет ----
    flat = prices[-30:]
    hi, lo = max(flat), min(flat)
    mid = (hi + lo) / 2
    if mid == 0:
        return None

    range_pct = abs((hi - lo) / mid * 100)
    if range_pct > flat_max_range:
        return None

    # ---- объём ----
    avg_vol = statistics.mean(volumes[-90:-30])
    last_vol = volumes[-1]

    if avg_vol == 0 or last_vol / avg_vol < volume_mult:
        return None

    return {
        "impulse_pct": round(impulse_pct, 2),
        "range_pct": round(range_pct, 2),
        "volume_x": round(last_vol / avg_vol, 2)
    }
