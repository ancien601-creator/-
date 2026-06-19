from aiogram import Router

# Импортируем роутеры из твоих файлов
from .client import router as client_router
from .admin import router as admin_router

# Создаем главный роутер для папки handlers
router = Router()

# Подключаем к нему импортированные роутеры
router.include_router(client_router)
router.include_router(admin_router)
