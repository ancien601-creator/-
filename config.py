import os

# Токен берем из переменных окружения Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Путь к БД: если запущен на сервере, сохраняем на постоянный диск /data
if os.getenv("RAILWAY_ENVIRONMENT_NAME"):
    DB_PATH = "/data/giveaway.db"
else:
    DB_PATH = "giveaway.db"  # Локально при разработке
