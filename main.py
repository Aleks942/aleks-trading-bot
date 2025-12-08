import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 1 — NO EXCHANGES) ===", flush=True)

# =========================
# ЗАГРУЗКА НАСТРОЕК
# =========================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ TELEGRAM_TOKEN или TELEGRAM_CHAT_ID не заданы", flush=True)

HEARTBEAT_INTERVAL = 60 * 5  # 5 минут

SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "DOGE/USDT",
    "NEAR/USDT",
    "ARB/USDT",
    "MINA/USDT",
    "STRK/USDT",
    "ZK/USDT",
    "NOT/USDT",
    "1INCH/USDT",
    "LDO/USDT"
]

# =========================
# TELEGRAM
# =========================

def send_telegram(message: str):
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print("❌ Telegram не настроен", flush=True)
            return

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }

        r = requests.post(url, data=payload, timeout=10)

        if r.status_code == 200:
            print("=== TELEGRAM SENT OK ===", flush=True)
        else:
            print(f"❌ TELEGRAM STATUS {r.status_code}: {r.text}", flush=True)

    except Exception as e:
        print("❌ TELEGRAM ERROR:", e, flush=True)

# =========================
# ОСНОВНОЙ ЦИКЛ (ШАГ 1)
# =========================

def run_bot_step1():
    print("=== BOT LOOP STARTED (STEP 1) ===", flush=True)

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            msg = (
                "🟢 Бот жив (ШАГ 1)\n\n"
                "Источник рынков: ОТКЛЮЧЕН\n"
                "Биржи: НЕ используются\n"
                "DEX: НЕ подключены\n\n"
                f"UTC Время: {now}\n"
                f"Монет в списке: {len(SYMBOLS)}\n\n"
                "Статус: проверка стабильности Railway"
            )

            send_telegram(msg)

        except Exception as e:
            print("❌ LOOP ERROR (STEP 1):", e, flush=True)

        time.sleep(HEARTBEAT_INTERVAL)

# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":
    try:
        print("=== MAIN ENTERED (STEP 1) ===", flush=True)
        send_telegram("✅ Бот запущен (ШАГ 1). Проверка стабильной работы без источников данных.")
        run_bot_step1()

    except Exception as e:
        print("🔥 FATAL START ERROR (STEP 1):", e, flush=True)
        while True:
            time.sleep(30)
