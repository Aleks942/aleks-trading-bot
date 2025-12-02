import pandas as pd

def calculate_volatility(df, period=20):
    """Обычная историческая волатильность"""
    returns = df['close'].pct_change()
    vol = returns.rolling(period).std() * (len(df) ** 0.5)
    return vol

def detect_volatility_zone(vol):
    """Определение зоны волатильности"""

    last = vol.iloc[-1]

    if last > vol.mean() * 1.5:
        return "high"        # высокая волатильность
    if last < vol.mean() * 0.7:
        return "low"         # низкая волатильность

    return "normal"          # средняя волатильность

def analyze_volatility(df):
    """Основная функция, которую импортирует analyzer.py"""

    vol = calculate_volatility(df)

    return {
        "volatility_value": float(vol.iloc[-1]),
        "zone": detect_volatility_zone(vol)
    }

