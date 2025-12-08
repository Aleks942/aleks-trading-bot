import time
import requests
import statistics
from telegram import Bot

# =========================
# НАСТРОЙКИ
# =========================
TELEGRAM_TOKEN = "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН"
CHAT_ID = "ВСТАВЬ_СЮДА_CHAT_ID"

TIMEFRAME = "15m"
TREND_TIMEFRAME = "1h"
CHECK_INTERVAL = 60  # проверка раз в минуту

BASE_URL = "https://api.binance.com/api/v3/klines"

bot = Bot(token=TELEGRAM_TOKEN)

# =========================
# ПАМЯТЬ АНТИДУБЛИКАТА
# =========================
last_signal_type = {}
last_signal_price = {}

# =========================
# СПИСОК АЛЬТОВ (ВСЕ USDT)
# =========================
def get_all_symbols():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    data = requests.get(url, timeout=10).json()

    symbols = []
    for s in data["symbols"]:
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
            symbols.append(s["symbol"])
    return symbols


# =========================
# ЗАГРУЗКА СВЕЧЕЙ
# =========================
def get_klines(symbol, interval, limit=200):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    return requests.get(BASE_URL, params=params, timeout=10).json()


# =========================
# ИНДИКАТОРЫ
# =========================
def ema(data, period):
    k = 2 / (period + 1)
    ema_val = data[0]
    for price in data[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def rsi_calc(closes, period=14):
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if losses else 0.0001

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr_calc(highs, lows, closes, period=14):
    trs = []
    for i in range(1, period + 1):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)

    atr = sum(trs) / period
    return (atr / closes[-1]) * 100


# =========================
# ОЦЕНКА СИГНАЛА
# =========================
def score_signal(volume_x, atr, trend_ok, btc_ok):
    score = 0
    if volume_x > 2: score += 3
    elif volume_x > 1.5: score += 2
    elif volume_x > 1.2: score += 1
    if btc_ok: score += 3
    if trend_ok: score += 2
    if atr > 0.25: score += 2
    return score


# =========================
# STOP / TAKE
# =========================
def calc_levels(price, atr_percent, direction):
    atr_abs = price * (atr_percent / 100)

    if direction == "LONG":
        sl = price - atr_abs * 1.2
        tp1 = price + atr_abs * 1.5
        tp2 = price + atr_abs * 2.5
        tp3 = price + atr_abs * 4
    else:
        sl = price + atr_abs * 1.2
        tp1 = price - atr_abs * 1.5
        tp2 = price - atr_abs * 2.5
        tp3 = price - atr_abs * 4

    return round(sl, 4), round(tp1, 4), round(tp2, 4), round(tp3, 4)


# =========================
# ГЛАВНАЯ ЛОГИКА
# =========================
def process_symbol(symbol, btc_trend):

    global last_signal_type, last_signal_price

    try:
        klines = get_klines(symbol, TIMEFRAME)
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        price = closes[-1]
        rsi = round(rsi_calc(closes), 2)
        atr = round(atr_calc(highs, lows, closes), 2)

        ema200 = ema(closes[-200:], 200)

        avg_volume = statistics.mean(volumes[-20:])
        volume_x = round(volumes[-1] / avg_volume, 2)

        trend_ok = price > ema200
        volume_ok = volume_x > 2
        atr_ok = atr > 0.25

        signal_type = None

        if trend_ok and volume_ok and atr_ok and rsi < 75 and btc_trend == "LONG":
            signal_type = "LONG"

        elif not trend_ok and volume_ok and atr_ok and rsi > 25 and btc_trend == "SHORT":
            signal_type = "SHORT"

        if signal_type:
            if symbol in last_signal_type:
                if last_signal_type[symbol] == signal_type and abs(price - last_signal_price[symbol]) / price < 0.0015:
                    return

            score = score_signal(volume_x, atr, trend_ok, btc_trend == signal_type)

            if score < 7:
                return

            sl, tp1, tp2, tp3 = calc_levels(price, atr, signal_type)

            text = f"""
🚀 {symbol} {signal_type} | 15m
Оценка: {score}/10
BTC-фильтр: ✅

📍 Entry: {round(price, 4)}
🛑 Stop: {sl}
🎯 TP1: {tp1}
🎯 TP2: {tp2}
🎯 TP3: {tp3}

ATR: {atr}%
Объём: {volume_x}x
RSI: {rsi}
Риск: Средний
            """

            bot.send_message(CHAT_ID, text)

            last_signal_type[symbol] = signal_type
            last_signal_price[symbol] = price

    except Exception as e:
        print(symbol, "ERROR:", e)


# =========================
# BTC ФИЛЬТР
# =========================
def get_btc_trend():
    btc_klines = get_klines("BTCUSDT", TREND_TIMEFRAME)
    closes = [float(k[4]) for k in btc_klines]
    ema200 = ema(closes[-200:], 200)
    price = closes[-1]

    return "LONG" if price > ema200 else "SHORT"


# =========================
# ЗАПУСК
# =========================
def main():

    symbols = get_all_symbols()
    print("Монет:", len(symbols))

    while True:
        btc_trend = get_btc_trend()
        print("BTC тренд:", btc_trend)

        for symbol in symbols:
            process_symbol(symbol, btc_trend)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
