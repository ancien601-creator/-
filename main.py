import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import Database
from handlers import get_handlers_router

async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    # Инициализация базы данных
    await Database.init_db()

    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher()

    # Подключение единого роутера хэндлеров
    dp.include_router(get_handlers_router())

    logging.info("Бот успешно запущен и готов к работе.")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
