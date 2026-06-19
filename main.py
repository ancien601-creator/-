import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import Message

# Импорт твоих конфигов и базы данных
# (Убедись, что переменные и пути совпадают с твоим проектом)
from config import BOT_TOKEN
from database import Database

# ЕСЛИ ХЭНДЛЕРЫ В ОТДЕЛЬНОМ ФАЙЛЕ (например, handlers.py):
# раскомментируй строку ниже и строку с include_router в функции main
# from handlers import router as main_router

async def main():
    # Настройка логирования в stdout, чтобы Railway корректно читал логи
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout
    )

    # 1. Инициализируем базу данных
    try:
        await Database.init_db()
        logging.info("База данных успешно инициализирована.")
    except Exception as e:
        logging.error(f"Ошибка при запуске базы данных: {e}")
        return

    # 2. Инициализируем бота с поддержкой HTML-тегов (для aiogram 3.7+)
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    
    dp = Dispatcher()

    # 3. Регистрация хэндлеров
    # Если используешь отдельный роутер для хэндлеров, подключи его здесь:
    # dp.include_router(main_router)

    # Тестовый хэндлер прямо в main.py, чтобы проверить реакцию на /start
    @dp.message(CommandStart())
    async def command_start_handler(message: Message) -> None:
        user_name = html.bold(message.from_user.full_name)
        await message.answer(f"Привет, {user_name}! Бот успешно запущен и отвечает.")

    # 4. Сброс незавершенных обновлений (чтобы бот не спамил старыми ответами при перезапуске)
    await bot.delete_webhook(drop_pending_updates=True)

    # 5. Запуск пуллинга
    logging.info("Бот переходит в режим ожидания сообщений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот принудительно остановлен пользователем.")
