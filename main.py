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

# Europe/Warsaw = UTC+1 зимой. Ты просил 7:30 — делаем по Варшаве.
WARSAW_OFFSET_HOURS = 1

# ===== SETTINGS =====
CHECK_INTERVAL_SEC = 60 * 10            # цикл 10 минут
COINS_LIMIT = 200

# фильтры/пороговые
FLAT_RANGE_MAX = 1.5                   # % диапазон флета для "подготовки"
OVERHEAT_4H = 6.0                      # перегрев по 4ч
COOLDOWN_MIN = 90                      # анти-спам на монету

# AGGRESSIVE (раньше SAFE)
AGG_VOL_MIN = 1.6                      # объём ≥ x1.6
AGG_IMPULSE_FACTOR = 0.7               # доля от динамического порога

# SAFE (строже)
SAFE_MIN_STRENGTH = 4                  # сила для SAFE
CONFIRM_WINDOW_HOURS = 6               # окно "AGG → SAFE подтверждён"

# отчёты
FORECAST_HOUR = 7
FORECAST_MINUTE = 30
DAILY_REPORT_HOUR = 20
DAILY_REPORT_MINUTE = 30
WEEKLY_REPORT_WEEKDAY = 0              # понедельник
WEEKLY_REPORT_HOUR = 10
WEEKLY_REPORT_MINUTE = 0

# хранение состояния (желательно на persistent volume)
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
            # защита: state должен быть dict
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
        # защита: должны получить list[dict], а не строку/словарь ошибки
        if not isinstance(data, list):
            return []
        return data
    except:
        return []

def get_market_chart(coin_id):
    """
    Берём 2 дня: хватает для 1h/4h логики.
    """
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 2}
        data = requests.get(url, params=params, timeout=20).json()
        # data должен быть dict
        if not isinstance(data, dict):
            return None, None
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
    """
    Динамический порог: 2× среднее абсолютное изменение.
    """
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

def memo_by_strength(strength):
    if strength <= 2:
        return "• ранний кандидат\n• просто наблюдать\n• без входа"
    if strength == 3:
        return "• наблюдай, жди структуру\n• вход только со стопом"
    if strength >= 4:
        return "• не FOMO\n• жди паузу/ретест\n• риск не увеличивать"
    return ""

def conclusion_for_safe():
    return "🟢 <b>МОЖНО ПЛАНИРОВАТЬ</b>\n(вход только по структуре на 5–15m)"

def conclusion_for_agg():
    return "🔴 <b>НЕ ВХОД</b>\n(ранний радар: наблюдать и ждать структуру)"

# ===== MARKET MODE (для утреннего прогноза, простая оценка) =====
def market_mode_snapshot(coins_sample):
    """
    Простой срез: сколько монет в плюсе/минусе по 4ч и есть ли 'широкий рынок'.
    """
    ups = downs = 0
    for c in coins_sample[:60]:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if not cid:
            continue
        prices, vols = get_market_chart(cid)
        if prices is None:
            continue
        chg4 = pct_change(prices, 4)
        if chg4 > 0.8:
            ups += 1
        elif chg4 < -0.8:
            downs += 1

    if ups >= 20 and ups > downs:
        return "🟢 ТРЕНДОВЫЙ"
    if downs >= 20 and downs > ups:
        return "🔴 СЛАБЫЙ"
    return "🟡 НЕЙТРАЛЬНЫЙ"

# ===== REPORTS =====
def warsaw_now():
    return datetime.utcnow() + timedelta(hours=WARSAW_OFFSET_HOURS)

def should_fire_at(now_dt, hour, minute):
    return now_dt.hour == hour and now_dt.minute == minute

# ===== MAIN =====
def run_bot():
    state = load_state()

    # ===== ЗАЩИТА STATE (ключевое — убирает 'str'.get) =====
    if not isinstance(state, dict):
        state = {}
    if not isinstance(state.get("coins", {}), dict):
        state["coins"] = {}
    if not isinstance(state.get("stats", {}), dict):
        state["stats"] = {}

    # структура state:
    # state = {
    #   "coins": { coin_id: {"last_sent_ts":..., "last_type":"AGG/SAFE", "last_stage":..., "last_strength":..., "last_agg_ts":..., "last_agg_dir": "UP/DOWN"} },
    #   "stats": { "day":"YYYY-MM-DD", "agg":0, "safe":0, "confirmed":0, "week":"YYYY-WW", "w_agg":0, "w_safe":0, "w_confirmed":0 },
    #   "last_forecast_day":"YYYY-MM-DD",
    #   "last_daily_day":"YYYY-MM-DD",
    #   "last_weekly_week":"YYYY-WW"
    # }

    coins_state = state.get("coins", {})
    stats = state.get("stats", {})
    if not stats:
        stats = {
            "day": warsaw_now().strftime("%Y-%m-%d"),
            "agg": 0,
            "safe": 0,
            "confirmed": 0,
            "week": warsaw_now().strftime("%G-%V"),
            "w_agg": 0,
            "w_safe": 0,
            "w_confirmed": 0
        }

    # стартовое сообщение один раз за сутки — через state-файл (чтобы не спамило при рестартах)
    today = warsaw_now().strftime("%Y-%m-%d")
    if state.get("start_day") != today:
        send_telegram("📡 <b>Радар рынка запущен</b>\n200 монет • 1h + 4h • SAFE + AGGRESSIVE • статистика • прогноз 07:30")
        state["start_day"] = today

    save_state({"coins": coins_state, "stats": stats, **{k: v for k, v in state.items() if k not in ("coins", "stats")}})

    while True:
        try:
            now = warsaw_now()
            day_key = now.strftime("%Y-%m-%d")
            week_key = now.strftime("%G-%V")

            # rollover day/week in stats
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

            # ===== утренний прогноз (07:30 Warsaw) =====
            if should_fire_at(now, FORECAST_HOUR, FORECAST_MINUTE) and state.get("last_forecast_day") != day_key:
                coins = get_top_coins()
                mode = market_mode_snapshot(coins)

                hint = "Тактика: SAFE — основной, AGGRESSIVE — только как радар."
                if mode.startswith("🟢"):
                    hint = "Тактика: смотри AGGRESSIVE, жди SAFE, работай выборочно."
                elif mode.startswith("🔴"):
                    hint = "Тактика: осторожно. Пропуск — ок. Только самые чистые SAFE."

                msg = (
                    "🧭 <b>ПРОГНОЗ ДНЯ</b>\n\n"
                    f"Режим рынка: <b>{mode}</b>\n"
                    f"{hint}\n\n"
                    "⛔ Если за 10 минут нет ясности — SKIP."
                )
                send_telegram(msg)
                state["last_forecast_day"] = day_key

            # ===== дневной отчёт (20:30 Warsaw) =====
            if should_fire_at(now, DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE) and state.get("last_daily_day") != day_key:
                agg = stats.get("agg", 0)
                safe = stats.get("safe", 0)
                conf = stats.get("confirmed", 0)

                quality = "🟡 НЕЙТРАЛЬНОЕ"
                rate = (conf / agg * 100.0) if agg > 0 else 0.0
                if agg >= 6 and rate >= 30:
                    quality = "🟢 ХОРОШЕЕ"
                elif agg >= 6 and rate < 15:
                    quality = "🔴 ШУМНОЕ"

                send_telegram(
                    "📊 <b>ИТОГ ДНЯ (AGGRESSIVE → SAFE)</b>\n\n"
                    f"AGGRESSIVE: {agg}\n"
                    f"SAFE: {safe}\n"
                    f"Подтверждений: {conf}\n\n"
                    f"Качество рынка: <b>{quality}</b>\n"
                )
                state["last_daily_day"] = day_key
                state["yesterday_quality"] = quality

            # ===== недельный отчёт (Пн 10:00 Warsaw) =====
            if (now.weekday() == WEEKLY_REPORT_WEEKDAY and
                should_fire_at(now, WEEKLY_REPORT_HOUR, WEEKLY_REPORT_MINUTE) and
                state.get("last_weekly_week") != week_key):

                send_telegram(
                    "📈 <b>СТАТИСТИКА НЕДЕЛИ</b>\n\n"
                    f"AGGRESSIVE: {stats.get('w_agg', 0)}\n"
                    f"SAFE: {stats.get('w_safe', 0)}\n"
                    f"Подтверждений: {stats.get('w_confirmed', 0)}\n"
                )
                state["last_weekly_week"] = week_key

            # ===== основной радар =====
            coins = get_top_coins()
            now_ts = datetime.utcnow().timestamp()

            for coin in coins:
                # защита: coin должен быть dict
                if not isinstance(coin, dict):
                    continue

                cid = coin.get("id")
                sym = coin.get("symbol", "").upper()
                if not cid:
                    continue

                prices, volumes = get_market_chart(cid)
                if prices is None:
                    continue

                cs = coins_state.get(cid, {})
                if not isinstance(cs, dict):
                    cs = {}

                last_sent_ts = cs.get("last_sent_ts", 0)
                if last_sent_ts and (now_ts - last_sent_ts) < (COOLDOWN_MIN * 60):
                    continue

                # расчёты
                price_range = (prices.max() - prices.min()) / prices.mean() * 100.0 if prices.mean() else 0.0
                vol_avg = volumes[:-12].mean() if len(volumes) > 12 else volumes.mean()
                vol_now = volumes.iloc[-1]
                vol_mult = (vol_now / vol_avg) if vol_avg and vol_avg > 0 else 0.0

                chg_1h = pct_change(prices, 1)
                chg_4h = pct_change(prices, 4)
                dyn_thr = dynamic_threshold(prices)

                # направление (грубо) — нужно для "подтверждён"
                direction = "UP" if chg_1h >= 0 else "DOWN"

                stage = None
                reasons = []
                strength = 0

                # сила от объёма
                if vol_mult >= 1.6:
                    strength += 1
                if vol_mult >= 2.0:
                    strength += 1
                if vol_mult >= 3.0:
                    strength += 1

                # подготовка
                if vol_mult >= 2.0 and price_range <= FLAT_RANGE_MAX:
                    stage = "ПОДГОТОВКА"
                    reasons += ["Цена во флете", f"Объём x{vol_mult:.1f}"]
                    strength += 1

                # запуск
                launch_impulse = abs(chg_1h) >= dyn_thr
                if vol_mult >= 3.0 and launch_impulse:
                    stage = "ЗАПУСК"
                    reasons += [f"Импульс 1ч {chg_1h:.2f}%", "Есть объём"]
                    strength += 1

                # перегрев
                if abs(chg_4h) >= OVERHEAT_4H:
                    stage = "ПЕРЕГРЕВ"
                    reasons += [f"Импульс 4ч {chg_4h:.2f}%", "Риск выдоха"]
                    strength += 1

                # подтверждение 1h + 4h в одну сторону
                if chg_1h * chg_4h > 0:
                    strength += 1
                    reasons.append("1h + 4h в одну сторону")

                # --------- AGGRESSIVE условия (раньше SAFE) ----------
                agg_impulse = abs(chg_1h) >= max(dyn_thr * AGG_IMPULSE_FACTOR, 0.6)
                is_aggressive = (vol_mult >= AGG_VOL_MIN and agg_impulse and stage != "ПЕРЕГРЕВ")

                # --------- SAFE условия (строже) ----------
                is_safe = (stage == "ЗАПУСК" and strength >= SAFE_MIN_STRENGTH and abs(chg_4h) < OVERHEAT_4H)

                if not is_aggressive and not is_safe:
                    continue

                # выбираем тип: SAFE приоритетнее
                sig_type = "SAFE" if is_safe else "AGG"

                # анти-дубликат: если одинаковое уже было
                if cs.get("last_type") == sig_type and cs.get("last_stage") == stage and cs.get("last_strength") == strength:
                    continue

                # --- логика подтверждения ---
                confirmed_tag = ""
                confirmed = False
                if sig_type == "SAFE":
                    last_agg_ts = cs.get("last_agg_ts", 0)
                    last_agg_dir = cs.get("last_agg_dir")
                    if last_agg_ts and (now_ts - last_agg_ts) <= (CONFIRM_WINDOW_HOURS * 3600) and last_agg_dir == direction:
                        confirmed = True
                        confirmed_tag = "\n<b>AGGRESSIVE → SAFE подтверждён</b>"

                # сформировать сообщение
                emoji = {"ПОДГОТОВКА": "🟢", "ЗАПУСК": "🟡", "ПЕРЕГРЕВ": "🔴"}.get(stage, "⚪")
                fire = "🔥" * max(1, min(strength, 5))
                strength_norm = max(1, min(strength, 5))

                if sig_type == "AGG":
                    title = f"⚠️ <b>AGGRESSIVE</b> — ранний радар"
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
                    f"Причины:\n• " + "\n• ".join(reasons) +
                    f"\n\n{memo_intraday()}\n\n"
                    f"🧠 <b>ВЫВОД</b>:\n{conclusion}"
                )

                send_telegram(msg)

                # обновить стейт монеты
                cs["last_sent_ts"] = now_ts
                cs["last_type"] = sig_type
                cs["last_stage"] = stage
                cs["last_strength"] = strength_norm

                # сохранить AGG “якорь” для будущего подтверждения
                if sig_type == "AGG":
                    cs["last_agg_ts"] = now_ts
                    cs["last_agg_dir"] = direction

                coins_state[cid] = cs

                # обновить статистику
                if sig_type == "AGG":
                    stats["agg"] = stats.get("agg", 0) + 1
                    stats["w_agg"] = stats.get("w_agg", 0) + 1
                else:
                    stats["safe"] = stats.get("safe", 0) + 1
                    stats["w_safe"] = stats.get("w_safe", 0) + 1
                    if confirmed:
                        stats["confirmed"] = stats.get("confirmed", 0) + 1
                        stats["w_confirmed"] = stats.get("w_confirmed", 0) + 1

            # сохранить состояние
            state["coins"] = coins_state
            state["stats"] = stats
            save_state(state)

        except Exception as e:
            send_telegram(f"❌ <b>BOT ERROR</b>: {e}")

        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    run_bot()
