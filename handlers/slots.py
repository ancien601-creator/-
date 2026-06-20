import random

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards import (
    main_menu_kb, channels_list_kb, payment_type_kb,
    confirm_kb, skip_kb, slots_grid_kb
)
from db.database import get_admin_channels, create_contest, set_contest_message_id, add_sponsor
from utils.states import SlotsContest
from utils.helpers import resolve_channel

router = Router()


@router.callback_query(F.data == "type_slots")
async def start_slots(call: CallbackQuery, state: FSMContext):
    channels = await get_admin_channels(call.from_user.id)
    if not channels:
        await call.message.edit_text(
            "📡 У вас нет добавленных каналов.\n\n"
            "Сначала добавьте канал через «Мои каналы».",
            reply_markup=main_menu_kb()
        )
        await call.answer()
        return

    await state.set_state(SlotsContest.select_channel)
    await state.update_data(type="slots")
    await call.message.edit_text(
        "📢 Шаг 1/7: Выберите канал для лотереи:",
        reply_markup=channels_list_kb(channels)
    )
    await call.answer()


# ──────────────────────── STEP 1: CHANNEL ────────────────────────

@router.callback_query(SlotsContest.select_channel, F.data.startswith("ch:"))
async def slots_select_channel(call: CallbackQuery, state: FSMContext):
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
    await state.set_state(SlotsContest.enter_content)
    await call.message.edit_text(
        f"✅ Канал: <b>{ch.get('channel_title', channel_id)}</b>\n\n"
        "📝 Шаг 2/7: Введите текст поста лотереи.\n\n"
        "Можно прикрепить фото к тексту в одном сообщении."
    )
    await call.answer()


# ──────────────────────── STEP 2: CONTENT ────────────────────────

@router.message(SlotsContest.enter_content)
async def slots_enter_content(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    if not text and not photo_id:
        await message.answer("❌ Пожалуйста, введите текст или прикрепите фото.")
        return

    title = (text[:50] + "...") if len(text) > 50 else text
    await state.update_data(text=text, photo_id=photo_id, title=title)
    await state.set_state(SlotsContest.enter_slots_count)
    await message.answer(
        "🎰 Шаг 3/7: Введите количество слотов в лотерее:\n\n"
        "Например: <code>10</code>, <code>20</code>, <code>50</code>"
    )


# ──────────────────────── STEP 3: SLOTS COUNT ────────────────────────

@router.message(SlotsContest.enter_slots_count)
async def slots_enter_count(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 2 or int(val) > 200:
        await message.answer("❌ Введите число от 2 до 200.")
        return

    total = int(val)
    winning_slot = random.randint(1, total)
    await state.update_data(total_slots=total, winning_slot=winning_slot)

    await state.set_state(SlotsContest.select_payment_type)
    await message.answer(
        f"✅ Слотов: <b>{total}</b>\n"
        f"🔐 Выигрышный слот тайно выбран и сохранён.\n\n"
        "💰 Шаг 4/7: Выберите тип участия:",
        reply_markup=payment_type_kb()
    )


# ──────────────────────── STEP 4: PAYMENT TYPE ────────────────────────

@router.callback_query(SlotsContest.select_payment_type, F.data == "pay_free")
async def slots_pay_free(call: CallbackQuery, state: FSMContext):
    await state.update_data(payment_type="free", slot_price=0)
    await state.set_state(SlotsContest.enter_sponsors)
    await call.message.edit_text(
        "📡 Шаг 5/7: Введите @username каналов-спонсоров (по одному или через запятую).\n\n"
        "Или нажмите «Пропустить», если спонсоров нет.",
        reply_markup=skip_kb()
    )
    await call.answer()


@router.callback_query(SlotsContest.select_payment_type, F.data == "pay_paid")
async def slots_pay_paid(call: CallbackQuery, state: FSMContext):
    await state.update_data(payment_type="paid")
    await state.set_state(SlotsContest.enter_slot_price)
    await call.message.edit_text(
        "⭐ Введите цену за слот в Telegram Stars:\n\n"
        "Пример: <code>50</code> (50 звёзд)"
    )
    await call.answer()


@router.message(SlotsContest.enter_slot_price)
async def slots_enter_price(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите положительное целое число (количество звёзд).")
        return
    await state.update_data(slot_price=int(val), currency="XTR")
    await state.set_state(SlotsContest.enter_sponsors)
    await message.answer(
        "📡 Шаг 6/7: Введите @username каналов-спонсоров (по одному или через запятую).\n\n"
        "Или нажмите «Пропустить», если спонсоров нет.",
        reply_markup=skip_kb()
    )


# ──────────────────────── STEP 5: SPONSORS ────────────────────────

@router.callback_query(SlotsContest.enter_sponsors, F.data == "skip")
async def slots_skip_sponsors(call: CallbackQuery, state: FSMContext):
    await state.update_data(sponsors=[])
    await state.set_state(SlotsContest.confirm)
    await show_slots_preview(call.message, state)
    await call.answer()


@router.message(SlotsContest.enter_sponsors)
async def slots_enter_sponsors(message: Message, state: FSMContext, bot: Bot):
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
            f"⚠️ Не удалось найти: {', '.join('@' + u for u in invalid)}\n"
            "Проверьте username или пропустите шаг.",
            reply_markup=skip_kb()
        )
        return

    await state.update_data(sponsors=valid)
    await state.set_state(SlotsContest.confirm)
    await show_slots_preview(message, state)


# ──────────────────────── STEP 6: CONFIRM & PUBLISH ────────────────────────

async def show_slots_preview(target, state: FSMContext):
    data = await state.get_data()
    pay_str = ("бесплатный" if data.get("payment_type") == "free"
               else f"платный — {data.get('slot_price')} ⭐ за слот")
    sponsors_str = ", ".join(f"@{s['username']}" for s in data.get("sponsors", [])) or "нет"
    preview = (
        f"📋 <b>Предпросмотр лотереи по слотам:</b>\n\n"
        f"📢 Канал: <b>{data.get('channel_title', data.get('channel_id'))}</b>\n"
        f"🎰 Слотов: <b>{data.get('total_slots')}</b>\n"
        f"💰 Участие: {pay_str}\n"
        f"📡 Спонсоры: {sponsors_str}\n\n"
        f"<b>Текст поста:</b>\n{data.get('text', '')}"
    )
    if isinstance(target, Message):
        await target.answer(preview, reply_markup=confirm_kb())
    else:
        await target.edit_text(preview, reply_markup=confirm_kb())


@router.callback_query(SlotsContest.confirm, F.data == "cancel_creation")
async def slots_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Создание отменено.", reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(SlotsContest.confirm, F.data == "confirm_publish")
async def slots_publish(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    contest_id = await create_contest({
        "admin_id": call.from_user.id,
        "type": "slots",
        "title": data.get("title", ""),
        "text": data.get("text", ""),
        "photo_id": data.get("photo_id"),
        "channel_id": data["channel_id"],
        "channel_username": data.get("channel_username", ""),
        "total_slots": data["total_slots"],
        "payment_type": data.get("payment_type", "free"),
        "slot_price": data.get("slot_price", 0),
        "currency": data.get("currency", "XTR"),
        "winning_slot": data["winning_slot"],
    })

    for sp in data.get("sponsors", []):
        await add_sponsor(contest_id, sp["username"], sp.get("id"))

    me = await bot.get_me()
    kb = slots_grid_kb(me.username, contest_id, data["total_slots"], set())
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
        f"🎉 Лотерея <b>#{contest_id}</b> опубликована!\n\n"
        f"Управление через «Мои проекты».",
        reply_markup=main_menu_kb()
    )
    await call.answer("Опубликовано!")
