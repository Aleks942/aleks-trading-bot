import requests
import pandas as pd
import time

# =============================
# СИМВОЛЫ ДЛЯ COINGECKO
# =============================
COINGECKO_SYMBOLS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana",
    "XRPUSDT": "ripple",
    "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2",
    "LINKUSDT": "chainlink",
    "MATICUSDT": "polygon",
    "TONUSDT": "toncoin",
    "NEARUSDT": "near",
    "OPUSDT": "optimism",
    "ARBUSDT": "arbitrum",
}


# =============================
# TF → DAYS (для COINGECKO)
# =============================
def tf_to_days(tf: str) -> int:
    # CoinGecko для /ohlc поддерживает дни:
    # 1, 7, 14, 30, 90, 180, 365, max
    if tf == "1h":
        return 1
    if tf == "4h":
        return 7
    if tf == "1d":
        return 90
    # по умолчанию – неделя
    return 7


# =============================
# COINGECKO OHLC
# =============================
def get_ohlcv_coingecko(symbol: str, timeframe: str):
    sym = symbol.upper()
    coin_id = COINGECKO_SYMBOLS.get(sym)
    if not coin_id:
        print(f"[COINGECKO] SYMBOL NOT MAPPED: {sym}")
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
    except Exception as e:
        print("[COINGECKO] REQUEST ERROR:", e)
        return None

    if not isinstance(data, list) or len(data) < 20:
        print("[COINGECKO] EMPTY OR SMALL DATA:", len(data) if isinstance(data, list) else "N/A")
        return None

    # Формат: [timestamp, open, high, low, close]
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close"
    ])

    # Объёма нет – ставим 0, чтобы не ломать индикаторы
    df["volume"] = 0.0
    df["timestamp"] = df["timestamp"] // 1000
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)

    print(f"[COINGECKO] DATA OK: {sym}, rows={len(df)}")
    return df


# =============================
# BINANCE DATA
# =============================
def get_klines_binance(symbol="BTCUSDT", interval="1h", limit=500):
    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception as e:
        print("[BINANCE] REQUEST ERROR:", e)
        return None

    if not isinstance(data, list) or len(data) < 50:
        print("[BINANCE] EMPTY DATA")
        return None

    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "close_time"
    ])

    df["open_time"] = df["open_time"] // 1000
    df.set_index("open_time", inplace=True)

    df = df.astype(float)
    print("[BINANCE] DATA OK:", symbol, "rows=", len(df))
    return df


# =============================
# BYBIT DATA
# =============================
def convert_tf_to_bybit(tf):
    mapping = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "4h": "240",
        "1d": "D"
    }
    return mapping.get(tf, "60")


def get_klines_bybit(symbol="BTCUSDT", interval="1h", limit=200):
    url = "https://api.bybit.com/v5/market/kline"

    interval_converted = convert_tf_to_bybit(interval)

    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval_converted,
        "limit": limit
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception as e:
        print("[BYBIT] REQUEST ERROR:", e)
        return None

    if "result" not in data or "list" not in data["result"]:
        print("[BYBIT] EMPTY DATA STRUCT")
        return None

    raw = data["result"]["list"]

    if not raw or len(raw) < 50:
        print("[BYBIT] EMPTY DATA")
        return None

    df = pd.DataFrame(raw, columns=[
        "timestamp", "open", "high", "low", "close",
        "volume", "_", "_"
    ])

    df["timestamp"] = df["timestamp"].astype("int64") // 1000
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)

    print("[BYBIT] DATA OK:", symbol, "rows=", len(df))
    return df


# =============================
# MAIN PUBLIC FUNCTION
# =============================
def get_ohlcv(symbol, timeframe):
    """
    Главная точка входа для анализатора.
    Порядок:
    1) CoinGecko
    2) Binance
    3) Bybit
    """
    sym = symbol.upper()
    tf = timeframe

    print("[DATASOURCE] REQUEST:", sym, tf)

    # 1. CoinGecko (основной)
    df = get_ohlcv_coingecko(sym, tf)
    if df is not None and len(df) >= 20:
        return df

    time.sleep(1)

    # 2. Binance (если поддерживает символ)
    df = get_klines_binance(sym, tf)
    if df is not None and len(df) >= 50:
        return df

    time.sleep(1)

    # 3. Bybit (резерв)
    df = get_klines_bybit(sym, tf)
    if df is not None and len(df) >= 50:
        return df

    print("[DATASOURCE] ALL SOURCES FAILED:", sym, tf)
    return None

