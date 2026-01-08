import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta
import statistics

print("=== CRYPTO RADAR (SAFE + AGGRESSIVE + CONFIRM + STATS + 07:30 FORECAST) ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

WARSAW_OFFSET_HOURS = 1

# ===== SETTINGS =====
CHECK_INTERVAL_SEC = 60 * 10
COINS_LIMIT = 200

FLAT_RANGE_MAX = 1.5
OVERHEAT_4H = 6.0
COOLDOWN_MIN = 90

AGG_VOL_MIN = 1.6
AGG_IMPULSE_FACTOR = 0.7

SAFE_MIN_STRENGTH = 4
CONFIRM_WINDOW_HOURS = 6

FORECAST_HOUR = 7
FORECAST_MINUTE = 30
DAILY_REPORT_HOUR = 20
DAILY_REPORT_MINUTE = 30
WEEKLY_REPORT_WEEKDAY = 0
WEEKLY_REPORT_HOUR = 10
WEEKLY_REPORT_MINUTE = 0

STATE_DIR = os.getenv("STATE_DIR", ".")
STATE_FILE = os.path.join(STATE_DIR, "crypto_radar_state.json")

# ===== TELEGRAM =====
def send_telegram(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except:
        pass

# ===== STATE IO =====
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
    except:
        return {}

def save_state(data):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass

# ===== DATA (COINGECKO) =====
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
        r = requests.get(url, params=params, timeout=30)
        data = r.json()
        if not isinstance(data, list):
            return []
        return data
    except:
        return []

def get_market_chart(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 2}
        data = requests.get(url, params=params, timeout=20).json()
        prices = [p[1] for p in data.get("prices", [])]
        vols = [v[1] for v in data.get("total_volumes", [])]
        if len(prices) < 24 or len(vols) < 24:
            return None, None
        return pd.Series(prices), pd.Series(vols)
    except:
        return None, None

def pct_change(series, h):
    if len(series) < h + 1:
        return 0.0
    base = series.iloc[-(h + 1)]
    if base == 0:
        return 0.0
    return (series.iloc[-1] - base) / base * 100.0

def dynamic_threshold(series):
    try:
        changes = []
        for i in range(1, len(series)):
            prev = series.iloc[i - 1]
            if prev == 0:
                continue
            changes.append(abs((series.iloc[i] - prev) / prev * 100))
        if len(changes) < 10:
            return 1.0
        return max(statistics.mean(changes) * 2, 0.8)
    except:
        return 1.0

# ===== MEMO + CONCLUSION =====
def memo_intraday():
    return (
        "🕒 <b>Интрадей-чек</b> (5–10 мин)\n"
        "1) 5–15m: импульс → пауза → продолжение?\n"
        "2) вход только после структуры (ретест/вторая свеча)\n"
        "3) стоп за локальный экстремум\n"
        "⛔ если за 10 минут нет ясности — SKIP"
    )

def conclusion_for_safe():
    return "🟢 <b>МОЖНО ПЛАНИРОВАТЬ</b>\n(вход только по структуре на 5–15m)"

def conclusion_for_agg():
    return "🔴 <b>НЕ ВХОД</b>\n(ранний радар: наблюдать и ждать структуру)"

# ===== TIME =====
def warsaw_now():
    return datetime.utcnow() + timedelta(hours=WARSAW_OFFSET_HOURS)

def should_fire_at(now_dt, hour, minute):
    return now_dt.hour == hour and now_dt.minute == minute

# ===== MAIN =====
def run_bot():
    state = load_state()

    # === STATE PROTECTION (НЕ МЕНЯЕТ ЛОГИКУ) ===
    if not isinstance(state, dict):
        state = {}

    if not isinstance(state.get("coins", {}), dict):
        state["coins"] = {}

    if not isinstance(state.get("stats", {}), dict):
        state["stats"] = {}

    coins_state = state["coins"]
    stats = state["stats"]

    if not stats:
        stats.update({
            "day": warsaw_now().strftime("%Y-%m-%d"),
            "agg": 0,
            "safe": 0,
            "confirmed": 0,
            "week": warsaw_now().strftime("%G-%V"),
            "w_agg": 0,
            "w_safe": 0,
            "w_confirmed": 0
        })

    today = warsaw_now().strftime("%Y-%m-%d")
    if state.get("start_day") != today:
        send_telegram(
            "📡 <b>Радар рынка запущен</b>\n"
            "200 монет • 1h + 4h • SAFE + AGGRESSIVE • статистика • прогноз 07:30"
        )
        state["start_day"] = today

    save_state(state)

    while True:
        try:
            now = warsaw_now()
            day_key = now.strftime("%Y-%m-%d")
            week_key = now.strftime("%G-%V")

            if stats.get("day") != day_key:
                stats["day"] = day_key
                stats["agg"] = 0
                stats["safe"] = 0
                stats["confirmed"] = 0

            if stats.get("week") != week_key:
                stats["week"] = week_key
                stats["w_agg"] = 0
                stats["w_safe"] = 0
                stats["w_confirmed"] = 0

            coins = get_top_coins()
            now_ts = datetime.utcnow().timestamp()

            for coin in coins:
                # === ЗАЩИТА ОТ STR ВМЕСТО DICT ===
                if not isinstance(coin, dict):
                    continue

                cid = coin.get("id")
                sym = coin.get("symbol", "").upper()

                prices, volumes = get_market_chart(cid)
                if prices is None:
                    continue

                cs = coins_state.get(cid, {})
                if not isinstance(cs, dict):
                    cs = {}

                last_sent_ts = cs.get("last_sent_ts", 0)
                if last_sent_ts and (now_ts - last_sent_ts) < (COOLDOWN_MIN * 60):
                    continue

                price_range = (prices.max() - prices.min()) / prices.mean() * 100.0 if prices.mean() else 0.0
                vol_avg = volumes[:-12].mean() if len(volumes) > 12 else volumes.mean()
                vol_now = volumes.iloc[-1]
                vol_mult = (vol_now / vol_avg) if vol_avg and vol_avg > 0 else 0.0

                chg_1h = pct_change(prices, 1)
                chg_4h = pct_change(prices, 4)
                dyn_thr = dynamic_threshold(prices)

                direction = "UP" if chg_1h >= 0 else "DOWN"

                stage = None
                reasons = []
                strength = 0

                if vol_mult >= 1.6: strength += 1
                if vol_mult >= 2.0: strength += 1
                if vol_mult >= 3.0: strength += 1

                if vol_mult >= 2.0 and price_range <= FLAT_RANGE_MAX:
                    stage = "ПОДГОТОВКА"
                    reasons += ["Цена во флете", f"Объём x{vol_mult:.1f}"]
                    strength += 1

                launch_impulse = abs(chg_1h) >= dyn_thr
                if vol_mult >= 3.0 and launch_impulse:
                    stage = "ЗАПУСК"
                    reasons += [f"Импульс 1ч {chg_1h:.2f}%", "Есть объём"]
                    strength += 1

                if abs(chg_4h) >= OVERHEAT_4H:
                    stage = "ПЕРЕГРЕВ"
                    reasons += [f"Импульс 4ч {chg_4h:.2f}%", "Риск выдоха"]
                    strength += 1

                if chg_1h * chg_4h > 0:
                    strength += 1
                    reasons.append("1h + 4h в одну сторону")

                agg_impulse = abs(chg_1h) >= max(dyn_thr * AGG_IMPULSE_FACTOR, 0.6)
                is_aggressive = (vol_mult >= AGG_VOL_MIN and agg_impulse and stage != "ПЕРЕГРЕВ")

                is_safe = (stage == "ЗАПУСК" and strength >= SAFE_MIN_STRENGTH and abs(chg_4h) < OVERHEAT_4H)

                if not is_aggressive and not is_safe:
                    continue

                sig_type = "SAFE" if is_safe else "AGG"

                if cs.get("last_type") == sig_type and cs.get("last_stage") == stage and cs.get("last_strength") == strength:
                    continue

                confirmed_tag = ""
                confirmed = False
                if sig_type == "SAFE":
                    last_agg_ts = cs.get("last_agg_ts", 0)
                    last_agg_dir = cs.get("last_agg_dir")
                    if last_agg_ts and (now_ts - last_agg_ts) <= (CONFIRM_WINDOW_HOURS * 3600) and last_agg_dir == direction:
                        confirmed = True
                        confirmed_tag = "\n<b>AGGRESSIVE → SAFE подтверждён</b>"

                emoji = {"ПОДГОТОВКА": "🟢", "ЗАПУСК": "🟡", "ПЕРЕГРЕВ": "🔴"}.get(stage, "⚪")
                fire = "🔥" * max(1, min(strength, 5))
                strength_norm = max(1, min(strength, 5))

                if sig_type == "AGG":
                    title = "⚠️ <b>AGGRESSIVE</b> — ранний радар"
                    conclusion = conclusion_for_agg()
                else:
                    title = f"✅ <b>SAFE</b>{confirmed_tag}"
                    conclusion = conclusion_for_safe()

                msg = (
                    f"{title}\n"
                    f"{emoji} <b>{sym}</b>\n"
                    f"Стадия: <b>{stage}</b>\n"
                    f"Сила: {fire} ({strength_norm}/5)\n\n"
                    f"1ч: {chg_1h:.2f}% | 4ч: {chg_4h:.2f}%\n"
                    f"Объём: x{vol_mult:.1f}\n\n"
                    "Причины:\n• " + "\n• ".join(reasons) +
                    f"\n\n{memo_intraday()}\n\n"
                    f"🧠 <b>ВЫВОД</b>:\n{conclusion}"
                )

                send_telegram(msg)

                cs["last_sent_ts"] = now_ts
                cs["last_type"] = sig_type
                cs["last_stage"] = stage
                cs["last_strength"] = strength_norm

                if sig_type == "AGG":
                    cs["last_agg_ts"] = now_ts
                    cs["last_agg_dir"] = direction

                coins_state[cid] = cs

                if sig_type == "AGG":
                    stats["agg"] += 1
                    stats["w_agg"] += 1
                else:
                    stats["safe"] += 1
                    stats["w_safe"] += 1
                    if confirmed:
                        stats["confirmed"] += 1
                        stats["w_confirmed"] += 1

            state["coins"] = coins_state
            state["stats"] = stats
            save_state(state)

        except Exception as e:
            send_telegram(f"❌ <b>BOT ERROR</b>: {e}")

        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    run_bot()
