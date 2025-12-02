from core.datasource import get_ohlcv
from core.indicators import calculate_indicators
from core.divergence import detect_divergence
from core.moneyflow import analyze_moneyflow
from core.phases import detect_market_phase
from core.volatility import analyze_volatility


def analyze_symbol(symbol: str, tf: str):
    try:
        # 1. Получаем OHLCV данные
        df = get_ohlcv(symbol, tf)
        if df is None or len(df) < 30:
            return {"error": "Недостаточно данных"}

        # 2. Индикаторы
        indi = calculate_indicators(df)

        # 3. Дивергенции
        div = detect_divergence(df)

        # 4. Денежный поток
        mf = analyze_moneyflow(df)

        # 5. Фаза рынка
        phase = detect_market_phase(df)

        # 6. Волатильность
        vola = analyze_volatility(df)

        # -----------------------------------------------------
        # Формируем причины (для Telegram)
        # -----------------------------------------------------
        reasons = []

        # Тренд
        if indi["trend"] == "up":
            reasons.append("Тренд: восходящий (EMA20 > EMA50)")
        elif indi["trend"] == "down":
            reasons.append("Тренд: нисходящий (EMA20 < EMA50)")
        else:
            reasons.append("Тренд: боковой")

        # MACD
        if indi["macd_hist"] > 0:
            reasons.append("MACD: бычий импульс")
        else:
            reasons.append("MACD: медвежий импульс")

        # RSI
        if indi["rsi"] > 60:
            reasons.append("RSI показывает покупку")
        elif indi["rsi"] < 40:
            reasons.append("RSI показывает продажу")
        else:
            reasons.append("RSI нейтральный")

        # Supertrend
        if indi["supertrend"] < df["close"].iloc[-1]:
            reasons.append("SuperTrend: рынок над линией (бычий)")
        else:
            reasons.append("SuperTrend: рынок под линией (медвежий)")

        # Дивергенции
        if div.get("bullish"):
            reasons.append("Обнаружена бычья дивергенция")
        if div.get("bearish"):
            reasons.append("Обнаружена медвежья дивергенция")

        # Денежный поток
        if mf["direction"] == "in":
            reasons.append("Капитал входит в рынок")
        elif mf["direction"] == "out":
            reasons.append("Капитал выходит из рынка")
        else:
            reasons.append("Денежный поток нейтрален")

        # VWAP
        if mf["price_vs_vwap"] == "above":
            reasons.append("Цена выше VWAP → покупатели сильнее")
        else:
            reasons.append("Цена ниже VWAP → продавцы сильнее")

        # Фаза рынка
        reasons.append(f"Фаза рынка: {phase.get('phase', 'неизвестно')}")

        # Волатильность
        reasons.append(f"Волатильность: {vola.get('volatility', 'нет данных')}")

        # -----------------------------------------------------
        # Считаем итоговый сигнал
        # -----------------------------------------------------
        score = 0

        if indi["trend"] == "up": score += 1
        if indi["macd_hist"] > 0: score += 1
        if indi["rsi"] > 55: score += 1
        if indi["supertrend"] < df["close"].iloc[-1]: score += 1
        if mf["direction"] == "in": score += 1

        if indi["trend"] == "down": score -= 1
        if indi["macd_hist"] < 0: score -= 1
        if indi["rsi"] < 45: score -= 1
        if indi["supertrend"] > df["close"].iloc[-1]: score -= 1
        if mf["direction"] == "out": score -= 1

        if score >= 2:
            signal = "LONG"
        elif score <= -2:
            signal = "SHORT"
            signal = "SHORT"
        else:
            signal = "NEUTRAL"

        return {
            "signal": signal,
            "strength": abs(score),
            "reasons": reasons
        }

    except Exception as e:
        return {"error": str(e)}
