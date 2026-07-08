import requests

TOKEN = "1624551307:sXvFHJ0-5wGM-VwHbGqW7DuLH0DUHNKZfP8"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
CHAT_ID = 536174723

resp = requests.post(f"{BASE_URL}/sendMessage", json={
    "chat_id": CHAT_ID,
    "text": "سلام! این یه پیام تستیه 🎬"
})
print(resp.json())
