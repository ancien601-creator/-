from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext

from keyboards import sponsors_check_kb, main_menu_kb, slots_grid_kb
from db.database import (
    get_contest, get_sponsors, add_participant, is_participant,
    get_slot, book_slot, get_all_slots, finish_contest,
    count_participants, count_user_slots,
    get_user_ticket_count, add_lottery_tickets, get_total_tickets
)
from utils.helpers import check_user_subscription, format_user_mention
from utils.states import LotteryBuy

router = Router()

_pending: dict[int, str] = {}


async def _check_sponsors(bot: Bot, user_id: int, contest_id: int) -> list[dict]:
    sponsors = await get_sponsors(contest_id)
    missing = []
    for sp in sponsors:
        if sp.get("channel_id"):
            ok = await check_user_subscription(bot, user_id, sp["channel_id"])
            if not ok:
                missing.append(sp)
    return missing


# ──────────────────────── /start ────────────────────────

@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    payload = command.args or ""

    if payload.startswith("join_"):
        try:
            contest_id = int(payload.split("_")[1])
            await handle_classic_join(message, bot, contest_id)
        except (ValueError, IndexError):
            await message.answer("❌ Неверная ссылка.")

    elif payload.startswith("slot_"):
        parts = payload.split("_")
        try:
            contest_id, slot_number = int(parts[1]), int(parts[2])
            await handle_slot_pick(message, bot, contest_id, slot_number)
        except (ValueError, IndexError):
            await message.answer("❌ Неверная ссылка.")

    elif payload.startswith("lottery_"):
        try:
            contest_id = int(payload.split("_")[1])
            await handle_lottery_join(message, bot, contest_id, state)
        except (ValueError, IndexError):
            await message.answer("❌ Неверная ссылка.")

    elif payload.startswith("battle_"):
        try:
            contest_id = int(payload.split("_")[1])
            from handlers.battle import join_battle
            await join_battle(message, bot, contest_id)
        except (ValueError, IndexError):
            await message.answer("❌ Неверная ссылка.")

    else:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\nДобро пожаловать в бот розыгрышей.",
            reply_markup=main_menu_kb()
        )


# ──────────────────────── CLASSIC ────────────────────────

async def handle_classic_join(message: Message, bot: Bot, contest_id: int):
    contest = await get_contest(contest_id)
    if not contest or contest["type"] != "classic":
        await message.answer("❌ Розыгрыш не найден.")
        return
    if contest["status"] != "active":
        await message.answer("🔒 Розыгрыш уже завершён.")
        return

    user = message.from_user

    in_main = await check_user_subscription(bot, user.id, contest["channel_id"])
    if not in_main:
        uname = contest.get("channel_username", "")
        await message.answer("❌ Подпишитесь на основной канал!", reply_markup=_link_kb(uname, "Подписаться") if uname else None)
        return

    missing = await _check_sponsors(bot, user.id, contest_id)
    if missing:
        await message.answer("❌ Подпишитесь на все каналы:", reply_markup=sponsors_check_kb(missing))
        _pending[user.id] = f"join_{contest_id}"
        return

    if await is_participant(contest_id, user.id):
        await message.answer("✅ Вы уже участвуете! Ждите результатов.")
        return

    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    added = await add_participant(contest_id, user.id, user.username, full_name)
    if not added:
        await message.answer("✅ Вы уже участвуете!")
        return

    count = await count_participants(contest_id)
    await message.answer(f"🎉 <b>Вы зарегистрированы!</b>\n\nУчастников: <b>{count}</b> 🤞")

    if contest.get("show_count"):
        await _update_classic_button(bot, contest, count)

    if contest.get("finish_condition") == "count":
        limit = int(contest.get("finish_value", 0))
        if limit and count >= limit:
            await _auto_finish_classic(bot, contest)


async def _update_classic_button(bot: Bot, contest: dict, count: int):
    from keyboards import participate_kb
    me = await bot.get_me()
    btn_text = f"{contest.get('button_text', 'Участвовать')} ({count})"
    kb = participate_kb(me.username, contest["id"], btn_text)
    try:
        await bot.edit_message_reply_markup(chat_id=contest["channel_id"], message_id=contest["message_id"], reply_markup=kb)
    except Exception:
        pass


async def _auto_finish_classic(bot: Bot, contest: dict):
    from db.database import get_participants
    from utils.helpers import pick_winners

    contest_id = contest["id"]
    participants = await get_participants(contest_id)
    if not participants:
        return

    winners = pick_winners(participants, contest.get("winners_count", 1))
    winners_text = "\n".join(
        f"{i+1}. {format_user_mention(w.get('username'), w.get('full_name',''), w['user_id'])}"
        for i, w in enumerate(winners)
    )

    if contest.get("message_id"):
        try:
            await bot.edit_message_reply_markup(chat_id=contest["channel_id"], message_id=contest["message_id"], reply_markup=None)
        except Exception:
            pass

    await bot.send_message(
        chat_id=contest["channel_id"],
        text=f"🏆 <b>Итоги розыгрыша #{contest_id}!</b>\n\nПобедители:\n{winners_text}\n\n🎉"
    )
    await finish_contest(contest_id)

    for w in winners:
        try:
            await bot.send_message(chat_id=w["user_id"], text=f"🎉 Вы победили в розыгрыше <b>#{contest_id}</b>!")
        except Exception:
            pass


# ──────────────────────── SLOTS ────────────────────────

async def handle_slot_pick(message: Message, bot: Bot, contest_id: int, slot_number: int):
    contest = await get_contest(contest_id)
    if not contest or contest["type"] != "slots":
        await message.answer("❌ Лотерея не найдена.")
        return
    if contest["status"] != "active":
        await message.answer("🔒 Лотерея завершена.")
        return

    user = message.from_user
    total = contest.get("total_slots", 0)

    if slot_number < 1 or slot_number > total:
        await message.answer(f"❌ Слот #{slot_number} не существует.")
        return

    existing = await get_slot(contest_id, slot_number)
    if existing and existing.get("user_id"):
        await message.answer(f"❌ Слот #{slot_number} уже занят.")
        return

    max_att = contest.get("max_attempts") or 1
    if await count_user_slots(contest_id, user.id) >= max_att:
        await message.answer(f"❌ Вы уже взяли максимум слотов ({max_att}).")
        return

    in_main = await check_user_subscription(bot, user.id, contest["channel_id"])
    if not in_main:
        uname = contest.get("channel_username", "")
        await message.answer("❌ Подпишитесь на канал!", reply_markup=_link_kb(uname, "Подписаться") if uname else None)
        return

    missing = await _check_sponsors(bot, user.id, contest_id)
    if missing:
        await message.answer("❌ Подпишитесь на каналы:", reply_markup=sponsors_check_kb(missing))
        _pending[user.id] = f"slot_{contest_id}_{slot_number}"
        return

    if contest.get("payment_type") == "paid":
        price = int(contest.get("slot_price", 0))
        if price > 0:
            await message.answer(f"💳 Оплата слота #{slot_number}: <b>{price} ⭐</b>")
            await bot.send_invoice(
                chat_id=user.id,
                title=f"Слот #{slot_number}",
                description=f"Слот #{slot_number} в лотерее #{contest_id}",
                payload=f"slot_{contest_id}_{slot_number}",
                currency="XTR",
                prices=[{"label": f"Слот #{slot_number}", "amount": price}],
                provider_token=""
            )
            return

    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    booked = await book_slot(contest_id, slot_number, user.id, user.username, full_name, "free")
    if not booked:
        await message.answer(f"❌ Слот #{slot_number} только что заняли.")
        return

    await process_slot_booked(bot, contest, slot_number, user)


async def process_slot_booked(bot: Bot, contest: dict, slot_number: int, user):
    contest_id = contest["id"]
    winning_slot = contest.get("winning_slot")
    user_id = user.id
    username = getattr(user, "username", None)
    full_name = f"{user.first_name} {getattr(user,'last_name','') or ''}".strip()

    all_slots = await get_all_slots(contest_id)
    booked_set = {s["slot_number"] for s in all_slots if s.get("user_id")}
    me = await bot.get_me()
    new_kb = slots_grid_kb(me.username, contest_id, contest["total_slots"], booked_set)

    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")
    if message_id:
        try:
            await bot.edit_message_reply_markup(chat_id=channel_id, message_id=message_id, reply_markup=new_kb)
        except Exception:
            pass

    if slot_number == winning_slot:
        mention = format_user_mention(username, full_name, user_id)
        await bot.send_message(
            chat_id=user_id,
            text=f"🎊 <b>Вы выбрали выигрышный слот #{slot_number}!</b>\nВы победили! 🏆"
        )
        try:
            await bot.send_message(
                chat_id=contest["admin_id"],
                text=f"🚨 <b>Победитель!</b> {mention} → слот <b>#{slot_number}</b> в лотерее <b>#{contest_id}</b>"
            )
        except Exception:
            pass
        if message_id:
            try:
                await bot.edit_message_reply_markup(chat_id=channel_id, message_id=message_id, reply_markup=None)
            except Exception:
                pass
        await bot.send_message(
            chat_id=channel_id,
            text=f"🏆 <b>Лотерея #{contest_id} завершена!</b>\nВыигрышный слот: <b>#{slot_number}</b>\nПобедитель: {mention} 🎉"
        )
        await finish_contest(contest_id)
    else:
        await bot.send_message(chat_id=user_id, text=f"✅ Слот <b>#{slot_number}</b> забронирован! Удачи 🍀")


# ──────────────────────── LOTTERY ────────────────────────

async def handle_lottery_join(message: Message, bot: Bot, contest_id: int, state: FSMContext):
    contest = await get_contest(contest_id)
    if not contest or contest["type"] != "lottery":
        await message.answer("❌ Лотерея не найдена.")
        return
    if contest["status"] != "active":
        await message.answer("🔒 Лотерея завершена.")
        return

    user = message.from_user

    in_main = await check_user_subscription(bot, user.id, contest["channel_id"])
    if not in_main:
        uname = contest.get("channel_username", "")
        await message.answer("❌ Подпишитесь на канал!", reply_markup=_link_kb(uname, "Подписаться") if uname else None)
        return

    missing = await _check_sponsors(bot, user.id, contest_id)
    if missing:
        await message.answer("❌ Подпишитесь на каналы:", reply_markup=sponsors_check_kb(missing))
        _pending[user.id] = f"lottery_{contest_id}"
        return

    max_tickets = contest.get("max_attempts") or 1
    already = await get_user_ticket_count(contest_id, user.id)
    remaining = max_tickets - already

    if remaining <= 0:
        total = await get_total_tickets(contest_id)
        await message.answer(f"❌ Вы уже взяли максимум билетов ({max_tickets}).\n\nВсего билетов в пуле: {total}")
        return

    price = contest.get("slot_price") or 0
    is_paid = contest.get("payment_type") == "paid" and price > 0

    if remaining == 1:
        if is_paid:
            full_name = f"{user.first_name} {user.last_name or ''}".strip()
            await state.update_data(lottery_contest_id=contest_id, lottery_quantity=1,
                                    lottery_full_name=full_name, lottery_username=user.username)
            await message.answer(f"💳 Оплата 1 билета: <b>{price} ⭐</b>")
            await bot.send_invoice(
                chat_id=user.id,
                title="Лотерейный билет",
                description=f"1 билет в лотерее #{contest_id}",
                payload=f"lottery_{contest_id}_1",
                currency="XTR",
                prices=[{"label": "1 билет", "amount": price}],
                provider_token=""
            )
        else:
            full_name = f"{user.first_name} {user.last_name or ''}".strip()
            await add_lottery_tickets(contest_id, user.id, user.username, full_name, 1)
            total = await get_total_tickets(contest_id)
            await message.answer(f"🎟 Билет получен!\n\nВаш билет #{already+1}\nВсего билетов в пуле: {total}")
        return

    # Несколько доступных билетов — спросить количество
    await state.set_state(LotteryBuy.enter_quantity)
    await state.update_data(
        lottery_contest_id=contest_id,
        lottery_max=remaining,
        lottery_price=price,
        lottery_is_paid=is_paid,
        lottery_username=user.username,
        lottery_full_name=f"{user.first_name} {user.last_name or ''}".strip()
    )
    if is_paid:
        await message.answer(
            f"🎟 Сколько билетов взять? (у вас осталось <b>{remaining}</b>, цена {price} ⭐ каждый)\n\n"
            f"Введите число от 1 до {remaining}:"
        )
    else:
        await message.answer(
            f"🎟 Сколько билетов взять? (доступно <b>{remaining}</b>)\n\n"
            f"Введите число от 1 до {remaining}:"
        )


@router.message(LotteryBuy.enter_quantity)
async def lottery_buy_quantity(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    val = message.text.strip()
    max_q = data.get("lottery_max", 1)

    if not val.isdigit() or int(val) < 1 or int(val) > max_q:
        await message.answer(f"❌ Введите число от 1 до {max_q}.")
        return

    quantity = int(val)
    contest_id = data["lottery_contest_id"]
    is_paid = data.get("lottery_is_paid")
    price = data.get("lottery_price", 0)

    await state.clear()

    if is_paid and price > 0:
        total_price = price * quantity
        await message.answer(f"💳 Оплата {quantity} билет(ов): <b>{total_price} ⭐</b>")
        await bot.send_invoice(
            chat_id=message.from_user.id,
            title=f"Лотерейные билеты ({quantity} шт.)",
            description=f"{quantity} билет(ов) в лотерее #{contest_id}",
            payload=f"lottery_{contest_id}_{quantity}",
            currency="XTR",
            prices=[{"label": f"{quantity} билет(ов)", "amount": total_price}],
            provider_token=""
        )
    else:
        user = message.from_user
        full_name = f"{user.first_name} {user.last_name or ''}".strip()
        await add_lottery_tickets(contest_id, user.id, user.username, full_name, quantity)
        total = await get_total_tickets(contest_id)
        await message.answer(f"🎟 <b>{quantity} билет(ов) получено!</b>\n\nВсего в пуле: {total}")


# ──────────────────────── RE-CHECK SUBSCRIPTIONS ────────────────────────

@router.callback_query(F.data == "check_subscriptions")
async def recheck_subscriptions(call: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = call.from_user.id
    payload = _pending.get(user_id)
    if not payload:
        await call.answer("Нет ожидающего действия. Перейдите по ссылке снова.", show_alert=True)
        return
    await call.answer("Проверяем...")

    class _FakeMsg:
        from_user = call.from_user
        caption = None
        photo = None
        async def answer(self, *a, **kw):
            await call.message.answer(*a, **kw)

    fake = _FakeMsg()
    try:
        if payload.startswith("join_"):
            await handle_classic_join(fake, bot, int(payload.split("_")[1]))
        elif payload.startswith("slot_"):
            p = payload.split("_")
            await handle_slot_pick(fake, bot, int(p[1]), int(p[2]))
        elif payload.startswith("lottery_"):
            await handle_lottery_join(fake, bot, int(payload.split("_")[1]), state)
        elif payload.startswith("battle_"):
            from handlers.battle import join_battle
            await join_battle(fake, bot, int(payload.split("_")[1]))
    except Exception:
        pass
    _pending.pop(user_id, None)


# ──────────────────────── HELPERS ────────────────────────

def _link_kb(username: str, label: str):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text=f"📢 {label}", url=f"https://t.me/{username.lstrip('@')}")
    return b.as_markup()
