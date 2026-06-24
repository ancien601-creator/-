import asyncio
import logging
import traceback

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from db.database import init_db
from handlers import participation, start, classic, slots, lottery, battle, my_projects, payments
from middlewares.admin import AdminMiddleware
from utils.scheduler import restore_schedules, background_checker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting bot...")

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.critical("BOT_TOKEN не задан!")
        return

    try:
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        me = await bot.get_me()
        logger.info(f"Авторизован как @{me.username}")
    except Exception as e:
        logger.critical(f"Ошибка авторизации: {e}")
        return

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    try:
        await init_db()
        logger.info("БД инициализирована")
    except Exception as e:
        logger.critical(f"Ошибка БД: {e}")
        traceback.print_exc()
        return

    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    # participation ПЕРВЫМ — перехватывает /start с deep link
    dp.include_router(participation.router)
    dp.include_router(start.router)
    dp.include_router(classic.router)
    dp.include_router(slots.router)
    dp.include_router(lottery.router)
    dp.include_router(battle.router)
    dp.include_router(my_projects.router)
    dp.include_router(payments.router)
    logger.info("Роутеры подключены")

    # Восстановить таймеры после перезапуска
    try:
        await restore_schedules(bot)
    except Exception as e:
        logger.error(f"restore_schedules: {e}")

    # Фоновый страховочный чекер (каждые 60 сек)
    asyncio.create_task(background_checker(bot))
    logger.info("Background checker запущен")

    logger.info("Бот запущен, polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Polling упал: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
