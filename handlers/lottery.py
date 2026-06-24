from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards import (
    main_menu_kb, channels_list_kb, payment_type_kb,
    confirm_kb, skip_kb, lottery_join_kb
)
from db.database import (
    get_admin_channels, create_contest, set_contest_message_id,
    add_sponsor, get_total_tickets
)
from utils.states import LotteryContest
from utils.helpers import resolve_channel

router = Router()


def ask_content_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="📝 Добавить текст / фото", callback_data="lot_content_yes")
    b.button(text="⏩ Без текста", callback_data="lot_content_no")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "type_lottery")
async def start_lottery(call: CallbackQuery, state: FSMContext):
    channels = await get_admin_channels(call.from_user.id)
    if not channels:
        await call.message.edit_text("📡 Нет каналов. Добавьте через «Мои каналы».", reply_markup=main_menu_kb())
        await call.answer()
        return
    await state.set_state(LotteryContest.select_channel)
    await state.update_data(type="lottery")
    await call.message.edit_text("📢 Шаг 1/7: Выберите канал:", reply_markup=channels_list_kb(channels))
    await call.answer()


@router.callback_query(LotteryContest.select_channel, F.data.startswith("ch:"))
async def lottery_channel(call: CallbackQuery, state: FSMContext):
    cid = int(call.data.split(":")[1])
    channels = await get_admin_channels(call.from_user.id)
    ch = next((c for c in channels if c["channel_id"] == cid), None)
    if not ch:
        await call.answer("Канал не найден", show_alert=True)
        return
    await state.update_data(channel_id=cid, channel_title=ch.get("channel_title",""), channel_username=ch.get("channel_username",""))
    await state.set_state(LotteryContest.ask_content)
    await call.message.edit_text(
        f"✅ Канал: <b>{ch.get('channel_title', cid)}</b>\n\n📝 Шаг 2/7: Добавить текст или фото?",
        reply_markup=ask_content_kb()
    )
    await call.answer()


@router.callback_query(LotteryContest.ask_content, F.data == "lot_content_no")
async def lottery_no_content(call: CallbackQuery, state: FSMContext):
    await state.update_data(text=None, photo_id=None, title="Лотерея")
    await state.set_state(LotteryContest.select_payment_type)
    await call.message.edit_text("💰 Шаг 3/7: Тип участия:", reply_markup=payment_type_kb())
    await call.answer()


@router.callback_query(LotteryContest.ask_content, F.data == "lot_content_yes")
async def lottery_ask_content(call: CallbackQuery, state: FSMContext):
    await state.set_state(LotteryContest.enter_content)
    await call.message.edit_text("📝 Введите текст поста (можно с фото):")
    await call.answer()


@router.message(LotteryContest.enter_content)
async def lottery_enter_content(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    if not text and not photo_id:
        await message.answer("❌ Введите текст или фото.")
        return
    title = (text[:50] + "...") if len(text) > 50 else text
    await state.update_data(text=text, photo_id=photo_id, title=title)
    await state.set_state(LotteryContest.select_payment_type)
    await message.answer("💰 Шаг 3/7: Тип участия:", reply_markup=payment_type_kb())


@router.callback_query(LotteryContest.select_payment_type, F.data == "pay_free")
async def lottery_free(call: CallbackQuery, state: FSMContext):
    await state.update_data(payment_type="free", slot_price=0)
    await state.set_state(LotteryContest.enter_max_tickets)
    await call.message.edit_text("🎟 Шаг 4/7: Максимум билетов на одного участника?\n\nПример: <code>3</code>")
    await call.answer()


@router.callback_query(LotteryContest.select_payment_type, F.data == "pay_paid")
async def lottery_paid(call: CallbackQuery, state: FSMContext):
    await state.update_data(payment_type="paid")
    await state.set_state(LotteryContest.enter_ticket_price)
    await call.message.edit_text("⭐ Шаг 4/7: Цена за 1 билет (Telegram Stars):\n\nПример: <code>10</code>")
    await call.answer()


@router.message(LotteryContest.enter_ticket_price)
async def lottery_ticket_price(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите положительное число.")
        return
    await state.update_data(slot_price=int(val), currency="XTR")
    await state.set_state(LotteryContest.enter_max_tickets)
    await message.answer("🎟 Шаг 5/7: Максимум билетов на одного участника?\n\nПример: <code>3</code>")


@router.message(LotteryContest.enter_max_tickets)
async def lottery_max_tickets(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите положительное число.")
        return
    await state.update_data(max_attempts=int(val))
    await state.set_state(LotteryContest.enter_sponsors)
    await message.answer("📡 Шаг 6/7: Введите @username спонсоров (через запятую) или пропустите:", reply_markup=skip_kb())


@router.callback_query(LotteryContest.enter_sponsors, F.data == "skip")
async def lottery_skip_sponsors(call: CallbackQuery, state: FSMContext):
    await state.update_data(sponsors=[])
    await state.set_state(LotteryContest.confirm)
    await _show_lottery_preview(call.message, state)
    await call.answer()


@router.message(LotteryContest.enter_sponsors)
async def lottery_sponsors(message: Message, state: FSMContext, bot: Bot):
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
        await message.answer(f"⚠️ Не найдены: {', '.join('@'+u for u in invalid)}\nПопробуйте снова или пропустите.", reply_markup=skip_kb())
        return
    await state.update_data(sponsors=valid)
    await state.set_state(LotteryContest.confirm)
    await _show_lottery_preview(message, state)


async def _show_lottery_preview(target, state: FSMContext):
    data = await state.get_data()
    pay = "бесплатная" if data.get("payment_type") == "free" else f"платная — {data.get('slot_price')} ⭐ за билет"
    sp = ", ".join(f"@{s['username']}" for s in data.get("sponsors", [])) or "нет"
    text = (
        f"📋 <b>Предпросмотр лотереи:</b>\n\n"
        f"📢 Канал: <b>{data.get('channel_title')}</b>\n"
        f"💰 Участие: {pay}\n"
        f"🎟 Макс. билетов: <b>{data.get('max_attempts', 1)}</b>\n"
        f"📡 Спонсоры: {sp}\n\n"
        f"Текст: {data.get('text') or '<i>без текста</i>'}"
    )
    kb = confirm_kb()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.edit_text(text, reply_markup=kb)


@router.callback_query(LotteryContest.confirm, F.data == "cancel_creation")
async def lottery_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.", reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(LotteryContest.confirm, F.data == "confirm_publish")
async def lottery_publish(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    contest_id = await create_contest({
        "admin_id": call.from_user.id,
        "type": "lottery",
        "title": data.get("title", "Лотерея"),
        "text": data.get("text"),
        "photo_id": data.get("photo_id"),
        "channel_id": data["channel_id"],
        "channel_username": data.get("channel_username", ""),
        "payment_type": data.get("payment_type", "free"),
        "slot_price": data.get("slot_price", 0),
        "currency": data.get("currency", "XTR"),
        "max_attempts": data.get("max_attempts", 1),
    })

    for sp in data.get("sponsors", []):
        await add_sponsor(contest_id, sp["username"], sp.get("id"))

    me = await bot.get_me()
    kb = lottery_join_kb(me.username, contest_id)
    post_text = data.get("text") or "🎟 Лотерея! Нажмите кнопку, чтобы получить билет."

    if data.get("photo_id"):
        msg = await bot.send_photo(chat_id=data["channel_id"], photo=data["photo_id"], caption=post_text, reply_markup=kb)
    else:
        msg = await bot.send_message(chat_id=data["channel_id"], text=post_text, reply_markup=kb)

    await set_contest_message_id(contest_id, msg.message_id)
    await call.message.edit_text(f"🎉 Лотерея <b>#{contest_id}</b> опубликована!", reply_markup=main_menu_kb())
    await call.answer("Опубликовано!")
