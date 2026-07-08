import requests

TOKEN = "1624551307:sXvFHJ0-5wGM-VwHbGqW7DuLH0DUHNKZfP8"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

resp = requests.get(f"{BASE_URL}/getUpdates")
print(resp.json())
