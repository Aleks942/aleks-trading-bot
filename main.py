# === ШАГ 11 — ЕЖЕДНЕВНЫЙ ОТЧЁТ В 22:00 (ПОЛЬША, UTC+1) ===

import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

print("=== BOT BOOT STARTED (STEP 11 — DAILY REPORT 22:00) ===", flush=True)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 60 * 5
STATE_FILE = "last_states.json"
POSITIONS_FILE = "open_positions.json"
TRADES_LOG_FILE = "trades_log.json"
DAILY_REPORT_FILE = "daily_report_state.json"

# ===== РЕЖИМ ОТЧЁТА =====
REPORT_HOUR = 22  # 22:00 Польша (UTC+1)

# ===== РИСК =====
START_DEPOSIT = 100.0
RISK_PERCENT = 1.0
RISK_USD = START_DEPOSIT * (RISK_PERCENT / 100.0)

# ===== ФИЛЬТРЫ =====
ALT_MIN_LIQUIDITY = 100_000
ALT_MIN_VOLUME = 250_000

# ===== ИНДИКАТОРЫ =====
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_LONG_LEVEL = 35
RSI_SHORT_LEVEL = 65
EMA_FAST = 50
EMA_SLOW = 200

# ===== ТРЕЙЛИНГ =====
TRAIL_MULT = 1.5

ALT_TOKENS = ["solana", "near", "arbitrum", "mina", "starknet", "zksync-era"]

# ===== УТИЛИТЫ =====
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ===== TELEGRAM =====
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=15)
    except:
        pass

# ===== COINGECKO =====
def get_ohlc(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 3}
        data = requests.get(url, params=params, timeout=20).json()
        prices = data.get("prices", [])
        if len(prices) < 60:
            return None
        df = pd.DataFrame({"close": [x[1] for x in prices]})
        return df
    except:
        return None

def rsi(df):
    d = df["close"].diff()
    g = d.where(d > 0, 0)
    l = -d.where(d < 0, 0)
    ag = g.rolling(RSI_PERIOD).mean()
    al = l.rolling(RSI_PERIOD).mean()
    rs = ag / al
    r = 100 - (100 / (1 + rs))
    return round(float(r.dropna().iloc[-1]), 2)

def atr(df):
    tr = df["close"].diff().abs()
    return round(float(tr.rolling(ATR_PERIOD).mean().dropna().iloc[-1]), 6)

def ema(df, p):
    if len(df) < p:
        return None
    return round(float(df["close"].ewm(span=p).mean().iloc[-1]), 6)

# ===== DEX =====
def dex_data(query):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"
        data = requests.get(url, timeout=15).json()
        p = data.get("pairs", [])
        if not p:
            return None
        p = sorted(p, key=lambda x: x.get("liquidity", {}).get("usd", 0), reverse=True)[0]
        liq = p.get("liquidity", {}).get("usd", 0)
        vol = p.get("volume", {}).get("h24", 0)
        dex = p.get("dexId")
        if liq < ALT_MIN_LIQUIDITY or vol < ALT_MIN_VOLUME:
            return None
        return liq, vol, dex
    except:
        return None

# ===== ЖУРНАЛ =====
def log_trade(trade):
    log = load_json(TRADES_LOG_FILE, [])
    log.append(trade)
    save_json(TRADES_LOG_FILE, log)

def all_stats():
    log = load_json(TRADES_LOG_FILE, [])
    total = sum(t["pnl"] for t in log) if log else 0.0
    wins = len([t for t in log if t["pnl"] > 0])
    return len(log), wins, total

# ===== ОТКРЫТИЕ / ЗАКРЫТИЕ =====
def open_position(alt, side, price, atr_v, dex):
    st = price - atr_v if side == "LONG" else price + atr_v
    tp1 = price + atr_v if side == "LONG" else price - atr_v
    tp2 = price + atr_v * 2 if side == "LONG" else price - atr_v * 2
    size = round(RISK_USD / abs(price - st), 6)

    pos = {
        "alt": alt, "side": side,
        "entry": round(price, 6),
        "stop": round(st, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "atr": atr_v,
        "size": size,
        "tp1_done": False,
        "active": True,
        "dex": dex,
        "time": datetime.utcnow().isoformat()
    }

    send_telegram(
        f"<b>ОТКРЫТА СДЕЛКА</b>\n{alt.upper()} {side}\n"
        f"Вход: {price}\nSTOP: {st}\nTP1: {tp1} | TP2: {tp2}\nРазмер: {size}"
    )
    return pos

def close_trade(pos, price):
    pnl = (price - pos["entry"]) * pos["size"] if pos["side"] == "LONG" else (pos["entry"] - price) * pos["size"]

    trade = {
        "time": datetime.utcnow().isoformat(),
        "alt": pos["alt"],
        "side": pos["side"],
        "entry": pos["entry"],
        "exit": round(price, 6),
        "size": pos["size"],
        "pnl": round(pnl, 2)
    }
    log_trade(trade)

    send_telegram(
        f"✅ <b>СДЕЛКА ЗАКРЫТА</b>\n{pos['alt'].upper()} {pos['side']}\n"
        f"Вход: {pos['entry']}\nВыход: {price}\n"
        f"PnL: {round(pnl,2)}$"
    )

def update_trailing(pos, price):
    trail = pos["atr"] * TRAIL_MULT

    if pos["side"] == "LONG":
        if not pos["tp1_done"] and price >= pos["tp1"]:
            pos["tp1_done"] = True
            pos["stop"] = pos["entry"]
        if pos["tp1_done"]:
            pos["stop"] = max(pos["stop"], price - trail)
        if price <= pos["stop"]:
            pos["active"] = False
            close_trade(pos, price)
    else:
        if not pos["tp1_done"] and price <= pos["tp1"]:
            pos["tp1_done"] = True
            pos["stop"] = pos["entry"]
        if pos["tp1_done"]:
            pos["stop"] = min(pos["stop"], price + trail)
        if price >= pos["stop"]:
            pos["active"] = False
            close_trade(pos, price)

    return pos

# ===== ЕЖЕДНЕВНЫЙ ОТЧЁТ =====
def send_daily_report():
    log = load_json(TRADES_LOG_FILE, [])
    today = datetime.utcnow().date()

    todays = [t for t in log if datetime.fromisoformat(t["time"]).date() == today]

    day_pnl = sum(t["pnl"] for t in todays) if todays else 0.0
    wins = len([t for t in todays if t["pnl"] > 0])
    losses = len([t for t in todays if t["pnl"] <= 0])

    total_trades, total_wins, total_pnl = all_stats()
    deposit = START_DEPOSIT + total_pnl
    drawdown = round((START_DEPOSIT - deposit) / START_DEPOSIT * 100, 2) if deposit < START_DEPOSIT else 0.0

    report = (
        f"📊 <b>ДНЕВНОЙ ОТЧЁТ</b>\n\n"
        f"Дата: {today}\n"
        f"Сделок за день: {len(todays)}\n"
        f"Профитных: {wins}\n"
        f"Убыточных: {losses}\n"
        f"Дневной PnL: {round(day_pnl,2)}$\n\n"
        f"Всего сделок: {total_trades}\n"
        f"Всего профитных: {total_wins}\n"
        f"Общий PnL: {round(total_pnl,2)}$\n"
        f"Текущий депозит: {round(deposit,2)}$\n"
        f"Просадка: {drawdown}%"
    )

    send_telegram(report)

# ===== ОСНОВНОЙ ЦИКЛ =====
def run_bot():
    states = load_json(STATE_FILE, {})
    positions = load_json(POSITIONS_FILE, {})
    report_state = load_json(DAILY_REPORT_FILE, {"last_date": None})

    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=1)  # Польша = UTC+1

            # --- ТРЕЙЛИНГ
            for alt, pos in list(positions.items()):
                if not pos["active"]:
                    continue
                df = get_ohlc(alt)
                if df is None:
                    continue
                price = float(df["close"].iloc[-1])
                pos = update_trailing(pos, price)
                if not pos["active"]:
                    positions.pop(alt)
                else:
                    positions[alt] = pos
            save_json(POSITIONS_FILE, positions)

            # --- ПОИСК СИГНАЛОВ
            for alt in ALT_TOKENS:
                if alt in positions:
                    continue
                dd = dex_data(alt)
                df = get_ohlc(alt)
                if not dd or df is None:
                    continue

                r = rsi(df)
                a = atr(df)
                p = float(df["close"].iloc[-1])
                e50 = ema(df, EMA_FAST)
                e200 = ema(df, EMA_SLOW)

                trend = "UP" if (e50 and e200 and e50 > e200) else "DOWN"
                sig = "LONG" if r < RSI_LONG_LEVEL and trend == "UP" else "SHORT" if r > RSI_SHORT_LEVEL and trend == "DOWN" else "NEUTRAL"

                if states.get(alt) == sig:
                    continue
                states[alt] = sig
                save_json(STATE_FILE, states)

                if sig != "NEUTRAL":
                    liq, vol, dex = dd
                    pos = open_position(alt, sig, p, a, dex)
                    positions[alt] = pos
                    save_json(POSITIONS_FILE, positions)

            # --- ЕЖЕДНЕВНЫЙ ОТЧЁТ В 22:00
            today_str = now.date().isoformat()
            if now.hour == REPORT_HOUR and report_state.get("last_date") != today_str:
                send_daily_report()
                report_state["last_date"] = today_str
                save_json(DAILY_REPORT_FILE, report_state)

        except Exception as e:
            send_telegram(f"❌ BOT ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    send_telegram("✅ ШАГ 11 активирован. Дневной отчёт каждый день в 22:00.")
    run_bot()
