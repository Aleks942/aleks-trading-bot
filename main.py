import os
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# =========================
# НАСТРОЙКИ
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = {
    "bitcoin": "BITCOIN",
    "ethereum": "ETHEREUM",
    "solana": "SOLANA",
}

# 5-минутные свечи, берём до 100 штук
TIMEFRAME_MINUTES = 5
CANDLES_LIMIT = 100
CHECK_INTERVAL = 60  # раз в минуту

LAST_HASH_FILE = "last_hash.txt"


# =========================
# TELEGRAM
# =========================
def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception:
        # В проде не роняем бота из-за телеги
        pass


# =========================
# COINGECKO OHLC (5m)
# =========================
def get_ohlc(coin_id: str) -> pd.DataFrame | None:
    """
    Возвращает DataFrame с колонками: time, open, high, low, close.
    Если данных нет или ответ пустой — возвращает None.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": 1,  # за последний день достаточно для 5m
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        # Иногда CoinGecko может вернуть не список
        if not isinstance(data, list) or len(data) == 0:
            return None

        df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
        if df.empty:
            return None

        # Берём только последние CANDLES_LIMIT свечей
        df = df.tail(CANDLES_LIMIT).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"OHLC ERROR for {coin_id}: {e}")
        return None


# =========================
# RSI
# =========================
def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    if series is None or series.empty or len(series) < period + 1:
        raise ValueError("Not enough data for RSI")

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return float(rsi.iloc[-1])


# =========================
# ATR
# =========================
def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    if df is None or df.empty or len(df) < period + 1:
        raise ValueError("Not enough data for ATR")

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    atr = true_range.rolling(period).mean()
    return float(atr.iloc[-1])


# =========================
# АНТИ-ДУБЛИ (по хэшу цен/RSI)
# =========================
def load_last_hash() -> str | None:
    if not os.path.exists(LAST_HASH_FILE):
        return None
    try:
        with open(LAST_HASH_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def save_last_hash(h: str) -> None:
    try:
        with open(LAST_HASH_FILE, "w") as f:
            f.write(h)
    except Exception:
        pass


# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================
def run() -> None:
    send_telegram("Bot started. Real OHLC 5m + RSI/ATR enabled.")

    while True:
        try:
            messages: list[str] = []
            current_hash_parts: list[str] = []

            for coin_id, name in SYMBOLS.items():
                df = get_ohlc(coin_id)

                # Защита: если нет данных или мало свечей — просто пропускаем монету
                if df is None or df.empty or len(df) < 20:
                    print(f"SKIP {coin_id}: not enough OHLC data")
                    continue

                try:
                    price = float(df["close"].iloc[-1])
                    rsi = calculate_rsi(df["close"])
                    atr = calculate_atr(df)
                except Exception as ind_err:
                    print(f"INDICATOR ERROR {coin_id}: {ind_err}")
                    continue

                # Собираем хэш по ценам и RSI, чтобы отсекать дубли
                current_hash_parts.append(f"{coin_id}:{round(price, 2)}:{round(rsi, 2)}")

                msg = (
                    f"{name}\n"
                    f"Price (5m close): {round(price, 2)}$\n"
                    f"RSI (5m): {round(rsi, 2)}\n"
                    f"ATR (5m): {round(atr, 4)}\n"
                    f"Time (UTC): {datetime.utcnow()}\n"
                )
                messages.append(msg)

            if not messages:
                # Ничего не собрали — просто ждём следующий цикл
                time.sleep(CHECK_INTERVAL)
                continue

            current_hash = "|".join(current_hash_parts)
            last_hash = load_last_hash()

            # Если состояние рынка (по нашему хэшу) изменилось — шлём сообщения
            if current_hash != last_hash:
                for msg in messages:
                    send_telegram(msg)
                save_last_hash(current_hash)
            else:
                # Ничего не поменялось — можно тихо пропустить отправку
                pass

        except Exception as e:
            # Ловим любые фатальные ошибки цикла, чтобы бот не падал
            print("MAIN LOOP ERROR:", e)
            send_telegram(f"BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)


# =========================
# ЗАПУСК
# =========================
if __name__ == "__main__":
    print("BOOT OK: main.py started")
    run()

