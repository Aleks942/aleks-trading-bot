import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import statistics

print("=== MARKET RADAR FINAL (ENV START FIX) ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 10   # 10 минут

# ===== PARAMS =====
COINS_LIMIT = 200
FLAT_RANGE_MAX = 1.5
OVERHEAT_4H = 6.0
COOLDOWN_MIN = 90

# ===== TELEGRAM =====
def send_telegram(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except:
        pass

# ===== START MESSAGE (ENV FIX) =====
def send_start_once_per_day():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    last = os.getenv("LAST_START_DATE")

    if last == today:
        return

    send_telegram(
        "📡 <b>Радар рынка запущен</b>\n"
        "200 монет • 1h + 4h • стадии • сила • памятка • вывод"
    )

    # Railway сохраняет ENV между рестартами
    os.environ["LAST_START_DATE"] = today

# ===== DATA =====
def get_top_coins():
    try:
        return requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": COINS_LIMIT,
                "page": 1,
                "sparkline": False
            },
            timeout=30
        ).json()
    except:
        return []

def get_market_chart(coin_id):
    try:
        data = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": 2},
            timeout=20
        ).json()

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
    return (series.iloc[-1] - series.iloc[-(h + 1)]) / series.iloc[-(h + 1)] * 100

def dynamic_threshold(series):
    changes = [
        abs((series.iloc[i] - series.iloc[i - 1]) / series.iloc[i - 1] * 100)
        for i in range(1, len(series))
    ]
    if len(changes) < 10:
        return 1.0
    return max(statistics.mean(changes) * 2, 0.8)

# ===== MEMO =====
def memo_by_strength(strength):
    if strength == 1:
        return "• ранний кандидат\n• просто наблюдать\n• без входа"
    if strength == 4:
        return (
            "• не входи сразу\n"
            "• жди паузу / ретест\n"
            "• проверь BTC\n"
            "• вход только со стопом"
        )
    if strength >= 5:
        return (
            "• не FOMO\n"
            "• проверь перегрев\n"
            "• риск не увеличивать"
        )
    return ""

def logical_conclusion(stage, strength, chg_4h):
    if stage == "ЗАПУСК" and strength >= 4 and abs(chg_4h) < OVERHEAT_4H:
        return "🟢 <b>ВХОД ВОЗМОЖЕН</b>\n(если появится структура)"
    if stage == "ПОДГОТОВКА":
        return "🟡 <b>НАБЛЮДАТЬ</b>"
    return "🔴 <b>НЕ ВХОД</b>"

# ===== MAIN =====
def run_bot():
    send_start_once_per_day()
    state = {}

    while True:
        coins = get_top_coins()
        now_ts = datetime.utcnow().timestamp()

        for coin in coins:
            cid = coin.get("id")
            sym = coin.get("symbol", "").upper()

            prices, volumes = get_market_chart(cid)
            if prices is None:
                continue

            last = state.get(cid)
            if last and now_ts - last["time"] < COOLDOWN_MIN * 60:
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
                strength += 1
                reasons += ["Флет", f"Объём x{vol_mult:.1f}"]

            if vol_mult >= 3 and abs(chg_1h) >= dyn_thr:
                stage = "ЗАПУСК"
                strength += 1
                reasons += [f"Импульс 1ч {chg_1h:.2f}%"]

            if abs(chg_4h) >= OVERHEAT_4H:
                stage = "ПЕРЕГРЕВ"
                strength += 1
                reasons += [f"Импульс 4ч {chg_4h:.2f}%"]

            if chg_1h * chg_4h > 0:
                strength += 1
                reasons.append("1h + 4h в одну сторону")

            if stage is None:
                continue
            if stage == "ПОДГОТОВКА" and strength < 1:
                continue
            if stage != "ПОДГОТОВКА" and strength < 2:
                continue

            if last and last["stage"] == stage and last["strength"] == strength:
                continue

            emoji = {"ПОДГОТОВКА": "🟢", "ЗАПУСК": "🟡", "ПЕРЕГРЕВ": "🔴"}[stage]
            fire = "🔥" * strength

            msg = (
                f"{emoji} <b>{sym}</b>\n"
                f"Стадия: <b>{stage}</b>\n"
                f"Сила: {fire} ({strength}/5)\n\n"
                f"1ч: {chg_1h:.2f}% | 4ч: {chg_4h:.2f}%\n"
                f"Объём: x{vol_mult:.1f}\n\n"
                f"Причины:\n• " + "\n• ".join(reasons)
            )

            memo = memo_by_strength(strength)
            if memo:
                msg += f"\n\n📌 <b>ПАМЯТКА</b>:\n{memo}"

            msg += f"\n\n🧠 <b>ВЫВОД</b>:\n{logical_conclusion(stage, strength, chg_4h)}"

            send_telegram(msg)
            state[cid] = {"stage": stage, "strength": strength, "time": now_ts}

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_bot()
    
