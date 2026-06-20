import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from db.database import init_db
from handlers import start, classic, slots, my_projects, participation, payments
from middlewares.admin import AdminMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    await init_db()

    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    dp.include_router(participation.router)  # ← ПЕРВЫМ
    dp.include_router(start.router)
    dp.include_router(classic.router)
    dp.include_router(slots.router)
    dp.include_router(my_projects.router)
    dp.include_router(payments.router)

    logger.info("Bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
