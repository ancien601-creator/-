from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from keyboards import main_menu_kb, manage_channels_kb, channels_list_kb
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


# handlers/start.py
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    # убери всю проверку args — participation.router обработает раньше
    await show_main_menu(message, f"👋 Привет, {message.from_user.first_name}!\n\nДобро пожаловать в бот розыгрышей и лотерей.")


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(call)
    await call.answer()


# ──────────────────────── CHANNELS MANAGEMENT ────────────────────────

@router.callback_query(F.data == "my_channels")
async def my_channels(call: CallbackQuery):
    channels = await get_admin_channels(call.from_user.id)
    if channels:
        text = "📡 <b>Ваши каналы:</b>\n\nНажмите на канал, чтобы удалить его."
        kb = manage_channels_kb(channels)
    else:
        text = "📡 <b>Каналы не добавлены.</b>\n\nДобавьте канал, в котором бот является администратором."
        kb = manage_channels_kb([])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.waiting_channel)
    await call.message.edit_text(
        "📡 Перешлите любое сообщение из канала <b>или</b> введите @username канала.\n\n"
        "⚠️ Убедитесь, что бот добавлен в этот канал как администратор."
    )
    await call.answer()


@router.message(AddChannel.waiting_channel, F.forward_from_chat)
async def add_channel_forwarded(message: Message, state: FSMContext, bot: Bot):
    chat = message.forward_from_chat
    channel_id = chat.id
    title = chat.title
    username = chat.username or ""

    is_admin = await check_bot_admin(bot, channel_id)
    if not is_admin:
        await message.answer(
            "❌ Бот не является администратором этого канала.\n"
            "Добавьте бота как администратора и попробуйте снова."
        )
        return

    await add_admin_channel(message.from_user.id, channel_id, title, username)
    await state.clear()
    channels = await get_admin_channels(message.from_user.id)
    await message.answer(
        f"✅ Канал <b>{title}</b> успешно добавлен!",
        reply_markup=manage_channels_kb(channels)
    )


@router.message(AddChannel.waiting_channel)
async def add_channel_username(message: Message, state: FSMContext, bot: Bot):
    username = message.text.strip()
    info = await resolve_channel(bot, username)
    if not info:
        await message.answer("❌ Канал не найден. Проверьте @username и попробуйте снова.")
        return

    is_admin = await check_bot_admin(bot, info["id"])
    if not is_admin:
        await message.answer(
            "❌ Бот не является администратором этого канала.\n"
            "Добавьте бота как администратора и попробуйте снова."
        )
        return

    await add_admin_channel(message.from_user.id, info["id"], info["title"], info.get("username", ""))
    await state.clear()
    channels = await get_admin_channels(message.from_user.id)
    await message.answer(
        f"✅ Канал <b>{info['title']}</b> успешно добавлен!",
        reply_markup=manage_channels_kb(channels)
    )


@router.callback_query(F.data.startswith("del_ch:"))
async def delete_channel(call: CallbackQuery):
    channel_id = int(call.data.split(":")[1])
    await remove_admin_channel(call.from_user.id, channel_id)
    channels = await get_admin_channels(call.from_user.id)
    await call.message.edit_text(
        "🗑 Канал удалён.\n\n📡 <b>Ваши каналы:</b>",
        reply_markup=manage_channels_kb(channels)
    )
    await call.answer("Канал удалён")
