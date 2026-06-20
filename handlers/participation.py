from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject

from keyboards import sponsors_check_kb, main_menu_kb, slots_grid_kb
from db.database import (
    get_contest, get_sponsors, add_participant, is_participant,
    get_slot, book_slot, get_all_slots, finish_contest, get_booked_slots_count
)
from utils.helpers import check_user_subscription, format_user_mention

router = Router()


async def verify_subscriptions(bot: Bot, user_id: int, sponsors: list[dict]) -> list[dict]:
    """Returns list of sponsors user is NOT subscribed to."""
    missing = []
    for sp in sponsors:
        channel_id = sp.get("channel_id")
        if channel_id:
            ok = await check_user_subscription(bot, user_id, channel_id)
            if not ok:
                missing.append(sp)
    return missing


# ──────────────────────── DEEP LINK ENTRY ────────────────────────

@router.message(CommandStart(deep_link=True))
async def handle_deep_link(message: Message, command: CommandObject, bot: Bot):
    payload = command.args or ""

    # join_<contest_id>  → classic
    if payload.startswith("join_"):
        try:
            contest_id = int(payload.split("_")[1])
        except (ValueError, IndexError):
            await message.answer("❌ Неверная ссылка.")
            return
        await handle_classic_join(message, bot, contest_id)

    # slot_<contest_id>_<slot_number>  → slots
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
        await message.answer(
            "👋 Привет! Используйте эту ссылку для участия в розыгрыше.",
            reply_markup=main_menu_kb()
        )


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

    # Check main channel subscription
    channel_id = contest["channel_id"]
    in_main = await check_user_subscription(bot, user_id, channel_id)
    if not in_main:
        ch_username = contest.get("channel_username", "")
        link = f"https://t.me/{ch_username}" if ch_username else ""
        await message.answer(
            f"❌ Для участия необходимо подписаться на основной канал!",
            reply_markup=_channel_link_kb(ch_username, "Подписаться на канал") if link else None
        )
        return

    # Check sponsors
    sponsors = await get_sponsors(contest_id)
    missing = await verify_subscriptions(bot, user_id, sponsors)
    if missing:
        await message.answer(
            "❌ Для участия подпишитесь на все обязательные каналы:",
            reply_markup=sponsors_check_kb(missing)
        )
        # Store pending state
        await _store_pending(message, f"join_{contest_id}")
        return

    # Register participant
    already = await is_participant(contest_id, user_id)
    if already:
        await message.answer("✅ Вы уже участвуете в этом розыгрыше! Ждите результатов.")
        return

    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    added = await add_participant(contest_id, user_id, user.username, full_name)
    if added:
        await message.answer(
            f"🎉 <b>Вы успешно зарегистрированы!</b>\n\n"
            f"Вы участвуете в розыгрыше. Ждите результатов! 🤞"
        )

        # Check finish_condition = count
        if contest.get("finish_condition") == "count":
            from db.database import count_participants
            count = await count_participants(contest_id)
            limit = int(contest.get("finish_value", 0))
            if limit and count >= limit:
                await auto_finish_classic(bot, contest)
    else:
        await message.answer("✅ Вы уже участвуете в этом розыгрыше!")


async def auto_finish_classic(bot: Bot, contest: dict):
    """Auto-draw when participant limit reached."""
    from db.database import get_participants, finish_contest
    from utils.helpers import pick_winners

    contest_id = contest["id"]
    participants = await get_participants(contest_id)
    if not participants:
        return

    winners_count = contest.get("winners_count", 1)
    winners = pick_winners(participants, winners_count)

    winners_text = "\n".join(
        f"{i+1}. {format_user_mention(w.get('username'), w.get('full_name', ''), w['user_id'])}"
        for i, w in enumerate(winners)
    )

    result_suffix = (
        f"\n\n🏆 <b>Итоги розыгрыша!</b>\n\n"
        f"Победители:\n{winners_text}\n\n🎉"
    )

    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")
    if message_id:
        try:
            if contest.get("photo_id"):
                await bot.edit_message_caption(
                    chat_id=channel_id,
                    message_id=message_id,
                    caption=(contest.get("text") or "") + result_suffix,
                    reply_markup=None
                )
            else:
                await bot.edit_message_text(
                    chat_id=channel_id,
                    message_id=message_id,
                    text=(contest.get("text") or "") + result_suffix,
                    reply_markup=None
                )
        except Exception:
            pass

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

    # Notify admin
    try:
        await bot.send_message(
            chat_id=contest["admin_id"],
            text=f"🏆 Розыгрыш <b>#{contest_id}</b> автоматически завершён!\n\n"
                 f"Победители:\n{winners_text}"
        )
    except Exception:
        pass


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

    # Check if slot already taken
    existing = await get_slot(contest_id, slot_number)
    if existing and existing.get("user_id"):
        await message.answer(f"❌ Слот #{slot_number} уже занят. Выберите другой.")
        return

    # Check main channel
    channel_id = contest["channel_id"]
    in_main = await check_user_subscription(bot, user_id, channel_id)
    if not in_main:
        ch_username = contest.get("channel_username", "")
        await message.answer(
            f"❌ Сначала подпишитесь на основной канал розыгрыша!",
            reply_markup=_channel_link_kb(ch_username, "Подписаться") if ch_username else None
        )
        return

    # Check sponsors
    sponsors = await get_sponsors(contest_id)
    missing = await verify_subscriptions(bot, user_id, sponsors)
    if missing:
        await message.answer(
            "❌ Подпишитесь на все обязательные каналы:",
            reply_markup=sponsors_check_kb(missing)
        )
        await _store_pending(message, f"slot_{contest_id}_{slot_number}")
        return

    # Payment check
    if contest.get("payment_type") == "paid":
        price = int(contest.get("slot_price", 0))
        if price > 0:
            await message.answer(
                f"💳 Для бронирования слота #{slot_number} необходима оплата <b>{price} ⭐</b>.\n\n"
                f"Нажмите кнопку для оплаты:"
            )
            await bot.send_invoice(
                chat_id=user_id,
                title=f"Слот #{slot_number}",
                description=f"Бронирование слота #{slot_number} в лотерее #{contest_id}",
                payload=f"slot_{contest_id}_{slot_number}",
                currency="XTR",
                prices=[{"label": f"Слот #{slot_number}", "amount": price}],
                provider_token=""  # Empty for Telegram Stars
            )
            return

    # Free slot — book immediately
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    booked = await book_slot(contest_id, slot_number, user_id, user.username, full_name, "free")
    if not booked:
        await message.answer(f"❌ Слот #{slot_number} только что занял другой пользователь. Выберите другой.")
        return

    await process_slot_booked(bot, contest, slot_number, user)


async def process_slot_booked(bot: Bot, contest: dict, slot_number: int, user):
    """Called after slot is confirmed booked (free or paid)."""
    contest_id = contest["id"]
    winning_slot = contest.get("winning_slot")
    user_id = user.id
    username = getattr(user, "username", None)
    full_name = f"{user.first_name} {getattr(user, 'last_name', '') or ''}".strip()

    # Update slot grid in channel
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
        # 🎉 WINNER!
        mention = format_user_mention(username, full_name, user_id)

        # Message to winner
        await bot.send_message(
            chat_id=user_id,
            text=f"🎊 <b>Поздравляем! Вы выбрали выигрышный слот #{slot_number}!</b>\n\n"
                 f"Вы победили в лотерее! Организатор скоро свяжется с вами. 🏆"
        )

        # Message to admin
        try:
            await bot.send_message(
                chat_id=contest["admin_id"],
                text=f"🚨 <b>Определён победитель!</b>\n\n"
                     f"{mention} выбрал выигрышный слот <b>#{slot_number}</b> "
                     f"в лотерее <b>#{contest_id}</b>!\n\n"
                     f"Свяжитесь с победителем."
            )
        except Exception:
            pass

        # Edit channel post
        finish_text = (
            f"\n\n🏆 <b>Лотерея окончена!</b>\n"
            f"Выигрышным оказался слот <b>#{slot_number}</b>.\n"
            f"Победитель: {mention} 🎉"
        )
        if message_id:
            try:
                if contest.get("photo_id"):
                    await bot.edit_message_caption(
                        chat_id=channel_id,
                        message_id=message_id,
                        caption=(contest.get("text") or "") + finish_text,
                        reply_markup=None
                    )
                else:
                    await bot.edit_message_text(
                        chat_id=channel_id,
                        message_id=message_id,
                        text=(contest.get("text") or "") + finish_text,
                        reply_markup=None
                    )
            except Exception:
                pass

        await finish_contest(contest_id)

    else:
        # Not winner
        await bot.send_message(
            chat_id=user_id,
            text=f"✅ Слот <b>#{slot_number}</b> забронирован!\n\n"
                 f"Ожидайте окончания лотереи. Удачи! 🍀"
        )


# ──────────────────────── SUBSCRIPTION RE-CHECK ────────────────────────

# Simple in-memory pending store (production should use Redis/DB)
_pending: dict[int, str] = {}


async def _store_pending(message: Message, payload: str):
    _pending[message.from_user.id] = payload


@router.callback_query(F.data == "check_subscriptions")
async def recheck_subscriptions(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    payload = _pending.get(user_id)
    if not payload:
        await call.answer("Нет ожидающего действия. Перейдите по ссылке снова.", show_alert=True)
        return

    await call.answer("Проверяем подписки...")

    # Re-trigger via fake message
    class _FakeMsg:
        from_user = call.from_user
        text = f"/start {payload}"
        caption = None
        photo = None

        async def answer(self, *args, **kwargs):
            await call.message.answer(*args, **kwargs)

    fake = _FakeMsg()

    if payload.startswith("join_"):
        try:
            contest_id = int(payload.split("_")[1])
        except ValueError:
            return
        await handle_classic_join(fake, bot, contest_id)
    elif payload.startswith("slot_"):
        parts = payload.split("_")
        try:
            contest_id = int(parts[1])
            slot_number = int(parts[2])
        except (ValueError, IndexError):
            return
        await handle_slot_pick(fake, bot, contest_id, slot_number)

    if user_id in _pending:
        del _pending[user_id]


# ──────────────────────── HELPERS ────────────────────────

def _channel_link_kb(username: str, label: str):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📢 {label}", url=f"https://t.me/{username.lstrip('@')}")
    return builder.as_markup()
