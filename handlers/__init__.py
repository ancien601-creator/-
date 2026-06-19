from aiogram import Router

def get_handlers_router() -> Router:
    from . import admin, client
    
    master_router = Router()
    # Важно: Сначала подключаем клиентский роутер, чтобы перехватывать deep linking /start contest_X 
    # до того, как его поймает дефолтный административный /start
    master_router.include_router(client.router)
    master_router.include_router(admin.router)
    
    return master_router
