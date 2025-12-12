import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta
import statistics

print("=== MARKET RADAR WITH STAGES STARTED ===", flush=True)

# ================= ENV =================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10  # 10 минут
STATE_FILE = "radar_state.json"

# ================= PARAMS =================
COINS_LIMIT = 200
VOLUME_SPIKE_MIN = 2.0        # минимум для внимания
VOLUME_SPIKE_STRONG = 3.0     # сильный объём
FLAT_RANGE_MAX = 1.5          # % диапазона флета
OVERHEAT_PCT = 6.0            # % для перегрева
COOLDOWN_MIN = 90             # анти-спам

# ================= TELEGRAM =================
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except:
        pass

# ================= STATE =================
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ================= DATA =================
def get_top_coins():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": COINS_LIMIT,
        "page": 1,
        "sparkline": False
    }
    try:
        return requests.get(url, params=params, timeout=30).json()
    except:
        return []

def get_market_chart(coin_id, days=2):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": days}
        data = requests.get(url, params=params, timeout=20).json()
        prices = [p[1] for p in data.get("prices", [])]
        volumes = [v[1] for v in data.get("total_volumes", [])]
        if len(prices) < 24:
            return None, None
        return pd.Series(prices), pd.Series(volumes)
    except:
        return None, None

def pct_change(series, hours):
    if len(series) < hours + 1:
        return 0
    return (series.iloc[-1] - series.iloc[-(hours+1)]) / series.iloc[-(hours+1)] * 100

def dynamic_threshold(series):
    changes = [abs((series.iloc[i] - series.iloc[i-1]) / series.iloc[i-1] * 100)
               for i in range(1, len(series))]
    if len(changes) < 10:
        return 1.0
    return max(statistics.mean(changes) * 2, 0.8)

# ================= MAIN =================
def run_bot():
    state = load_state()
    send_telegram("📡 <b>Радар рынка запущен</b>\n200 монет • 1h + 4h • стадии движения")

    while True:
        coins = get_top_coins()
        now_ts = datetime.utcnow().timestamp()

        for coin in coins:
            coin_id = coin.get("id")
            symbol = coin.get("symbol", "").upper()

            prices, volumes = get_market_chart(coin_id)
            if prices is None:
                continue

            # анти-спам
            last = state.get(coin_id, {})
            if last and now_ts - last.get("time", 0) < COOLDOWN_MIN * 60:
                continue

            # расчёты
            price_range = (prices.max() - prices.min()) / prices.mean() * 100
            vol_avg = volumes[:-12].mean()
            vol_now = volumes.iloc[-1]
            vol_mult = vol_now / vol_avg if vol_avg > 0 else 0

            chg_1h = pct_change(prices, 1)
            chg_4h = pct_change(prices, 4)
            dyn_thr = dynamic_threshold(prices)

            stage = None
            reasons = []

            # 🟢 ПОДГОТОВКА
            if vol_mult >= VOLUME_SPIKE_MIN and price_range <= FLAT_RANGE_MAX:
                stage = "ПОДГОТОВКА"
                reasons.append(f"Объём x{vol_mult:.1f}")
                reasons.append("Цена во флете")

            # 🟡 ЗАПУСК
            if vol_mult >= VOLUME_SPIKE_STRONG and abs(chg_1h) >= dyn_thr:
                stage = "ЗАПУСК"
                reasons.append(f"Импульс 1ч {chg_1h:.2f}%")
                reasons.append(f"Объём x{vol_mult:.1f}")

            # 🔴 ПЕРЕГРЕВ
            if abs(chg_4h) >= OVERHEAT_PCT:
                stage = "ПЕРЕГРЕВ"
                reasons.append(f"Импульс 4ч {chg_4h:.2f}%")
                reasons.append("Риск выдоха")

            if stage is None:
                continue

            # сообщение только при смене стадии
            if last.get("stage") == stage:
                continue

            emoji = {"ПОДГОТОВКА":"🟢","ЗАПУСК":"🟡","ПЕРЕГРЕВ":"🔴"}[stage]

            msg = (
                f"{emoji} <b>{symbol}</b>\n"
                f"Стадия: <b>{stage}</b>\n\n"
                f"1ч: {chg_1h:.2f}% | 4ч: {chg_4h:.2f}%\n"
                f"Объём: x{vol_mult:.1f}\n\n"
                f"Причины:\n• " + "\n• ".join(reasons) +
                "\n\nСтатус: <b>НАБЛЮДАТЬ</b>"
            )

            send_telegram(msg)
            state[coin_id] = {"stage": stage, "time": now_ts}
            save_state(state)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
