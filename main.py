import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import statistics

print("=== MARKET RADAR FINAL (STAGES + STRENGTH + MEMO + CONCLUSION) ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10   # 10 минут
STATE_FILE = "radar_state.json"

# ===== PARAMS =====
COINS_LIMIT = 200
FLAT_RANGE_MAX = 1.5       # % диапазон флета
OVERHEAT_4H = 6.0          # % для перегрева
COOLDOWN_MIN = 90          # анти-спам в минутах

# ===== START CONTROL =====
last_start_in_memory = None

# ===== TELEGRAM =====
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

# ===== STATE =====
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(data):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

# ===== START MESSAGE (1 РАЗ В СУТКИ) =====
def send_start_once_per_day(state):
    global last_start_in_memory
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if last_start_in_memory == today:
        return

    if state.get("_last_start") == today:
        last_start_in_memory = today
        return

    send_telegram(
        "📡 <b>Радар рынка активен</b>\n"
        "200 монет • 1h + 4h • стадии • сила • памятка • вывод"
    )

    state["_last_start"] = today
    last_start_in_memory = today
    save_state(state)

# ===== DATA =====
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

def get_market_chart(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 2}
        data = requests.get(url, params=params, timeout=20).json()
        prices = [p[1] for p in data.get("prices", [])]
        volumes = [v[1] for v in data.get("total_volumes", [])]
        if len(prices) < 24:
            return None, None
        return pd.Series(prices), pd.Series(volumes)
    except:
        return None, None

def pct_change(series, h):
    if len(series) < h + 1:
        return 0
    return (series.iloc[-1] - series.iloc[-(h+1)]) / series.iloc[-(h+1)] * 100

def dynamic_threshold(series):
    changes = [
        abs((series.iloc[i] - series.iloc[i-1]) / series.iloc[i-1] * 100)
        for i in range(1, len(series))
    ]
    if len(changes) < 10:
        return 1.0
    return max(statistics.mean(changes) * 2, 0.8)

# ===== MEMO =====
def memo_by_strength(strength):
    if strength == 4:
        return (
            "• не входи сразу\n"
            "• жди ретест / паузу\n"
            "• проверь BTC (флет = плюс)\n"
            "• вход только с понятным стопом"
        )
    if strength >= 5:
        return (
            "• проверь: это НЕ перегрев?\n"
            "• если есть база — можно планировать\n"
            "• не увеличивай риск\n"
            "• не входи на эмоциях"
        )
    return ""

# ===== LOGICAL CONCLUSION =====
def logical_conclusion(stage, strength, chg_4h):
    if stage == "ЗАПУСК" and strength >= 4 and abs(chg_4h) < OVERHEAT_4H:
        return "🟢 <b>ВХОД ВОЗМОЖЕН</b>\n(если появится структура)"
    return "🔴 <b>НЕ ВХОД</b>\n(рано, поздно или риск)"

# ===== MAIN =====
def run_bot():
    state = load_state()
    send_start_once_per_day(state)

    while True:
        coins = get_top_coins()
        now_ts = datetime.utcnow().timestamp()

        for coin in coins:
            cid = coin.get("id")
            sym = coin.get("symbol", "").upper()

            prices, volumes = get_market_chart(cid)
            if prices is None:
                continue

            last = state.get(cid, {})
            if last and now_ts - last.get("time", 0) < COOLDOWN_MIN * 60:
                continue

            price_range = (prices.max() - prices.min()) / prices.mean() * 100
            vol_avg = volumes[:-12].mean()
            vol_now = volumes.iloc[-1]
            vol_mult = vol_now / vol_avg if vol_avg > 0 else 0

            chg_1h = pct_change(prices, 1)
            chg_4h = pct_change(prices, 4)
            dyn_thr = dynamic_threshold(prices)

            stage = None
            reasons = []
            strength = 0

            if vol_mult >= 2: strength += 1
            if vol_mult >= 3: strength += 1

            if vol_mult >= 2 and price_range <= FLAT_RANGE_MAX:
                stage = "ПОДГОТОВКА"
                reasons += ["Цена во флете", f"Объём x{vol_mult:.1f}"]
                strength += 1

            if vol_mult >= 3 and abs(chg_1h) >= dyn_thr:
                stage = "ЗАПУСК"
                reasons += [f"Импульс 1ч {chg_1h:.2f}%", "Выход из флета"]
                strength += 1

            if abs(chg_4h) >= OVERHEAT_4H:
                stage = "ПЕРЕГРЕВ"
                reasons += [f"Импульс 4ч {chg_4h:.2f}%", "Риск выдоха"]
                strength += 1

            if chg_1h * chg_4h > 0:
                strength += 1
                reasons.append("1h + 4h в одну сторону")

            if stage is None or strength < 2:
                continue

            if last.get("stage") == stage and last.get("strength") == strength:
                continue

            emoji = {"ПОДГОТОВКА": "🟢", "ЗАПУСК": "🟡", "ПЕРЕГРЕВ": "🔴"}[stage]
            fire = "🔥" * strength
            memo = memo_by_strength(strength)
            conclusion = logical_conclusion(stage, strength, chg_4h)

            msg = (
                f"{emoji} <b>{sym}</b>\n"
                f"Стадия: <b>{stage}</b>\n"
                f"Сила: {fire} ({strength}/5)\n\n"
                f"1ч: {chg_1h:.2f}% | 4ч: {chg_4h:.2f}%\n"
                f"Объём: x{vol_mult:.1f}\n\n"
                f"Причины:\n• " + "\n• ".join(reasons)
            )

            if memo:
                msg += f"\n\n📌 <b>ПАМЯТКА</b>:\n{memo}"

            msg += f"\n\n🧠 <b>ВЫВОД</b>:\n{conclusion}"

            send_telegram(msg)
            state[cid] = {"stage": stage, "strength": strength, "time": now_ts}
            save_state(state)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
