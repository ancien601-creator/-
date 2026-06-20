import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8821231189:AAE6rlFTF4iIR7r-YtOBLVpqD0XHnlw3avk")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
DB_PATH = os.getenv("DB_PATH", "giveaway.db")
