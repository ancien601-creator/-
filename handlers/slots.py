import random
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards import (
    main_menu_kb, channels_list_kb, payment_type_kb,
    confirm_kb, skip_kb, slots_grid_kb, ask_content_kb
)
from db.database import get_admin_channels, create_contest, set_contest_message_id, add_sponsor
from utils.states import SlotsContest
from utils.helpers import resolve_channel

router = Router()


@router.callback_query(F.data == "type_slots")
async def start_slots(call: CallbackQuery, state: FSMContext):
    channels = await get_admin_channels(call.from_user.id)
    if not channels:
        await call.message.edit_text("📡 Нет каналов. Добавьте через «Мои каналы».", reply_markup=main_menu_kb())
        await call.answer()
        return
    await state.set_state(SlotsContest.select_channel)
    await call.message.edit_text("📢 Шаг 1/8: Выберите канал:", reply_markup=channels_list_kb(channels))
    await call.answer()


@router.callback_query(SlotsContest.select_channel, F.data.startswith("ch:"))
async def slots_channel(call: CallbackQuery, state: FSMContext):
    cid = int(call.data.split(":")[1])
    channels = await get_admin_channels(call.from_user.id)
    ch = next((c for c in channels if c["channel_id"] == cid), None)
    if not ch:
        await call.answer("Не найден", show_alert=True)
        return
    await state.update_data(channel_id=cid, channel_title=ch.get("channel_title",""), channel_username=ch.get("channel_username",""))
    await state.set_state(SlotsContest.ask_content)
    await call.message.edit_text(
        f"✅ Канал: <b>{ch.get('channel_title', cid)}</b>\n\n📝 Шаг 2/8: Добавить текст или фото?",
        reply_markup=ask_content_kb("sl_")
    )
    await call.answer()


@router.callback_query(SlotsContest.ask_content, F.data == "sl_content_no")
async def slots_no_content(call: CallbackQuery, state: FSMContext):
    await state.update_data(text=None, photo_id=None, title="Лотерея по слотам")
    await state.set_state(SlotsContest.enter_slots_count)
    await call.message.edit_text("🎰 Шаг 3/8: Кол-во слотов (2–200):\n\nПример: <code>10</code>")
    await call.answer()


@router.callback_query(SlotsContest.ask_content, F.data == "sl_content_yes")
async def slots_yes_content(call: CallbackQuery, state: FSMContext):
    await state.set_state(SlotsContest.enter_content)
    await call.message.edit_text("📝 Введите текст поста (можно с фото):")
    await call.answer()


@router.message(SlotsContest.enter_content)
async def slots_enter_content(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    if not text and not photo_id:
        await message.answer("❌ Введите текст или фото.")
        return
    title = (text[:50] + "...") if len(text) > 50 else text
    await state.update_data(text=text, photo_id=photo_id, title=title)
    await state.set_state(SlotsContest.enter_slots_count)
    await message.answer("🎰 Шаг 3/8: Кол-во слотов (2–200):\n\nПример: <code>10</code>")


@router.message(SlotsContest.enter_slots_count)
async def slots_enter_count(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 2 or int(val) > 200:
        await message.answer("❌ Введите число от 2 до 200.")
        return
    total = int(val)
    winning_slot = random.randint(1, total)
    await state.update_data(total_slots=total, winning_slot=winning_slot)
    await state.set_state(SlotsContest.enter_max_attempts)
    await message.answer(f"✅ Слотов: <b>{total}</b> | 🔐 Выигрышный тайно выбран.\n\n🎯 Шаг 4/8: Макс. слотов на участника?\n\nПример: <code>1</code>")


@router.message(SlotsContest.enter_max_attempts)
async def slots_enter_max(message: Message, state: FSMContext):
    data = await state.get_data()
    val = message.text.strip()
    total = data.get("total_slots", 200)
    if not val.isdigit() or int(val) < 1 or int(val) > total:
        await message.answer(f"❌ Введите число от 1 до {total}.")
        return
    await state.update_data(max_attempts=int(val))
    await state.set_state(SlotsContest.select_payment_type)
    await message.answer(f"✅ Макс. слотов: <b>{val}</b>\n\n💰 Шаг 5/8: Тип участия:", reply_markup=payment_type_kb())


@router.callback_query(SlotsContest.select_payment_type, F.data == "pay_free")
async def slots_free(call: CallbackQuery, state: FSMContext):
    await state.update_data(payment_type="free", slot_price=0)
    await state.set_state(SlotsContest.enter_sponsors)
    await call.message.edit_text("📡 Шаг 6/8: Введите @username спонсоров или пропустите:", reply_markup=skip_kb())
    await call.answer()


@router.callback_query(SlotsContest.select_payment_type, F.data == "pay_paid")
async def slots_paid(call: CallbackQuery, state: FSMContext):
    await state.update_data(payment_type="paid")
    await state.set_state(SlotsContest.enter_slot_price)
    await call.message.edit_text("⭐ Цена за слот (Telegram Stars):\n\nПример: <code>50</code>")
    await call.answer()


@router.message(SlotsContest.enter_slot_price)
async def slots_price(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите положительное число.")
        return
    await state.update_data(slot_price=int(val), currency="XTR")
    await state.set_state(SlotsContest.enter_sponsors)
    await message.answer("📡 Шаг 6/8: Введите @username спонсоров или пропустите:", reply_markup=skip_kb())


@router.callback_query(SlotsContest.enter_sponsors, F.data == "skip")
async def slots_skip_sponsors(call: CallbackQuery, state: FSMContext):
    await state.update_data(sponsors=[])
    await state.set_state(SlotsContest.confirm)
    await _show_preview(call.message, state)
    await call.answer()


@router.message(SlotsContest.enter_sponsors)
async def slots_sponsors(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip()
    usernames = [u.strip().lstrip("@") for u in raw.replace(",", " ").split() if u.strip()]
    valid, invalid = [], []
    for u in usernames:
        info = await resolve_channel(bot, f"@{u}")
        if info:
            valid.append({"username": u, "id": info["id"]})
        else:
            invalid.append(u)
    if invalid:
        await message.answer(f"⚠️ Не найдены: {', '.join('@'+u for u in invalid)}", reply_markup=skip_kb())
        return
    await state.update_data(sponsors=valid)
    await state.set_state(SlotsContest.confirm)
    await _show_preview(message, state)


async def _show_preview(target, state: FSMContext):
    data = await state.get_data()
    pay = "бесплатно" if data.get("payment_type") == "free" else f"{data.get('slot_price')} ⭐/слот"
    sp = ", ".join(f"@{s['username']}" for s in data.get("sponsors", [])) or "нет"
    text = (
        f"📋 <b>Предпросмотр лотереи по слотам:</b>\n\n"
        f"📢 Канал: <b>{data.get('channel_title')}</b>\n"
        f"🎰 Слотов: <b>{data.get('total_slots')}</b>\n"
        f"🎯 Макс. на участника: <b>{data.get('max_attempts', 1)}</b>\n"
        f"💰 Участие: {pay}\n"
        f"📡 Спонсоры: {sp}"
    )
    kb = confirm_kb()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.edit_text(text, reply_markup=kb)


@router.callback_query(SlotsContest.confirm, F.data == "cancel_creation")
async def slots_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.", reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(SlotsContest.confirm, F.data == "confirm_publish")
async def slots_publish(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    contest_id = await create_contest({
        "admin_id": call.from_user.id,
        "type": "slots",
        "title": data.get("title", "Лотерея"),
        "text": data.get("text"),
        "photo_id": data.get("photo_id"),
        "channel_id": data["channel_id"],
        "channel_username": data.get("channel_username", ""),
        "total_slots": data["total_slots"],
        "max_attempts": data.get("max_attempts", 1),
        "payment_type": data.get("payment_type", "free"),
        "slot_price": data.get("slot_price", 0),
        "currency": data.get("currency", "XTR"),
        "winning_slot": data["winning_slot"],
    })

    for sp in data.get("sponsors", []):
        await add_sponsor(contest_id, sp["username"], sp.get("id"))

    me = await bot.get_me()
    kb = slots_grid_kb(me.username, contest_id, data["total_slots"], set())
    post_text = data.get("text") or ""
    channel_id = data["channel_id"]

    if data.get("photo_id"):
        msg = await bot.send_photo(chat_id=channel_id, photo=data["photo_id"], caption=post_text or None, reply_markup=kb)
    elif post_text:
        msg = await bot.send_message(chat_id=channel_id, text=post_text, reply_markup=kb)
    else:
        msg = await bot.send_message(chat_id=channel_id, text="🎰 Лотерея по слотам", reply_markup=kb)

    await set_contest_message_id(contest_id, msg.message_id)
    await call.message.edit_text(f"🎉 Лотерея <b>#{contest_id}</b> опубликована!", reply_markup=main_menu_kb())
    await call.answer("Опубликовано!")
