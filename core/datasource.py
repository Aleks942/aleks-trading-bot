import requests
import pandas as pd


class DataSource:

    def __init__(self):
        self.binance_url = "https://api.binance.com"

    def get_klines_binance(self, symbol="BTCUSDT", interval="1h"):

        url = f"{self.binance_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 500
        }

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        try:
            print("BINANCE REQUEST SENT:", symbol, interval)
            r = requests.get(url, params=params, headers=headers, timeout=10)
            print("BINANCE STATUS:", r.status_code)
            data = r.json()
            print("BINANCE RAW TYPE:", type(data))
        except Exception as e:
            print("BINANCE REQUEST EXCEPTION:", e)
            return None

        if not isinstance(data, list):
            print("BINANCE NOT LIST:", data)
            return None

        if len(data) == 0:
            print("BINANCE EMPTY LIST")
            return None

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "close_time"
        ])

        df["open_time"] = df["open_time"] // 1000
        df.set_index("open_time", inplace=True)
        df = df.astype(float)

        print("BINANCE DF LEN:", len(df))
        return df


def get_ohlcv(symbol: str, timeframe: str):

    print("GET OHLCV CALLED:", symbol, timeframe)

    ds = DataSource()
    df = ds.get_klines_binance(symbol, timeframe)

    if df is None:
        print("GET OHLCV RESULT: NONE")
        return None

    print("GET OHLCV RESULT LEN:", len(df))

    if len(df) >= 50:
        return df

    return None
