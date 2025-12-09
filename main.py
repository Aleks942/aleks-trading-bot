import os
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60         # секунд между циклами
RISK_PERCENT = 1            # риск на сделку, %
DEPOSIT = 100               # условный депозит
RSI_LOW = 35
RSI_HIGH = 65

# id в CoinGecko -> тикер
SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
}

LAST_SIGNAL_FILE = "last_signal.txt"


# ============= ВСПОМОГАТЕЛЬНЫЕ =============

def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram not configured", flush=True)
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("TELEGRAM ERROR:", e, flush=True)


def load_last() -> str:
    if not os.path.exists(LAST_SIGNAL_FILE):
        return ""
    try:
        with open(LAST_SIGNAL_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def save_last(sig: str) -> None:
    try:
        with open(LAST_SIGNAL_FILE, "w") as f:
            f.write(sig)
    except Exception as e:
        print("SAVE LAST ERROR:", e, flush=True)


def get_market_data():
    """CoinGecko: цена, капа, %24ч по всем нужным монетам"""
    ids = ",".join(SYMBOLS.keys())
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ids,
        "price_change_percentage": "24h",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []
        return data
    except Exception as e:
        print("MARKET DATA ERROR:", e, flush=True)
        return []


def get_dex(symbol: str):
    """
    DEX Screener: ликвидность и объём.
    Берём первую попавшуюся пару по поиску тикера.
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/search"
        r = requests.get(url, params={"q": symbol}, timeout=10)
        data = r.json()
        if "pairs" not in data or not data["pairs"]:
            return None, 0.0, 0.0

        p = data["pairs"][0]
        dex_id = p.get("dexId")
        liq = float(p.get("liquidity", {}).get("usd", 0) or 0)
        vol = float(p.get("volume", {}).get("h24", 0) or 0)
        return dex_id, liq, vol
    except Exception as e:
        print("DEX ERROR:", e, flush=True)
        return None, 0.0, 0.0


def get_ohlc(coin_id: str):
    """
    OHLC из CoinGecko /coins/{id}/ohlc.
    Используем для расчёта RSI/ATR.
    """
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
        r = requests.get(url, params={"vs_currency": "usd", "days": 1}, timeout=10)
        data = r.json()
        if not isinstance(data, list) or len(data) < 20:
            # мало свечей — пропускаем
            return None
        df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
        return df
    except Exception as e:
        print("OHLC ERROR:", e, flush=True)
        return None


def calculate_rsi(df: pd.DataFrame, period: int = 14):
    """
    Безопасный RSI: если мало данных или всё NaN — возвращаем None.
    """
    try:
        if df is None or len(df) < period + 1:
            return None

        close = df["close"].astype(float)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi_clean = rsi.dropna()
        if rsi_clean.empty:
            return None
        return float(rsi_clean.iloc[-1])
    except Exception as e:
        print("RSI ERROR:", e, flush=True)
        return None


def calculate_atr(df: pd.DataFrame, period: int = 14):
    """
    Безопасный ATR: если мало данных или всё NaN — возвращаем None.
    """
    try:
        if df is None or len(df) < period + 1:
            return None

        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)

        high_low = high - low
        high_close = (high - close.shift()).abs()
        low_close = (low - close.shift()).abs()

        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(period).mean()
        atr_clean = atr.dropna()
        if atr_clean.empty:
            return None
        return float(atr_clean.iloc[-1])
    except Exception as e:
        print("ATR ERROR:", e, flush=True)
        return None


def calc_position(atr_value: float):
    """
    Риск 1% от депозита / диапазон ATR.
    """
    if atr_value is None or atr_value <= 0:
        return 0.0
    risk = DEPOSIT * RISK_PERCENT / 100
    size = risk / atr_value
    return round(size, 5)


# ============= ЗАПУСК БОТА =============

send_telegram("Bot started. Strategy: RSI 35/65 + Risk 1% + TP1/TP2 (DEX + CoinGecko)")
print("BOT STARTED", flush=True)

while True:
    try:
        market = get_market_data()
        last = load_last()

        for item in market:
            try:
                coin_id = item.get("id")
                if coin_id not in SYMBOLS:
                    continue

                symbol = SYMBOLS[coin_id]
                price = float(item.get("current_price") or 0)
                cap = float(item.get("market_cap") or 0)
                cap_ch = float(item.get("market_cap_change_percentage_24h") or 0)

                if price <= 0:
                    continue

                df = get_ohlc(coin_id)
                rsi_val = calculate_rsi(df)
                atr_val = calculate_atr(df)

                if rsi_val is None or atr_val is None:
                    # не смогли посчитать индикаторы — пропускаем монету
                    continue

                dex_id, liq, vol = get_dex(symbol)

                # ЛОГИКА СИГНАЛА
                signal = None
                if rsi_val >= RSI_HIGH:
                    signal = "SHORT"
                elif rsi_val <= RSI_LOW:
                    signal = "LONG"

                if not signal:
                    continue

                uid = f"{symbol}_{signal}"
                if uid == last:
                    # тот же сигнал, что и в прошлый раз — не спамим
                    continue

                # РАСЧЁТ УРОВНЕЙ
                if signal == "SHORT":
                    entry = price
                    stop = price + atr_val
                    tp1 = price - atr_val
                    tp2 = price - atr_val * 2
                else:
                    entry = price
                    stop = price - atr_val
                    tp1 = price + atr_val
                    tp2 = price + atr_val * 2

                size = calc_position(atr_val)

                msg = (
                    f"SIGNAL: {signal} | {symbol}\n\n"
                    f"Price: {round(price, 5)}\n"
                    f"RSI: {round(rsi_val, 2)}\n"
                    f"ATR: {round(atr_val, 5)}\n\n"
                    f"Entry: {round(entry, 5)}\n"
                    f"STOP: {round(stop, 5)}\n"
                    f"TP1: {round(tp1, 5)}\n"
                    f"TP2: {round(tp2, 5)}\n\n"
                    f"Deposit: {DEPOSIT}$\n"
                    f"Risk: {RISK_PERCENT}%\n"
                    f"Position size: {size}\n\n"
                    f"Cap: {int(cap)}$\n"
                    f"Cap 24h: {round(cap_ch, 2)}%\n"
                    f"DEX: {dex_id}\n"
                    f"Liquidity: {liq}$\n"
                    f"Volume 24h: {vol}$\n"
                    f"Time UTC: {datetime.utcnow()}"
                )

                send_telegram(msg)
                save_last(uid)

            except Exception as inner_e:
                # Локальная защита на одной монете, чтобы не падал весь цикл
                print(f"SYMBOL LOOP ERROR {symbol}:", inner_e, flush=True)
                continue

    except Exception as e:
        send_telegram(f"BOT ERROR (outer): {e}")
        print("OUTER ERROR:", e, flush=True)

    time.sleep(CHECK_INTERVAL)

