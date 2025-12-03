from core.datasource import get_ohlcv
from core.indicators import calculate_indicators
from core.divergence import detect_divergence
from core.moneyflow import analyze_moneyflow
from core.phases import detect_market_phase
from core.volatility import analyze_volatility


def safe_dict(x):
    if isinstance(x, dict):
        return x
    return {}


def analyze_symbol(symbol: str, tf: str):
    try:
        # 1. Данные
        df = get_ohlcv(symbol, tf)
        if df is None or len(df) < 20:
            return {"error": "Недостаточно данных"}

        # 2. Модули (ЖЁСТКАЯ ЗАЩИТА)
        indi = safe_dict(calculate_indicators(df))
        div = safe_dict(detect_divergence(df))
        mf = safe_dict(analyze_moneyflow(df))
        phase = safe_dict(detect_market_phase(df))
        vola = safe_dict(analyze_volatility(df))

        # 3. Причины
        reasons = []

        # Тренд
        if indi.get("trend") == "up":
            reasons.append("Тренд: восходящий (EMA20 > EMA50)")
        elif indi.get("trend") == "down":
            reasons.append("Тренд: нисходящий (EMA20 < EMA50)")
        else:
            reasons.append("Тренд: боковой")

        # MACD
        try:
            macd_hist = float(indi.get("macd_hist", 0))
        except Exception:
            macd_hist = 0

        if macd_hist > 0:
            reasons.append("MACD: бычий импульс")
        else:
            reasons.append("MACD: медвежий импульс")

        # RSI
        try:
            rsi = float(indi.get("rsi", 50))
        except Exception:
            rsi = 50

        if rsi > 60:
            reasons.append("RSI показывает покупку")
        elif rsi < 40:
            reasons.append("RSI показывает продажу")
        else:
            reasons.append("RSI нейтральный")

        # SuperTrend
        try:
            supertrend = float(indi.get("supertrend", 0))
            last_price = float(df["close"].iloc[-1])
        except Exception:
            supertrend = 0
            last_price = 0

        if supertrend < last_price:
            reasons.append("SuperTrend: рынок над линией (бычий)")
        else:
            reasons.append("SuperTrend: рынок под линией (медвежий)")

        # Дивергенции
        if div.get("bullish"):
            reasons.append("Обнаружена бычья дивергенция")
        if div.get("bearish"):
            reasons.append("Обнаружена медвежья дивергенция")

        # Денежный поток
        if mf.get("direction") == "in":
            reasons.append("Капитал входит в рынок")
        elif mf.get("direction") == "out":
            reasons.append("Капитал выходит из рынка")
        else:
            reasons.append("Денежный поток нейтрален")

        # VWAP
        if mf.get("price_vs_vwap") == "above":
            reasons.append("Цена выше VWAP → покупатели сильнее")
        elif mf.get("price_vs_vwap") == "below":
            reasons.append("Цена ниже VWAP → продавцы сильнее")

        # Фаза рынка
        reasons.append(f"Фаза рынка: {phase.get('phase', 'неизвестно')}")

        # Волатильность
        reasons.append(f"Волатильность: {vola.get('volatility', 'нет данных')}")

        # 4. Итоговый скоринг
        score = 0

        if indi.get("trend") == "up":
            score += 1
        if macd_hist > 0:
            score += 1
        if rsi > 55:
            score += 1
        if supertrend < last_price:
            score += 1
        if mf.get("direction") == "in":
            score += 1

        if indi.get("trend") == "down":
            score -= 1
        if macd_hist < 0:
            score -= 1
        if rsi < 45:
            score -= 1
        if supertrend > last_price:
            score -= 1
        if mf.get("direction") == "out":
            score -= 1

        # 5. Финальный сигнал
        if score >= 2:
            signal = "LONG"
        elif score <= -2:
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

