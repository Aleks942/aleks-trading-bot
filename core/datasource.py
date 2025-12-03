import requests
import pandas as pd


class DataSource:

    def __init__(self):
        self.binance_url = "https://api.binance.com"

    # ============================
    # BINANCE KLINES
    # ============================
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
            r = requests.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
        except Exception:
            print("BINANCE REQUEST FAILED")
            return None

        if not isinstance(data, list) or len(data) == 0:
            print("BINANCE EMPTY DATA")
            return None

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "close_time"
        ])

        df["open_time"] = df["open_time"] // 1000
        df.set_index("open_time", inplace=True)
        df = df.astype(float)

        print("BINANCE LEN:", len(df))
        return df


# =============================
# PUBLIC API (только BINANCE)
# =============================
def get_ohlcv(symbol: str, timeframe: str):

    ds = DataSource()

    df = ds.get_klines_binance(symbol, timeframe)

    if df is not None and len(df) >= 50:
        return df

    return None
