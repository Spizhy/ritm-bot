import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Telegram User ID(s) of admin(s) who will receive applications
# You can find your ID via @userinfobot
ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in os.getenv("ADMIN_IDS", "").split(",")
    if admin_id.strip().isdigit()
]
