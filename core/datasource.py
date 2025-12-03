import requests
import pandas as pd


# =============================
# КОНВЕРТАЦИЯ TF ДЛЯ BYBIT
# =============================
def convert_tf_to_bybit(tf: str) -> str:
    mapping = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "4h": "240",
        "1d": "D",
        "1w": "W"
    }
    return mapping.get(tf, "60")  # по умолчанию 1h


# =============================
# DATA SOURCE
# =============================
class DataSource:

    def __init__(self):
        self.bybit_url = "https://api.bybit.com"
        self.binance_url = "https://api.binance.com"

    # ============================
    # BYBIT KLINES
    # ============================
    def get_klines_bybit(self, symbol="BTCUSDT", interval="1h"):

        interval_converted = convert_tf_to_bybit(interval)

        url = f"{self.bybit_url}/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval_converted,
            "limit": 200
        }

        try:
           headers = {
    "User-Agent": "Mozilla/5.0"
}
r = requests.get(url, params=params, headers=headers, timeout=10)

            data = r.json()
        except Exception:
            return None

        if "result" not in data or "list" not in data["result"]:
            return None

        raw = data["result"]["list"]
        if not raw:
            return None

        df = pd.DataFrame(raw)
        df.columns = [
            "timestamp", "open", "high", "low", "close",
            "volume", "_", "_"
        ]

        df["timestamp"] = df["timestamp"].astype("int64") // 1000
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)

        return df

    # ============================
    # BINANCE KLINES (FALLBACK)
    # ============================
    def get_klines_binance(self, symbol="BTCUSDT", interval="1h"):

        url = f"{self.binance_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 500
        }

        try:
            headers = {
    "User-Agent": "Mozilla/5.0"
}
r = requests.get(url, params=params, headers=headers, timeout=10)

            data = r.json()
        except Exception:
            return None

        if not isinstance(data, list) or len(data) == 0:
            return None

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "close_time"
        ])

        df["open_time"] = df["open_time"] // 1000
        df.set_index("open_time", inplace=True)
        df = df.astype(float)

        return df


# =============================
# PUBLIC API
# =============================
def get_ohlcv(symbol: str, timeframe: str):

    ds = DataSource()

    # 1. Пробуем BYBIT
    df = ds.get_klines_bybit(symbol, timeframe)

    if df is not None and len(df) >= 50:
        return df

    # 2. Если BYBIT не дал данных — BINANCE
    df = ds.get_klines_binance(symbol, timeframe)

    if df is not None and len(df) >= 50:
        return df

    # 3. Полный фэйл
    return None

       
