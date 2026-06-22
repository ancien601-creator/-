from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards import main_menu_kb, manage_channels_kb
from db.database import get_admin_channels, add_admin_channel, remove_admin_channel
from utils.helpers import check_bot_admin, resolve_channel
from utils.states import AddChannel

router = Router()


async def show_main_menu(target, text: str = "👋 Главное меню:"):
    kb = main_menu_kb()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    elif isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(call)
    await call.answer()


# ──────────────────────── CHANNELS ────────────────────────

@router.callback_query(F.data == "my_channels")
async def my_channels(call: CallbackQuery):
    channels = await get_admin_channels(call.from_user.id)
    text = (
        "📡 <b>Ваши каналы:</b>\n\nНажмите на канал, чтобы удалить его."
        if channels else
        "📡 <b>Каналы не добавлены.</b>\n\nДобавьте канал где бот является администратором."
    )
    await call.message.edit_text(text, reply_markup=manage_channels_kb(channels))
    await call.answer()


@router.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.waiting_channel)
    await call.message.edit_text(
        "📡 Перешлите любое сообщение из канала <b>или</b> введите @username канала.\n\n"
        "⚠️ Бот должен быть администратором этого канала."
    )
    await call.answer()


@router.message(AddChannel.waiting_channel, F.forward_from_chat)
async def add_channel_forwarded(message: Message, state: FSMContext, bot: Bot):
    chat = message.forward_from_chat
    is_admin = await check_bot_admin(bot, chat.id)
    if not is_admin:
        await message.answer("❌ Бот не является администратором этого канала.")
        return
    await add_admin_channel(message.from_user.id, chat.id, chat.title, chat.username or "")
    await state.clear()
    channels = await get_admin_channels(message.from_user.id)
    await message.answer(f"✅ Канал <b>{chat.title}</b> добавлен!", reply_markup=manage_channels_kb(channels))


@router.message(AddChannel.waiting_channel)
async def add_channel_username(message: Message, state: FSMContext, bot: Bot):
    info = await resolve_channel(bot, message.text.strip())
    if not info:
        await message.answer("❌ Канал не найден. Проверьте @username.")
        return
    is_admin = await check_bot_admin(bot, info["id"])
    if not is_admin:
        await message.answer("❌ Бот не является администратором этого канала.")
        return
    await add_admin_channel(message.from_user.id, info["id"], info["title"], info.get("username", ""))
    await state.clear()
    channels = await get_admin_channels(message.from_user.id)
    await message.answer(f"✅ Канал <b>{info['title']}</b> добавлен!", reply_markup=manage_channels_kb(channels))


@router.callback_query(F.data.startswith("del_ch:"))
async def delete_channel(call: CallbackQuery):
    channel_id = int(call.data.split(":")[1])
    await remove_admin_channel(call.from_user.id, channel_id)
    channels = await get_admin_channels(call.from_user.id)
    await call.message.edit_text("🗑 Канал удалён.\n\n📡 <b>Ваши каналы:</b>", reply_markup=manage_channels_kb(channels))
    await call.answer("Канал удалён")
