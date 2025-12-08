import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime

print("=== BOT BOOT STARTED (STEP 1 SIMPLE) ===", flush=True)

# =========================
# ЗАГРУЗКА ПЕРЕМЕННЫХ
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print("❌ BOT_TOKEN или CHAT_ID не заданы в Railway", flush=True)

HEARTBEAT_INTERVAL = 60 * 5  # 5 минут

# =========================
# TELEGRAM
# =========================

def send_telegram(message: str):
    try:
        if not BOT_TOKEN or not CHAT_ID:
            print("❌ Telegram не настроен (нет токена или chat_id)", flush=True)
            return

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message
        }

        r = requests.post(url, data=payload, timeout=10)

        if r.status_code == 200:
            print("=== TELEGRAM SENT OK ===", flush=True)
        else:
            print(f"❌ TELEGRAM ERROR {r.status_code}: {r.text}", flush=True)

    except Exception as e:
        print("❌ TELEGRAM EXCEPTION:", e, flush=True)

# =========================
# ОСНОВНОЙ ЦИКЛ
# =========================

def run_bot():
    print("=== BOT LOOP STARTED (STEP 1 SIMPLE) ===", flush=True)

    while True:
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            msg = (
                "🟢 Бот жив\n\n"
                "Режим: тестовый (ШАГ 1)\n"
                "Источники рынка: отключены\n\n"
                f"UTC время: {now}"
            )

            send_telegram(msg)

        except Exception as e:
            print("❌ LOOP ERROR:", e, flush=True)

        time.sleep(HEARTBEAT_INTERVAL)

# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":
    try:
        print("=== MAIN ENTERED (STEP 1 SIMPLE) ===", flush=True)
        send_telegram("✅ Бот запущен (ШАГ 1). Проверка связи с Telegram.")
        run_bot()

    except Exception as e:
        print("🔥 FATAL START ERROR:", e, flush=True)
        while True:
            time.sleep(30)
