import requests

BOT_TOKEN = "ТВОЙ_ТОКЕН"
CHAT_ID = "ТВОЙ_CHAT_ID"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
r = requests.post(url, json={
    "chat_id": CHAT_ID,
    "text": "✅ TEST MESSAGE FROM RAILWAY"
})

print(r.text)
