import requests
import pandas as pd
import time

class DataSource:
    # ... (весь ваш класс DataSource остается без изменений) ...
    def __init__(self):
        self.bybit_url = "https://api.bybit.com"
        self.binance_url = "https://api.binance.com"

    # ============================
    #   BYBIT KLINES (свечи)
    # ============================
    def get_klines_bybit(self, symbol="BTCUSDT", interval="60"):
        url = f"{self.bybit_url}/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": 200
        }
        r = requests.get(url, params=params).json()

        if "result" not in r or "list" not in r["result"]:
            return None

        df = pd.DataFrame(r["result"]["list"])
        df.columns = [
            "timestamp", "open", "high", "low", "close",
            "volume", "_", "_"
        ]
        df["timestamp"] = df["timestamp"].astype("int64") // 1000
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)

        return df

    # ============================
    #     OPEN INTEREST (BYBIT)
    # ============================
    def get_open_interest(self, symbol="BTCUSDT"):
        url = f"{self.bybit_url}/v5/market/open-interest"
        params = {
            "category": "linear",
            "symbol": symbol,
            "intervalTime": "5min"
        }
        r = requests.get(url, params=params).json()

        if "result" not in r:
            return None

        df = pd.DataFrame(r["result"]["list"])
        df["openInterest"] = df["openInterest"].astype(float)
        return df

    # ============================
    #     ПУЛ ЛИКВИДАЦИЙ (BYBIT)
    # ============================
    def get_liquidations(self, symbol="BTCUSDT"):
        url = f"{self.bybit_url}/v5/market/liquidation"
        params = {
            "category": "linear",
            "symbol": symbol,
            "limit": 200
        }
        r = requests.get(url, params=params).json()

        if "result" not in r:
            return None

        df = pd.DataFrame(r["result"]["list"])
        return df

    # ============================
    #   BACKUP: BINANCE KLINES
    # ============================
    def get_klines_binance(self, symbol="BTCUSDT", interval="1h"):
        url = f"{self.binance_url}/api/v3/klines"
        
        r = requests.get(url, params={
            "symbol": symbol,
            "interval": interval,
            "limit": 500
        }).json()

        df = pd.DataFrame(r, columns=[
            "open_time","open","high","low","close","volume",
            "_","_","_","_","_","close_time"
        ])

        df["open_time"] = df["open_time"] // 1000
        df.set_index("open_time", inplace=True)
        df = df.astype(float)

        return df

# !!! ДОБАВЬТЕ ЭТУ ФУНКЦИЮ В КОНЕЦ ФАЙЛА !!!
def get_ohlcv(symbol, timeframe):
    ds = DataSource()
    # Пытаемся получить данные с Bybit, если не получается, пробуем Binance
    df = ds.get_klines_bybit(symbol, timeframe)
    if df is None or len(df) == 0:
        df = ds.get_klines_binance(symbol, timeframe)
    return df
