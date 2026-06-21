from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject

from keyboards import sponsors_check_kb, main_menu_kb, slots_grid_kb
from db.database import (
    get_contest, get_sponsors, add_participant, is_participant,
    get_slot, book_slot, get_all_slots, finish_contest,
    count_participants, count_user_slots
)
from utils.helpers import check_user_subscription, format_user_mention

router = Router()


async def verify_subscriptions(bot: Bot, user_id: int, sponsors: list[dict]) -> list[dict]:
    missing = []
    for sp in sponsors:
        channel_id = sp.get("channel_id")
        if channel_id:
            ok = await check_user_subscription(bot, user_id, channel_id)
            if not ok:
                missing.append(sp)
    return missing


# ──────────────────────── DEEP LINK ────────────────────────

@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject, bot: Bot):
    payload = command.args or ""

    if payload.startswith("join_"):
        try:
            contest_id = int(payload.split("_")[1])
        except (ValueError, IndexError):
            await message.answer("❌ Неверная ссылка.")
            return
        await handle_classic_join(message, bot, contest_id)

    elif payload.startswith("slot_"):
        parts = payload.split("_")
        if len(parts) < 3:
            await message.answer("❌ Неверная ссылка.")
            return
        try:
            contest_id = int(parts[1])
            slot_number = int(parts[2])
        except ValueError:
            await message.answer("❌ Неверная ссылка.")
            return
        await handle_slot_pick(message, bot, contest_id, slot_number)

    else:
        from handlers.start import show_main_menu
        await show_main_menu(message, f"👋 Привет, {message.from_user.first_name}!")


# ──────────────────────── CLASSIC JOIN ────────────────────────

async def handle_classic_join(message: Message, bot: Bot, contest_id: int):
    contest = await get_contest(contest_id)
    if not contest or contest["type"] != "classic":
        await message.answer("❌ Розыгрыш не найден.")
        return
    if contest["status"] != "active":
        await message.answer("🔒 Этот розыгрыш уже завершён.")
        return

    user = message.from_user
    user_id = user.id

    # Проверка подписки на основной канал
    in_main = await check_user_subscription(bot, user_id, contest["channel_id"])
    if not in_main:
        ch_username = contest.get("channel_username", "")
        await message.answer(
            "❌ Для участия необходимо подписаться на основной канал!",
            reply_markup=_channel_link_kb(ch_username, "Подписаться на канал") if ch_username else None
        )
        return

    # Проверка спонсоров
    sponsors = await get_sponsors(contest_id)
    missing = await verify_subscriptions(bot, user_id, sponsors)
    if missing:
        await message.answer(
            "❌ Подпишитесь на все обязательные каналы:",
            reply_markup=sponsors_check_kb(missing)
        )
        _pending[user_id] = f"join_{contest_id}"
        return

    already = await is_participant(contest_id, user_id)
    if already:
        await message.answer("✅ Вы уже участвуете в этом розыгрыше! Ждите результатов.")
        return

    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    added = await add_participant(contest_id, user_id, user.username, full_name)
    if not added:
        await message.answer("✅ Вы уже участвуете в этом розыгрыше!")
        return

    count = await count_participants(contest_id)
    await message.answer(
        f"🎉 <b>Вы успешно зарегистрированы!</b>\n\n"
        f"Участников: <b>{count}</b>\nЖдите результатов! 🤞"
    )

    # Обновить кнопку со счётчиком если включено
    if contest.get("show_count"):
        await _update_classic_button(bot, contest, count)

    # Автофиниш по лимиту участников
    if contest.get("finish_condition") == "count":
        limit = int(contest.get("finish_value", 0))
        if limit and count >= limit:
            await auto_finish_classic(bot, contest)


async def _update_classic_button(bot: Bot, contest: dict, count: int):
    """Обновляет текст кнопки с актуальным счётчиком участников."""
    from keyboards import participate_kb
    me = await bot.get_me()
    btn_text = contest.get("button_text", "Участвовать")
    kb = participate_kb(me.username, contest["id"], f"{btn_text} ({count})")
    try:
        await bot.edit_message_reply_markup(
            chat_id=contest["channel_id"],
            message_id=contest["message_id"],
            reply_markup=kb
        )
    except Exception:
        pass


async def auto_finish_classic(bot: Bot, contest: dict):
    from db.database import get_participants
    from utils.helpers import pick_winners

    contest_id = contest["id"]
    participants = await get_participants(contest_id)
    if not participants:
        return

    winners = pick_winners(participants, contest.get("winners_count", 1))
    winners_text = "\n".join(
        f"{i+1}. {format_user_mention(w.get('username'), w.get('full_name', ''), w['user_id'])}"
        for i, w in enumerate(winners)
    )

    await _post_winner_message(bot, contest, winners_text)
    await finish_contest(contest_id)

    for w in winners:
        try:
            await bot.send_message(
                chat_id=w["user_id"],
                text=f"🎉 Поздравляем! Вы победили в розыгрыше <b>#{contest_id}</b>!\n"
                     f"С вами свяжется организатор."
            )
        except Exception:
            pass

    try:
        await bot.send_message(
            chat_id=contest["admin_id"],
            text=f"🏆 Розыгрыш <b>#{contest_id}</b> завершён автоматически!\n\n"
                 f"Победители:\n{winners_text}"
        )
    except Exception:
        pass


async def _post_winner_message(bot: Bot, contest: dict, winners_text: str):
    """Отправляет НОВЫЙ пост с победителями (не редактирует старый)."""
    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")

    result_text = (
        f"🏆 <b>Итоги розыгрыша #{contest['id']}!</b>\n\n"
        f"Победител{'и' if winners_text.count('\n') > 0 else 'ь'}:\n{winners_text}\n\n"
        f"Поздравляем! 🎉"
    )

    # Убрать кнопку со старого поста
    if message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=None
            )
        except Exception:
            pass

    # Отправить новый пост с результатами
    await bot.send_message(chat_id=channel_id, text=result_text)


# ──────────────────────── SLOT PICK ────────────────────────

async def handle_slot_pick(message: Message, bot: Bot, contest_id: int, slot_number: int):
    contest = await get_contest(contest_id)
    if not contest or contest["type"] != "slots":
        await message.answer("❌ Лотерея не найдена.")
        return
    if contest["status"] != "active":
        await message.answer("🔒 Эта лотерея уже завершена.")
        return

    total = contest.get("total_slots", 0)
    if slot_number < 1 or slot_number > total:
        await message.answer(f"❌ Слот #{slot_number} не существует.")
        return

    user = message.from_user
    user_id = user.id

    # Слот уже занят?
    existing = await get_slot(contest_id, slot_number)
    if existing and existing.get("user_id"):
        await message.answer(f"❌ Слот #{slot_number} уже занят. Выберите другой.")
        return

    # Проверка лимита попыток
    max_attempts = contest.get("max_attempts") or 1
    user_booked = await count_user_slots(contest_id, user_id)
    if user_booked >= max_attempts:
        slots_word = "слот" if max_attempts == 1 else "слота" if max_attempts < 5 else "слотов"
        await message.answer(
            f"❌ Вы уже взяли максимальное количество слотов "
            f"(<b>{max_attempts} {slots_word}</b>) в этой лотерее."
        )
        return

    # Подписка на основной канал
    in_main = await check_user_subscription(bot, user_id, contest["channel_id"])
    if not in_main:
        ch_username = contest.get("channel_username", "")
        await message.answer(
            "❌ Сначала подпишитесь на основной канал!",
            reply_markup=_channel_link_kb(ch_username, "Подписаться") if ch_username else None
        )
        return

    # Спонсоры
    sponsors = await get_sponsors(contest_id)
    missing = await verify_subscriptions(bot, user_id, sponsors)
    if missing:
        await message.answer(
            "❌ Подпишитесь на все обязательные каналы:",
            reply_markup=sponsors_check_kb(missing)
        )
        _pending[user_id] = f"slot_{contest_id}_{slot_number}"
        return

    # Оплата
    if contest.get("payment_type") == "paid":
        price = int(contest.get("slot_price", 0))
        if price > 0:
            await message.answer(
                f"💳 Оплата слота #{slot_number}: <b>{price} ⭐</b>"
            )
            await bot.send_invoice(
                chat_id=user_id,
                title=f"Слот #{slot_number}",
                description=f"Бронирование слота #{slot_number} в лотерее #{contest_id}",
                payload=f"slot_{contest_id}_{slot_number}",
                currency="XTR",
                prices=[{"label": f"Слот #{slot_number}", "amount": price}],
                provider_token=""
            )
            return

    # Бесплатный — бронируем сразу
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    booked = await book_slot(contest_id, slot_number, user_id, user.username, full_name, "free")
    if not booked:
        await message.answer(f"❌ Слот #{slot_number} только что занял другой пользователь.")
        return

    await process_slot_booked(bot, contest, slot_number, user)


async def process_slot_booked(bot: Bot, contest: dict, slot_number: int, user):
    contest_id = contest["id"]
    winning_slot = contest.get("winning_slot")
    user_id = user.id
    username = getattr(user, "username", None)
    full_name = f"{user.first_name} {getattr(user, 'last_name', '') or ''}".strip()

    # Обновить сетку слотов в канале
    all_slots = await get_all_slots(contest_id)
    booked_set = {s["slot_number"] for s in all_slots if s.get("user_id")}
    me = await bot.get_me()
    new_kb = slots_grid_kb(me.username, contest_id, contest["total_slots"], booked_set)

    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")
    if message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=new_kb
            )
        except Exception:
            pass

    if slot_number == winning_slot:
        mention = format_user_mention(username, full_name, user_id)

        await bot.send_message(
            chat_id=user_id,
            text=f"🎊 <b>Поздравляем! Вы выбрали выигрышный слот #{slot_number}!</b>\n\n"
                 f"Вы победили в лотерее! Организатор свяжется с вами. 🏆"
        )

        try:
            await bot.send_message(
                chat_id=contest["admin_id"],
                text=f"🚨 <b>Определён победитель!</b>\n\n"
                     f"{mention} выбрал выигрышный слот <b>#{slot_number}</b> "
                     f"в лотерее <b>#{contest_id}</b>!"
            )
        except Exception:
            pass

        # Убрать кнопки со старого поста
        if message_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=channel_id,
                    message_id=message_id,
                    reply_markup=None
                )
            except Exception:
                pass

        # Новый пост с результатом
        await bot.send_message(
            chat_id=channel_id,
            text=f"🏆 <b>Лотерея #{contest_id} завершена!</b>\n\n"
                 f"Выигрышный слот: <b>#{slot_number}</b>\n"
                 f"Победитель: {mention} 🎉"
        )

        await finish_contest(contest_id)

    else:
        await bot.send_message(
            chat_id=user_id,
            text=f"✅ Слот <b>#{slot_number}</b> забронирован!\n\n"
                 f"Ожидайте окончания лотереи. Удачи! 🍀"
        )


# ──────────────────────── RE-CHECK SUBSCRIPTIONS ────────────────────────

_pending: dict[int, str] = {}


@router.callback_query(F.data == "check_subscriptions")
async def recheck_subscriptions(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    payload = _pending.get(user_id)
    if not payload:
        await call.answer("Нет ожидающего действия. Перейдите по ссылке снова.", show_alert=True)
        return

    await call.answer("Проверяем подписки...")

    class _FakeMsg:
        from_user = call.from_user
        caption = None
        photo = None
        async def answer(self, *args, **kwargs):
            await call.message.answer(*args, **kwargs)

    fake = _FakeMsg()

    if payload.startswith("join_"):
        try:
            contest_id = int(payload.split("_")[1])
            await handle_classic_join(fake, bot, contest_id)
        except ValueError:
            pass
    elif payload.startswith("slot_"):
        parts = payload.split("_")
        try:
            contest_id = int(parts[1])
            slot_number = int(parts[2])
            await handle_slot_pick(fake, bot, contest_id, slot_number)
        except (ValueError, IndexError):
            pass

    _pending.pop(user_id, None)


# ──────────────────────── HELPERS ────────────────────────

def _channel_link_kb(username: str, label: str):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📢 {label}", url=f"https://t.me/{username.lstrip('@')}")
    return builder.as_markup()
