from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from db import add_user, is_admin
from keyboards import main_menu

router = Router()

@router.message(CommandStart())
async def start_cmd(message: Message):
    user = message.from_user
    await add_user(user.id, user.username)
    admin = await is_admin(user.id)
    await message.answer(
        "👋 Добро пожаловать! Выберите действие:",
        reply_markup=main_menu(admin)
    )

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    admin = await is_admin(callback.from_user.id)
    await callback.message.edit_text(
        "👋 Главное меню:",
        reply_markup=main_menu(admin)
    )
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    text = (
        "ℹ️ <b>Справка</b>\n\n"
        "• <b>Классический розыгрыш:</b> участники нажимают кнопку, победители выбираются случайно.\n"
        "• <b>Лотерея по слотам:</b> игроки занимают слоты; один слот — выигрышный, определяется мгновенно.\n\n"
        "Для создания розыгрыша добавьте канал и нажмите «Создать проект»."
    )
    await callback.message.edit_text(text, reply_markup=main_menu(await is_admin(callback.from_user.id)))
    await callback.answer()
