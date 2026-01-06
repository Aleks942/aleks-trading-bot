import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta
import statistics

from signals import range_breakout_5m

print("=== CRYPTO RADAR (SAFE + AGGRESSIVE + CONFIRM + STATS + 07:30 FORECAST) ===", flush=True)

# ===== ENV =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

WARSAW_OFFSET_HOURS = 1  # Europe/Warsaw (зима)

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

# RANGE → BREAKOUT
RB_COOLDOWN_MIN = 60  # 1 раз в час на монету

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
        if not BOT_TOKEN or not CHAT_ID:
            return
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
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
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
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
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": 2},
            timeout=20
        ).json()
        prices = [p[1] for p in r.get("prices", [])]
        vols = [v[1] for v in r.get("total_volumes", [])]
        if len(prices) < 24:
            return None, None
        return pd.Series(prices), pd.Series(vols)
    except:
        return None, None

def build_5m_candles(prices, volumes, window=30):
    if prices is None or volumes is None:
        return None
    if len(prices) < window:
        return None

    df = pd.DataFrame({
        "close": prices.iloc[-window:].values,
        "volume": volumes.iloc[-window:].values
    })
    df["open"] = df["close"].shift(1)
    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)
    df = df.dropna()
    return df[["open", "high", "low", "close", "volume"]]

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

# ===== TIME =====
def warsaw_now():
    return datetime.utcnow() + timedelta(hours=WARSAW_OFFSET_HOURS)

def should_fire_at(now, h, m):
    return now.hour == h and now.minute == m

# ===== MAIN =====
def run_bot():
    state = load_state()
    coins_state = state.get("coins", {})
    stats = state.get("stats", {
        "day": warsaw_now().strftime("%Y-%m-%d"),
        "agg": 0, "safe": 0, "confirmed": 0,
        "week": warsaw_now().strftime("%G-%V"),
        "w_agg": 0, "w_safe": 0, "w_confirmed": 0
    })

    send_telegram(
        "📡 <b>Радар рынка запущен</b>\n"
        "200 монет • 1h + 4h • SAFE + AGGRESSIVE • статистика • прогноз 07:30"
    )

    while True:
        try:
            now = warsaw_now()
            now_ts = datetime.utcnow().timestamp()

            coins = get_top_coins()

            for coin in coins:
                cid = coin.get("id")
                sym = coin.get("symbol", "").upper()

                prices, volumes = get_market_chart(cid)
                if prices is None:
                    continue

                cs = coins_state.get(cid, {})

                # ===== 🔵 RANGE → BREAKOUT (5m) =====
                rb_last_ts = cs.get("rb_last_ts", 0)
                rb_last_range = cs.get("rb_last_range")

                if (not rb_last_ts) or ((now_ts - rb_last_ts) >= RB_COOLDOWN_MIN * 60):
                    candles_5m = build_5m_candles(prices, volumes)
                    if candles_5m is not None and len(candles_5m) >= 21:
                        rb = range_breakout_5m(candles_5m)
                    else:
                        rb = None

                    if rb:
                        if rb_last_range != rb["range_pct"]:
                            send_telegram(
                                "🔵 <b>RANGE → BREAKOUT (5m)</b>\n\n"
                                f"<b>{sym}</b>\n"
                                f"Флет: {rb['range_pct']}%\n"
                                f"Свеча: +{rb['candle_move']}%\n"
                                f"Объём: x{rb['volume_x']}\n\n"
                                "⚠️ <b>ВНИМАНИЕ, НЕ ВХОД</b>\n"
                                "Ждать паузу → брать 3–7%"
                            )
                            cs["rb_last_ts"] = now_ts
                            cs["rb_last_range"] = rb["range_pct"]

                # ===== COOLDOWN SAFE / AGG =====
                if cs.get("last_sent_ts") and (now_ts - cs["last_sent_ts"]) < COOLDOWN_MIN * 60:
                    coins_state[cid] = cs
                    continue

                price_range = (prices.max() - prices.min()) / prices.mean() * 100.0 if prices.mean() else 0.0
                vol_avg = volumes[:-12].mean() if len(volumes) > 12 else volumes.mean()
                vol_now = volumes.iloc[-1]
                vol_mult = (vol_now / vol_avg) if vol_avg and vol_avg > 0 else 0.0

                chg_1h = pct_change(prices, 1)
                chg_4h = pct_change(prices, 4)
                dyn_thr = dynamic_threshold(prices)

                stage = None
                strength = 0

                if vol_mult >= 1.6: strength += 1
                if vol_mult >= 2.0: strength += 1
                if vol_mult >= 3.0: strength += 1

                if vol_mult >= 2.0 and price_range <= FLAT_RANGE_MAX:
                    stage = "ПОДГОТОВКА"
                    strength += 1

                if vol_mult >= 3.0 and abs(chg_1h) >= dyn_thr:
                    stage = "ЗАПУСК"
                    strength += 1

                if abs(chg_4h) >= OVERHEAT_4H:
                    stage = "ПЕРЕГРЕВ"
                    strength += 1

                is_agg = vol_mult >= AGG_VOL_MIN and abs(chg_1h) >= dyn_thr * AGG_IMPULSE_FACTOR
                is_safe = stage == "ЗАПУСК" and strength >= SAFE_MIN_STRENGTH

                if not is_agg and not is_safe:
                    coins_state[cid] = cs
                    continue

                sig_type = "SAFE" if is_safe else "AGG"
                send_telegram(f"{'✅ SAFE' if sig_type=='SAFE' else '⚠️ AGG'} • <b>{sym}</b>")

                cs["last_sent_ts"] = now_ts
                cs["last_type"] = sig_type
                coins_state[cid] = cs

            state["coins"] = coins_state
            state["stats"] = stats
            save_state(state)

        except Exception as e:
            send_telegram(f"❌ <b>BOT ERROR</b>: {e}")

        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    run_bot()
