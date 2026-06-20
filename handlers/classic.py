import random
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

from keyboards import (
    main_menu_kb, contest_type_kb, channels_list_kb,
    finish_condition_kb, button_text_kb, confirm_kb, skip_kb, participate_kb
)
from db.database import get_admin_channels, create_contest, set_contest_message_id, add_sponsor
from utils.states import ClassicContest
from utils.helpers import check_bot_admin, resolve_channel

router = Router()


# ──────────────────────── ENTRY ────────────────────────

@router.callback_query(F.data == "create_project")
async def create_project(call: CallbackQuery):
    await call.message.edit_text(
        "🎪 Выберите тип проекта:",
        reply_markup=contest_type_kb()
    )
    await call.answer()


@router.callback_query(F.data == "type_classic")
async def start_classic(call: CallbackQuery, state: FSMContext):
    channels = await get_admin_channels(call.from_user.id)
    if not channels:
        await call.message.edit_text(
            "📡 У вас нет добавленных каналов.\n\n"
            "Сначала добавьте канал через «Мои каналы».",
            reply_markup=main_menu_kb()
        )
        await call.answer()
        return

    await state.set_state(ClassicContest.select_channel)
    await state.update_data(type="classic")
    await call.message.edit_text(
        "📢 Шаг 1/7: Выберите канал для розыгрыша:",
        reply_markup=channels_list_kb(channels)
    )
    await call.answer()


# ──────────────────────── STEP 1: CHANNEL ────────────────────────

@router.callback_query(ClassicContest.select_channel, F.data.startswith("ch:"))
async def classic_select_channel(call: CallbackQuery, state: FSMContext):
    channel_id = int(call.data.split(":")[1])
    channels = await get_admin_channels(call.from_user.id)
    ch = next((c for c in channels if c["channel_id"] == channel_id), None)
    if not ch:
        await call.answer("Канал не найден", show_alert=True)
        return

    await state.update_data(
        channel_id=channel_id,
        channel_title=ch.get("channel_title", ""),
        channel_username=ch.get("channel_username", "")
    )
    await state.set_state(ClassicContest.enter_content)
    await call.message.edit_text(
        f"✅ Канал: <b>{ch.get('channel_title', channel_id)}</b>\n\n"
        "📝 Шаг 2/7: Введите текст поста для розыгрыша.\n\n"
        "Можно прикрепить фото к тексту в одном сообщении."
    )
    await call.answer()


# ──────────────────────── STEP 2: CONTENT ────────────────────────

@router.message(ClassicContest.enter_content)
async def classic_enter_content(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    if not text and not photo_id:
        await message.answer("❌ Пожалуйста, введите текст или прикрепите фото.")
        return

    title = (text[:50] + "...") if len(text) > 50 else text
    await state.update_data(text=text, photo_id=photo_id, title=title)
    await state.set_state(ClassicContest.select_finish_condition)
    await message.answer(
        "⏱ Шаг 3/7: Выберите условие завершения розыгрыша:",
        reply_markup=finish_condition_kb()
    )


# ──────────────────────── STEP 3: FINISH CONDITION ────────────────────────

@router.callback_query(ClassicContest.select_finish_condition, F.data == "finish_time")
async def classic_finish_time(call: CallbackQuery, state: FSMContext):
    await state.update_data(finish_condition="time")
    await state.set_state(ClassicContest.enter_finish_value)
    await call.message.edit_text(
        "⏰ Введите дату и время окончания в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>31.12.2025 23:59</code>"
    )
    await call.answer()


@router.callback_query(ClassicContest.select_finish_condition, F.data == "finish_count")
async def classic_finish_count(call: CallbackQuery, state: FSMContext):
    await state.update_data(finish_condition="count")
    await state.set_state(ClassicContest.enter_finish_value)
    await call.message.edit_text(
        "👥 Введите количество участников для завершения:\n\n"
        "Пример: <code>100</code>"
    )
    await call.answer()


@router.message(ClassicContest.enter_finish_value)
async def classic_enter_finish_value(message: Message, state: FSMContext):
    data = await state.get_data()
    value = message.text.strip()

    if data["finish_condition"] == "time":
        try:
            datetime.strptime(value, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>")
            return
    else:
        if not value.isdigit() or int(value) < 1:
            await message.answer("❌ Введите положительное число.")
            return

    await state.update_data(finish_value=value)
    await state.set_state(ClassicContest.enter_winners_count)
    await message.answer(
        "🏆 Шаг 4/7: Сколько победителей выбрать?\n\n"
        "Введите число (например: <code>1</code>, <code>3</code>, <code>5</code>)"
    )


# ──────────────────────── STEP 4: WINNERS COUNT ────────────────────────

@router.message(ClassicContest.enter_winners_count)
async def classic_enter_winners(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите положительное число.")
        return

    await state.update_data(winners_count=int(val))
    await state.set_state(ClassicContest.select_button_text)
    await message.answer(
        "🔘 Шаг 5/7: Выберите текст кнопки участия:",
        reply_markup=button_text_kb()
    )


# ──────────────────────── STEP 5: BUTTON TEXT ────────────────────────

@router.callback_query(ClassicContest.select_button_text, F.data.startswith("btn:"))
async def classic_select_button(call: CallbackQuery, state: FSMContext):
    choice = call.data.split(":", 1)[1]
    if choice == "custom":
        await state.set_state(ClassicContest.enter_custom_button_text)
        await call.message.edit_text("✏️ Введите свой текст для кнопки:")
        await call.answer()
        return

    await state.update_data(button_text=choice)
    await state.set_state(ClassicContest.enter_sponsors)
    await call.message.edit_text(
        "📡 Шаг 6/7: Введите @username каналов-спонсоров (по одному или через запятую).\n\n"
        "Или нажмите «Пропустить», если спонсоров нет.",
        reply_markup=skip_kb()
    )
    await call.answer()


@router.message(ClassicContest.enter_custom_button_text)
async def classic_custom_button(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return
    await state.update_data(button_text=text)
    await state.set_state(ClassicContest.enter_sponsors)
    await message.answer(
        "📡 Шаг 6/7: Введите @username каналов-спонсоров (по одному или через запятую).\n\n"
        "Или нажмите «Пропустить», если спонсоров нет.",
        reply_markup=skip_kb()
    )


# ──────────────────────── STEP 6: SPONSORS ────────────────────────

@router.callback_query(ClassicContest.enter_sponsors, F.data == "skip")
async def classic_skip_sponsors(call: CallbackQuery, state: FSMContext):
    await state.update_data(sponsors=[])
    await state.set_state(ClassicContest.confirm)
    await show_classic_preview(call.message, state)
    await call.answer()


@router.message(ClassicContest.enter_sponsors)
async def classic_enter_sponsors(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip()
    usernames = [u.strip().lstrip("@") for u in raw.replace(",", " ").split() if u.strip()]
    valid = []
    invalid = []
    for u in usernames:
        info = await resolve_channel(bot, f"@{u}")
        if info:
            valid.append({"username": u, "id": info["id"]})
        else:
            invalid.append(u)

    if invalid:
        await message.answer(
            f"⚠️ Не удалось найти каналы: {', '.join('@' + u for u in invalid)}\n"
            "Проверьте правильность username и попробуйте снова, или пропустите шаг.",
            reply_markup=skip_kb()
        )
        return

    await state.update_data(sponsors=valid)
    await state.set_state(ClassicContest.confirm)
    await show_classic_preview(message, state)


# ──────────────────────── STEP 7: CONFIRM & PUBLISH ────────────────────────

async def show_classic_preview(target, state: FSMContext):
    data = await state.get_data()
    cond = data.get("finish_condition")
    cond_str = f"⏰ {data.get('finish_value')}" if cond == "time" else f"👥 {data.get('finish_value')} участников"
    sponsors_str = ", ".join(f"@{s['username']}" for s in data.get("sponsors", [])) or "нет"
    preview = (
        f"📋 <b>Предпросмотр розыгрыша:</b>\n\n"
        f"📢 Канал: <b>{data.get('channel_title', data.get('channel_id'))}</b>\n"
        f"⏱ Условие: {cond_str}\n"
        f"🏆 Победителей: {data.get('winners_count', 1)}\n"
        f"🔘 Кнопка: <b>{data.get('button_text', 'Участвовать')}</b>\n"
        f"📡 Спонсоры: {sponsors_str}\n\n"
        f"<b>Текст поста:</b>\n{data.get('text', '')}"
    )
    if isinstance(target, Message):
        await target.answer(preview, reply_markup=confirm_kb())
    else:
        await target.edit_text(preview, reply_markup=confirm_kb())


@router.callback_query(ClassicContest.confirm, F.data == "cancel_creation")
async def classic_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Создание отменено.", reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(ClassicContest.confirm, F.data == "confirm_publish")
async def classic_publish(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    contest_id = await create_contest({
        "admin_id": call.from_user.id,
        "type": "classic",
        "title": data.get("title", ""),
        "text": data.get("text", ""),
        "photo_id": data.get("photo_id"),
        "channel_id": data["channel_id"],
        "channel_username": data.get("channel_username", ""),
        "finish_condition": data.get("finish_condition"),
        "finish_value": data.get("finish_value"),
        "winners_count": data.get("winners_count", 1),
        "button_text": data.get("button_text", "Участвовать"),
    })

    for sp in data.get("sponsors", []):
        await add_sponsor(contest_id, sp["username"], sp.get("id"))

    me = await bot.get_me()
    kb = participate_kb(me.username, contest_id, data.get("button_text", "Участвовать"))
    post_text = data.get("text", "")

    channel_id = data["channel_id"]
    if data.get("photo_id"):
        msg = await bot.send_photo(
            chat_id=channel_id,
            photo=data["photo_id"],
            caption=post_text,
            reply_markup=kb
        )
    else:
        msg = await bot.send_message(
            chat_id=channel_id,
            text=post_text,
            reply_markup=kb
        )

    await set_contest_message_id(contest_id, msg.message_id)

    await call.message.edit_text(
        f"🎉 Розыгрыш <b>#{contest_id}</b> опубликован в канале!\n\n"
        f"Управление через «Мои проекты».",
        reply_markup=main_menu_kb()
    )
    await call.answer("Опубликовано!")
