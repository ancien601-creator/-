import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

# Импорт твоих конфигов и базы данных
from config import BOT_TOKEN
from database import Database

# Импорт общего роутера из твоей папки с хэндлерами
# (Убедись, что папка называется handlers, а роутер внутри неё — router)
from handlers import router


async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout
    )

    # Инициализация базы данных
    try:
        await Database.init_db()
        logging.info("База данных успешно инициализирована.")
    except Exception as e:
        logging.error(f"Ошибка при запуске базы данных: {e}")
        return

    # Инициализация бота с настройками по умолчанию (aiogram 3.7+)
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    
    dp = Dispatcher()

    # ПОДКЛЮЧЕНИЕ ТВОИХ ХЭНДЛЕРОВ ИЗ ПАПКИ
    dp.include_router(router)

    # Сброс старых апдейтов, чтобы бот не отвечал на старые сообщения при запуске
    await bot.delete_webhook(drop_pending_updates=True)

    # Запуск бота
    logging.info("Бот переходит в режим ожидания сообщений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот принудительно остановлен.")
