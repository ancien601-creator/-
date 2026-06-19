import json
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.deep_linking import create_start_link
from db import (
    is_admin, get_admin_channels, create_contest, get_contest,
    get_active_contests_for_admin, update_contest,
    add_admin_channel, remove_admin_channel,
    get_random_participants, get_occupied_slots
)
from keyboards import (
    main_menu, project_type_choice, end_condition_choice,
    button_text_choice, payment_choice, skip_button,
    confirm_keyboard, my_projects_keyboard, project_actions,
    slot_buttons
)
from states import ClassicCreation, SlotsCreation
from utils import update_post_message, generate_contest_post
from datetime import datetime
import random

router = Router()

# --- Вспомогательная функция проверки админа ---
async def require_admin(user_id: int) -> bool:
    return await is_admin(user_id)

# --- Добавление канала ---
@router.callback_query(F.data == "add_channel_menu")
async def add_channel_prompt(callback: CallbackQuery):
    await callback.message.edit_text(
        "Чтобы добавить канал, отправьте мне его @username (например, @mychannel) "
        "или перешлите любое сообщение из канала.\n"
        "Я проверю, что вы администратор, а бот имеет права.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    )
    await callback.answer()

@router.message(F.text & F.text.startswith("@"))
async def add_channel_by_username(message: Message, bot: Bot):
    username = message.text.strip().lstrip("@")
    try:
        chat = await bot.get_chat(f"@{username}")
        # Проверка пользователя
        member = await bot.get_chat_member(chat.id, message.from_user.id)
        if member.status not in ['creator', 'administrator']:
            await message.answer("❌ Вы не администратор этого канала.")
            return
        # Проверка бота
        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status != 'administrator':
            await message.answer("❌ Бот не администратор канала. Добавьте бота и дайте права.")
            return
        await add_admin_channel(message.from_user.id, chat.id, f"@{username}")
        await message.answer(f"✅ Канал @{username} успешно добавлен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(F.forward_from_chat)
async def add_channel_by_forward(message: Message, bot: Bot):
    chat = message.forward_from_chat
    if not chat:
        await message.answer("Не удалось определить канал.")
        return
    try:
        member = await bot.get_chat_member(chat.id, message.from_user.id)
        if member.status not in ['creator', 'administrator']:
            await message.answer("❌ Вы не администратор этого канала.")
            return
        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status != 'administrator':
            await message.answer("❌ Бот не админ в этом канале.")
            return
        username = f"@{chat.username}" if chat.username else f"ID{chat.id}"
        await add_admin_channel(message.from_user.id, chat.id, username)
        await message.answer(f"✅ Канал {username} добавлен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# --- Создание проекта ---
@router.callback_query(F.data == "create_project")
async def create_project(callback: CallbackQuery, state: FSMContext):
    if not await require_admin(callback.from_user.id):
        await callback.answer("❌ Добавьте канал, чтобы создавать проекты.", show_alert=True)
        return
    await callback.message.edit_text("Выберите тип проекта:", reply_markup=project_type_choice())
    await callback.answer()

# === КЛАССИЧЕСКИЙ РОЗЫГРЫШ ===
@router.callback_query(F.data == "type_classic")
async def classic_start(callback: CallbackQuery, state: FSMContext):
    if not await require_admin(callback.from_user.id): return
    await state.set_state(ClassicCreation.channel)
    channels = await get_admin_channels(callback.from_user.id)
    if not channels:
        await callback.message.edit_text("Нет добавленных каналов.", reply_markup=main_menu(True))
        return
    builder = InlineKeyboardBuilder()
    for ch_id, ch_username in channels:
        builder.button(text=ch_username or f"ID {ch_id}", callback_data=f"ch_{ch_id}")
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    await callback.message.edit_text("Выберите канал:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(StateFilter(ClassicCreation.channel), F.data.startswith("ch_"))
async def classic_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split("_")[1])
    await state.update_data(channel_id=channel_id)
    await state.set_state(ClassicCreation.content_text)
    await callback.message.edit_text("Введите текст поста (или пропустите):", reply_markup=skip_button())
    await callback.answer()

@router.callback_query(StateFilter(ClassicCreation.content_text), F.data == "skip")
async def classic_skip_text(callback: CallbackQuery, state: FSMContext):
    await state.update_data(text="")
    await state.set_state(ClassicCreation.content_photo)
    await callback.message.edit_text("Отправьте фото (или пропустите):", reply_markup=skip_button())

@router.message(StateFilter(ClassicCreation.content_text))
async def classic_content_text(message: Message, state: FSMContext):
    if message.text and message.text.strip() != "/skip":
        await state.update_data(text=message.text)
    await state.set_state(ClassicCreation.content_photo)
    await message.answer("Отправьте фото (или пропустите):", reply_markup=skip_button())

@router.callback_query(StateFilter(ClassicCreation.content_photo), F.data == "skip")
async def classic_skip_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ClassicCreation.end_condition)
    await callback.message.edit_text("Выберите условие завершения:", reply_markup=end_condition_choice())

@router.message(StateFilter(ClassicCreation.content_photo), F.photo)
async def classic_content_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(ClassicCreation.end_condition)
    await message.answer("Выберите условие завершения:", reply_markup=end_condition_choice())

@router.callback_query(StateFilter(ClassicCreation.end_condition), F.data.startswith("cond_"))
async def classic_end_condition(callback: CallbackQuery, state: FSMContext):
    cond = callback.data.split("_")[1]
    await state.update_data(end_condition=cond)
    text = "Введите дату и время (ГГГГ-ММ-ДД ЧЧ:ММ МСК):" if cond == "time" else "Введите количество участников:"
    await callback.message.edit_text(text)
    await state.set_state(ClassicCreation.end_value)

@router.message(StateFilter(ClassicCreation.end_value))
async def classic_end_value(message: Message, state: FSMContext):
    await state.update_data(end_value=message.text.strip())
    await state.set_state(ClassicCreation.winners_count)
    await message.answer("Сколько победителей?")

@router.message(StateFilter(ClassicCreation.winners_count))
async def classic_winners(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 1:
        await message.answer("Введите целое число > 0.")
        return
    await state.update_data(winners_count=int(message.text))
    await state.set_state(ClassicCreation.button_text)
    await message.answer("Текст на кнопке:", reply_markup=button_text_choice())

@router.callback_query(StateFilter(ClassicCreation.button_text))
async def classic_button_text(callback: CallbackQuery, state: FSMContext):
    if callback.data == "btn_custom":
        await callback.message.edit_text("Введите свой текст:")
        return
    mapping = {"btn_participate": "Участвовать", "btn_join": "Подключаюсь", "btn_luck": "Испытать удачу"}
    await state.update_data(button_text=mapping.get(callback.data, "Участвовать"))
    await state.set_state(ClassicCreation.sponsors)
    await callback.message.edit_text("Введите @username спонсоров через пробел (или 0):")

@router.message(StateFilter(ClassicCreation.button_text))
async def classic_custom_button(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text.strip())
    await state.set_state(ClassicCreation.sponsors)
    await message.answer("Введите @username спонсоров через пробел (или 0):")

@router.message(StateFilter(ClassicCreation.sponsors))
async def classic_sponsors(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip()
    sponsors = [] if raw == "0" else [ch.strip().lstrip('@') for ch in raw.split() if ch.startswith('@')]
    valid = []
    for sp in sponsors:
        try:
            await bot.get_chat(f"@{sp}")
            valid.append(sp)
        except:
            await message.answer(f"Канал @{sp} недоступен.")
    await state.update_data(sponsors=valid)
    data = await state.get_data()
    await state.set_state(ClassicCreation.confirm)
    preview = (
        f"📢 Предпросмотр\nКанал: {data['channel_id']}\nТекст: {data.get('text', '—')}\n"
        f"Фото: {'есть' if data.get('photo') else 'нет'}\n"
        f"Условие: {'время' if data['end_condition']=='time' else 'участники'} — {data['end_value']}\n"
        f"Победителей: {data['winners_count']}\nКнопка: «{data['button_text']}»\n"
        f"Спонсоры: {', '.join('@'+s for s in valid) if valid else 'нет'}"
    )
    await message.answer(preview, reply_markup=confirm_keyboard())

@router.callback_query(StateFilter(ClassicCreation.confirm), F.data == "publish")
async def classic_publish(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    contest_id = await create_contest({
        "type": "classic",
        "text": data.get("text", ""),
        "photo_file_id": data.get("photo", ""),
        "channel_id": data["channel_id"],
        "created_by": callback.from_user.id,
        "end_condition": data["end_condition"],
        "end_value": data["end_value"],
        "winners_count": data["winners_count"],
        "sponsor_channels": json.dumps(data["sponsors"]),
        "title": (data.get("text") or "Розыгрыш")[:30]
    })
    deep_link = await create_start_link(bot, f"contest_{contest_id}", encode=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=data["button_text"], url=deep_link)]
    ])
    post_text = generate_contest_post({
        "type": "classic",
        "text": data.get("text", ""),
        "end_condition": data["end_condition"],
        "end_value": data["end_value"],
        "winners_count": data["winners_count"]
    })
    try:
        if data.get("photo"):
            msg = await bot.send_photo(data["channel_id"], photo=data["photo"], caption=post_text, reply_markup=kb)
        else:
            msg = await bot.send_message(data["channel_id"], text=post_text, reply_markup=kb)
        await update_contest(contest_id, message_id=msg.message_id)
        await state.clear()
        await callback.message.edit_text("✅ Опубликовано!")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
    await callback.answer()

# === ЛОТЕРЕЯ ПО СЛОТАМ ===
@router.callback_query(F.data == "type_slots")
async def slots_start(callback: CallbackQuery, state: FSMContext):
    if not await require_admin(callback.from_user.id): return
    await state.set_state(SlotsCreation.channel)
    channels = await get_admin_channels(callback.from_user.id)
    if not channels:
        await callback.message.edit_text("Нет каналов.", reply_markup=main_menu(True))
        return
    builder = InlineKeyboardBuilder()
    for ch_id, ch_username in channels:
        builder.button(text=ch_username or f"ID {ch_id}", callback_data=f"sch_{ch_id}")
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    await callback.message.edit_text("Выберите канал:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(StateFilter(SlotsCreation.channel), F.data.startswith("sch_"))
async def slots_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split("_")[1])
    await state.update_data(channel_id=channel_id)
    await state.set_state(SlotsCreation.content_text)
    await callback.message.edit_text("Введите текст (или пропустите):", reply_markup=skip_button())
    await callback.answer()

@router.callback_query(StateFilter(SlotsCreation.content_text), F.data == "skip")
async def slots_skip_text(callback: CallbackQuery, state: FSMContext):
    await state.update_data(text="")
    await state.set_state(SlotsCreation.content_photo)
    await callback.message.edit_text("Отправьте фото (или пропустите):", reply_markup=skip_button())

@router.message(StateFilter(SlotsCreation.content_text))
async def slots_content_text(message: Message, state: FSMContext):
    if message.text and message.text.strip() != "/skip":
        await state.update_data(text=message.text)
    await state.set_state(SlotsCreation.content_photo)
    await message.answer("Отправьте фото (или пропустите):", reply_markup=skip_button())

@router.callback_query(StateFilter(SlotsCreation.content_photo), F.data == "skip")
async def slots_skip_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SlotsCreation.slots_count)
    await callback.message.edit_text("Сколько слотов?")

@router.message(StateFilter(SlotsCreation.content_photo), F.photo)
async def slots_content_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(SlotsCreation.slots_count)
    await message.answer("Сколько слотов?")

@router.message(StateFilter(SlotsCreation.slots_count))
async def slots_count(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 2:
        await message.answer("Введите целое число > 1.")
        return
    cnt = int(message.text)
    winning = random.randint(1, cnt)
    await state.update_data(slots_count=cnt, winning_slot=winning)
    await state.set_state(SlotsCreation.payment)
    await message.answer("Тип участия:", reply_markup=payment_choice())

@router.callback_query(StateFilter(SlotsCreation.payment))
async def slots_payment(callback: CallbackQuery, state: FSMContext):
    if callback.data == "pay_free":
        await state.update_data(payment_required=0, slot_price=0)
        await state.set_state(SlotsCreation.sponsors)
        await callback.message.edit_text("Введите @username спонсоров через пробел (или 0):")
    else:
        await state.update_data(payment_required=1)
        await state.set_state(SlotsCreation.slot_price)
        await callback.message.edit_text("Цена слота в рублях:")

@router.message(StateFilter(SlotsCreation.slot_price))
async def slots_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число.")
        return
    price = int(message.text)
    await state.update_data(slot_price=price * 100)  # копейки
    await state.set_state(SlotsCreation.sponsors)
    await message.answer("Введите @username спонсоров через пробел (или 0):")

@router.message(StateFilter(SlotsCreation.sponsors))
async def slots_sponsors(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip()
    sponsors = [] if raw == "0" else [ch.strip().lstrip('@') for ch in raw.split() if ch.startswith('@')]
    valid = []
    for sp in sponsors:
        try:
            await bot.get_chat(f"@{sp}")
            valid.append(sp)
        except:
            await message.answer(f"Канал @{sp} недоступен.")
    await state.update_data(sponsors=valid)
    data = await state.get_data()
    await state.set_state(SlotsCreation.confirm)
    preview = (
        f"🎰 Лотерея\nКанал: {data['channel_id']}\n"
        f"Слотов: {data['slots_count']}\nПобедный слот выбран тайно\n"
        f"Оплата: {'платно' if data['payment_required'] else 'бесплатно'}\n"
        f"Спонсоры: {', '.join('@'+s for s in valid) if valid else 'нет'}"
    )
    await message.answer(preview, reply_markup=confirm_keyboard())

@router.callback_query(StateFilter(SlotsCreation.confirm), F.data == "publish")
async def slots_publish(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    contest_id = await create_contest({
        "type": "slots",
        "text": data.get("text", ""),
        "photo_file_id": data.get("photo", ""),
        "channel_id": data["channel_id"],
        "created_by": callback.from_user.id,
        "slots_count": data["slots_count"],
        "winning_slot": data["winning_slot"],
        "payment_required": data["payment_required"],
        "slot_price": data["slot_price"],
        "sponsor_channels": json.dumps(data["sponsors"]),
        "title": (data.get("text") or "Лотерея")[:30]
    })
    kb = slot_buttons(contest_id, data["slots_count"], {})
    post_text = generate_contest_post({
        "type": "slots",
        "text": data.get("text", ""),
        "slots_count": data["slots_count"],
        "payment_required": data["payment_required"],
        "slot_price": data["slot_price"]
    })
    try:
        if data.get("photo"):
            msg = await bot.send_photo(data["channel_id"], photo=data["photo"], caption=post_text, reply_markup=kb)
        else:
            msg = await bot.send_message(data["channel_id"], text=post_text, reply_markup=kb)
        await update_contest(contest_id, message_id=msg.message_id)
        await state.clear()
        await callback.message.edit_text("✅ Лотерея запущена!")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
    await callback.answer()

# --- Мои проекты ---
@router.callback_query(F.data == "my_projects")
async def my_projects(callback: CallbackQuery):
    if not await require_admin(callback.from_user.id):
        await callback.answer("Добавьте канал.", show_alert=True)
        return
    contests = await get_active_contests_for_admin(callback.from_user.id)
    if not contests:
        await callback.message.edit_text("Нет активных проектов.", reply_markup=main_menu(True))
    else:
        await callback.message.edit_text("Ваши проекты:", reply_markup=my_projects_keyboard(contests))
    await callback.answer()

@router.callback_query(F.data.startswith("project_"))
async def project_detail(callback: CallbackQuery):
    contest_id = int(callback.data.split("_")[1])
    contest = await get_contest(contest_id)
    if not contest or contest['created_by'] != callback.from_user.id:
        await callback.answer("Нет доступа.")
        return
    await callback.message.edit_text(
        f"Проект #{contest_id}\nТип: {contest['type']}\nСтатус: {contest['status']}",
        reply_markup=project_actions(contest_id, contest['type'])
    )

@router.callback_query(F.data.startswith("finish_"))
async def finish_contest(callback: CallbackQuery, bot: Bot):
    contest_id = int(callback.data.split("_")[1])
    contest = await get_contest(contest_id)
    if not contest or contest['created_by'] != callback.from_user.id:
        await callback.answer("Нет прав.")
        return
    if contest['type'] == 'classic':
        winners = await get_random_participants(contest_id, contest['winners_count'])
        mentions = []
        for uid in winners:
            try:
                user = await bot.get_chat(uid)
                mentions.append(f"@{user.username}" if user.username else f"tg://user?id={uid}")
            except:
                pass
        new_text = generate_contest_post(contest) + f"\n\n🏆 Победители: {', '.join(mentions)}"
        await update_post_message(bot, contest, new_text=new_text)
        await update_contest(contest_id, status='finished', finished_at=datetime.now())
        await callback.message.edit_text("✅ Итоги подведены!")
    else:  # slots
        await update_contest(contest_id, status='finished', finished_at=datetime.now())
        await update_post_message(bot, contest, reply_markup=None)
        await callback.message.edit_text("✅ Лотерея завершена.")
    await callback.answer()

@router.callback_query(F.data.startswith("delete_"))
async def delete_contest(callback: CallbackQuery, bot: Bot):
    contest_id = int(callback.data.split("_")[1])
    contest = await get_contest(contest_id)
    if not contest or contest['created_by'] != callback.from_user.id:
        await callback.answer("Нет прав.")
        return
    # Удаляем пост из канала, если возможно
    try:
        await bot.delete_message(contest['channel_id'], contest['message_id'])
    except:
        pass
    await update_contest(contest_id, status='deleted')
    await callback.message.edit_text("🗑 Проект удалён.", reply_markup=main_menu(True))
    await callback.answer()
