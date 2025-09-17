import requests

BOT_TOKEN = "7247278760:AAHh1XCjoEoQ0oLpt7yUIOruQ2biMHCd5so"
WEBHOOK_URL = "https://arada-bingo-dv-oxct.onrender.com/webhook"

response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    data={"url": WEBHOOK_URL}
)

print(response.json())
