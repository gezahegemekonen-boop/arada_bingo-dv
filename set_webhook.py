import requests

# Your bot token from BotFather
BOT_TOKEN = "7247278760:AAHh1XCjoEoQ0oLpt7yUIOruQ2biMHCd5so"

# Your deployed Render URL with /webhook path
WEBHOOK_URL = "https://arada-bingo-dv-oxct.onrender.com/webhook"

# Set the webhook
response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    data={"url": WEBHOOK_URL}
)

# Print the result
print("Webhook setup response:")
print(response.json())
