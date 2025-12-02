from core.datasource import get_ohlcv
from core.indicators import calculate_indicators
from core.divergence import detect_divergence
from core.moneyflow import analyze_moneyflow
from core.phases import detect_market_phase
from core.volatility import analyze_volatility


def analyze_symbol(symbol: str, tf: str):
    try:
        # 1. Получаем данные с бирж
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

        # Сбор причин
        reasons = []

        # Тренд
        if indi.get("trend") == "up":
            reasons.append("Тренд: восходящий (индикаторы)")
        elif indi.get("trend") == "down":
            reasons.append("Тренд: нисходящий (индикаторы)")
        else:
            reasons.append("Тренд: боковой")

        # Дивергенции
        if div.get("bullish"):
            reasons.append("Бычья дивергенция")
        if div.get("bearish"):
            reasons.append("Медвежья дивергенция")

        # Поток капитала
        if mf.get("moneyflow") == "in":
            reasons.append("Поток капитала входит")
        else:
            reasons.append("Поток капитала выходит")

        # Фаза
        reasons.append(f"Фаза рынка: {phase.get('phase')}")

        # Волатильность
        reasons.append(f"Волатильность: {vola.get('volatility')}")

        # Итоговый балл
        score = 0
        if indi.get("trend") == "up": score += 1
        if div.get("bullish"): score += 1
        if mf.get("moneyflow") == "in": score += 1

        if indi.get("trend") == "down": score -= 1
        if div.get("bearish"): score -= 1
        if mf.get("moneyflow") == "out": score -= 1

        if score >= 2:
            signal = "LONG"
        elif score <= -2:
            signal = "SHORT"
        else:
            signal = "NEUTRAL"

        strength = abs(score)

        return {
            "signal": signal,
            "strength": strength,
            "reasons": reasons
        }

    except Exception as e:
        return {"error": str(e)}
