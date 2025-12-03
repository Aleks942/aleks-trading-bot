import requests
import pandas as pd
from datetime import datetime


# =============================
# СЛОВАРЬ СИМВОЛОВ
# =============================
COINGECKO_SYMBOLS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana",
    "XRPUSDT": "ripple",
    "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin"
}


# =============================
# КОНВЕРТАЦИЯ TF → DAYS
# =============================
def tf_to_days(tf: str) -> int:
    if tf == "1h":
        return 2        # ~48 часов
    if tf == "4h":
        return 7
    if tf == "1d":
        return 90
    return 2


# =============================
# COINGECKO OHLC
# =============================
def get_ohlcv(symbol: str, timeframe: str):

    coin_id = COINGECKO_SYMBOLS.get(symbol.upper())
    if not coin_id:
        return None

    days = tf_to_days(timeframe)

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": days
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
    except Exception:
        return None

    if not isinstance(data, list) or len(data) == 0:
        return None

    # Формат CoinGecko:
    # [timestamp, open, high, low, close]
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close"
    ])

    df["volume"] = 0.0  # Заглушка под твой анализатор
    df["timestamp"] = df["timestamp"] // 1000
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)

    return df
