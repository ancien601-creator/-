from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards import (
    main_menu_kb, contest_type_kb, channels_list_kb,
    finish_condition_kb, button_text_kb, confirm_kb, skip_kb,
    participate_kb, show_count_kb, ask_content_kb
)
from db.database import get_admin_channels, create_contest, set_contest_message_id, add_sponsor
from utils.states import ClassicContest
from utils.helpers import resolve_channel

router = Router()


def _time_examples() -> str:
    now = datetime.now()
    fmt = "%d.%m.%Y %H:%M"
    return (
        f"Примеры:\n"
        f"<code>{(now + timedelta(minutes=10)).strftime(fmt)}</code> — через 10 минут\n"
        f"<code>{(now + timedelta(hours=1)).strftime(fmt)}</code> — через час\n"
        f"<code>{(now + timedelta(days=1)).strftime(fmt)}</code> — через день\n"
        f"<code>{(now + timedelta(weeks=1)).strftime(fmt)}</code> — через неделю"
    )


@router.callback_query(F.data == "create_project")
async def create_project(call: CallbackQuery):
    await call.message.edit_text("🎪 Выберите тип проекта:", reply_markup=contest_type_kb())
    await call.answer()


@router.callback_query(F.data == "type_classic")
async def start_classic(call: CallbackQuery, state: FSMContext):
    channels = await get_admin_channels(call.from_user.id)
    if not channels:
        await call.message.edit_text("📡 Нет каналов. Добавьте через «Мои каналы».", reply_markup=main_menu_kb())
        await call.answer()
        return
    await state.set_state(ClassicContest.select_channel)
    await call.message.edit_text("📢 Шаг 1/8: Выберите канал:", reply_markup=channels_list_kb(channels))
    await call.answer()


@router.callback_query(ClassicContest.select_channel, F.data.startswith("ch:"))
async def classic_channel(call: CallbackQuery, state: FSMContext):
    cid = int(call.data.split(":")[1])
    channels = await get_admin_channels(call.from_user.id)
    ch = next((c for c in channels if c["channel_id"] == cid), None)
    if not ch:
        await call.answer("Не найден", show_alert=True)
        return
    await state.update_data(channel_id=cid, channel_title=ch.get("channel_title",""), channel_username=ch.get("channel_username",""))
    await state.set_state(ClassicContest.enter_content)
    await call.message.edit_text(
        f"✅ Канал: <b>{ch.get('channel_title', cid)}</b>\n\n📝 Шаг 2/8: Добавить текст или фото?",
        reply_markup=ask_content_kb("cl_")
    )
    await call.answer()


@router.callback_query(ClassicContest.enter_content, F.data == "cl_content_no")
async def classic_no_content(call: CallbackQuery, state: FSMContext):
    await state.update_data(text=None, photo_id=None, title="Розыгрыш")
    await state.set_state(ClassicContest.select_finish_condition)
    await call.message.edit_text("⏱ Шаг 3/8: Условие завершения:", reply_markup=finish_condition_kb())
    await call.answer()


@router.callback_query(ClassicContest.enter_content, F.data == "cl_content_yes")
async def classic_yes_content(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 Введите текст поста (можно с фото):")
    await call.answer()


@router.message(ClassicContest.enter_content)
async def classic_enter_content(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    if not text and not photo_id:
        await message.answer("❌ Введите текст или фото.")
        return
    title = (text[:50] + "...") if len(text) > 50 else text
    await state.update_data(text=text, photo_id=photo_id, title=title)
    await state.set_state(ClassicContest.select_finish_condition)
    await message.answer("⏱ Шаг 3/8: Условие завершения:", reply_markup=finish_condition_kb())


@router.callback_query(ClassicContest.select_finish_condition, F.data == "finish_time")
async def classic_finish_time(call: CallbackQuery, state: FSMContext):
    await state.update_data(finish_condition="time")
    await state.set_state(ClassicContest.enter_finish_value)
    await call.message.edit_text(
        f"⏰ Введите дату и время окончания:\n<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n{_time_examples()}"
    )
    await call.answer()


@router.callback_query(ClassicContest.select_finish_condition, F.data == "finish_count")
async def classic_finish_count(call: CallbackQuery, state: FSMContext):
    await state.update_data(finish_condition="count")
    await state.set_state(ClassicContest.enter_finish_value)
    await call.message.edit_text("👥 Введите кол-во участников для завершения:\n\nПример: <code>100</code>")
    await call.answer()


@router.message(ClassicContest.enter_finish_value)
async def classic_enter_finish_value(message: Message, state: FSMContext):
    data = await state.get_data()
    value = message.text.strip()
    if data["finish_condition"] == "time":
        try:
            finish_dt = datetime.strptime(value, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer(f"❌ Неверный формат.\n\n{_time_examples()}")
            return
        if finish_dt <= datetime.now():
            await message.answer(f"❌ Дата должна быть в будущем.\n\n{_time_examples()}")
            return
    else:
        if not value.isdigit() or int(value) < 1:
            await message.answer("❌ Введите положительное число.")
            return
    await state.update_data(finish_value=value)
    await state.set_state(ClassicContest.enter_winners_count)
    await message.answer("🏆 Шаг 4/8: Сколько победителей?\n\nПример: <code>1</code>")


@router.message(ClassicContest.enter_winners_count)
async def classic_enter_winners(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите положительное число.")
        return
    await state.update_data(winners_count=int(val))
    await state.set_state(ClassicContest.select_button_text)
    await message.answer("🔘 Шаг 5/8: Текст кнопки участия:", reply_markup=button_text_kb())


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
    await call.message.edit_text("👁 Шаг 6/8: Показывать счётчик участников на кнопке?", reply_markup=show_count_kb())
    await call.answer()


@router.message(ClassicContest.enter_custom_button_text)
async def classic_custom_button(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return
    await state.update_data(button_text=text)
    await state.set_state(ClassicContest.enter_sponsors)
    await message.answer("👁 Шаг 6/8: Показывать счётчик участников на кнопке?", reply_markup=show_count_kb())


@router.callback_query(F.data.startswith("show_count:"))
async def classic_show_count(call: CallbackQuery, state: FSMContext):
    show = call.data.split(":")[1] == "yes"
    await state.update_data(show_count=show)
    await state.set_state(ClassicContest.enter_sponsors)
    await call.message.edit_text(
        "📡 Шаг 7/8: Введите @username спонсоров (через запятую) или пропустите:",
        reply_markup=skip_kb()
    )
    await call.answer()


@router.callback_query(ClassicContest.enter_sponsors, F.data == "skip")
async def classic_skip_sponsors(call: CallbackQuery, state: FSMContext):
    await state.update_data(sponsors=[])
    await state.set_state(ClassicContest.confirm)
    await _show_preview(call.message, state)
    await call.answer()


@router.message(ClassicContest.enter_sponsors)
async def classic_enter_sponsors(message: Message, state: FSMContext, bot: Bot):
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
    await state.set_state(ClassicContest.confirm)
    await _show_preview(message, state)


async def _show_preview(target, state: FSMContext):
    data = await state.get_data()
    cond = data.get("finish_condition")
    cond_str = f"⏰ {data.get('finish_value')}" if cond == "time" else f"👥 {data.get('finish_value')} участников"
    sp = ", ".join(f"@{s['username']}" for s in data.get("sponsors", [])) or "нет"
    text = (
        f"📋 <b>Предпросмотр:</b>\n\n"
        f"📢 Канал: <b>{data.get('channel_title')}</b>\n"
        f"⏱ Условие: {cond_str}\n"
        f"🏆 Победителей: {data.get('winners_count', 1)}\n"
        f"🔘 Кнопка: <b>{data.get('button_text', 'Участвовать')}</b>\n"
        f"👁 Счётчик: {'да' if data.get('show_count') else 'нет'}\n"
        f"📡 Спонсоры: {sp}\n\n"
        f"Текст: {data.get('text') or '<i>без текста</i>'}"
    )
    kb = confirm_kb()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.edit_text(text, reply_markup=kb)


@router.callback_query(ClassicContest.confirm, F.data == "cancel_creation")
async def classic_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.", reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(ClassicContest.confirm, F.data == "confirm_publish")
async def classic_publish(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    contest_id = await create_contest({
        "admin_id": call.from_user.id,
        "type": "classic",
        "title": data.get("title", "Розыгрыш"),
        "text": data.get("text"),
        "photo_id": data.get("photo_id"),
        "channel_id": data["channel_id"],
        "channel_username": data.get("channel_username", ""),
        "finish_condition": data.get("finish_condition"),
        "finish_value": data.get("finish_value"),
        "winners_count": data.get("winners_count", 1),
        "button_text": data.get("button_text", "Участвовать"),
        "show_count": 1 if data.get("show_count") else 0,
    })

    for sp in data.get("sponsors", []):
        await add_sponsor(contest_id, sp["username"], sp.get("id"))

    me = await bot.get_me()
    btn_text = data.get("button_text", "Участвовать")
    if data.get("show_count"):
        btn_text = f"{btn_text} (0)"
    kb = participate_kb(me.username, contest_id, btn_text)

    channel_id = data["channel_id"]
    post_text = data.get("text") or ""

    if data.get("photo_id"):
        msg = await bot.send_photo(chat_id=channel_id, photo=data["photo_id"], caption=post_text or None, reply_markup=kb)
    elif post_text:
        msg = await bot.send_message(chat_id=channel_id, text=post_text, reply_markup=kb)
    else:
        msg = await bot.send_message(chat_id=channel_id, text="🎯 Розыгрыш", reply_markup=kb)

    await set_contest_message_id(contest_id, msg.message_id)

    # ── ФИКС: запускаем таймер сразу после публикации ──
    if data.get("finish_condition") == "time":
        from utils.scheduler import schedule_contest
        finish_dt = datetime.strptime(data["finish_value"], "%d.%m.%Y %H:%M")
        schedule_contest(bot, contest_id, finish_dt)

    await call.message.edit_text(
        f"🎉 Розыгрыш <b>#{contest_id}</b> опубликован!", reply_markup=main_menu_kb()
    )
    await call.answer("Опубликовано!")
