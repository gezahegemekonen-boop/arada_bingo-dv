import requests

BOT_TOKEN = "your-real-bot-token-here"
WEBHOOK_URL = "https://arada-bingo-dv-oxct.onrender.com/webhook"

response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    data={"url": WEBHOOK_URL}
)

print(response.json())
