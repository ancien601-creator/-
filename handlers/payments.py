from aiogram import Router, F, Bot
from aiogram.types import Message, PreCheckoutQuery

from db.database import get_contest, get_slot, book_slot, set_slot_paid, add_lottery_tickets

router = Router()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, bot: Bot):
    payload = query.invoice_payload
    if payload.startswith("slot_"):
        parts = payload.split("_")
        try:
            contest_id, slot_number = int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            await query.answer(ok=False, error_message="Неверный платёж.")
            return
        contest = await get_contest(contest_id)
        if not contest or contest["status"] != "active":
            await query.answer(ok=False, error_message="Лотерея завершена.")
            return
        existing = await get_slot(contest_id, slot_number)
        if existing and existing.get("user_id") and existing["user_id"] != query.from_user.id:
            await query.answer(ok=False, error_message=f"Слот #{slot_number} уже занят.")
            return
    elif payload.startswith("lottery_"):
        parts = payload.split("_")
        try:
            contest_id = int(parts[1])
        except (ValueError, IndexError):
            await query.answer(ok=False, error_message="Неверный платёж.")
            return
        contest = await get_contest(contest_id)
        if not contest or contest["status"] != "active":
            await query.answer(ok=False, error_message="Лотерея завершена.")
            return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    payment = message.successful_payment
    payload = payment.invoice_payload
    user = message.from_user
    full_name = f"{user.first_name} {user.last_name or ''}".strip()

    if payload.startswith("slot_"):
        parts = payload.split("_")
        try:
            contest_id, slot_number = int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            return
        contest = await get_contest(contest_id)
        if not contest:
            return
        booked = await book_slot(contest_id, slot_number, user.id, user.username, full_name, "paid")
        if booked:
            await set_slot_paid(contest_id, slot_number, payment.telegram_payment_charge_id)
            await message.answer(f"✅ Оплата прошла! Слот <b>#{slot_number}</b> ваш.")
            from handlers.participation import process_slot_booked
            await process_slot_booked(bot, contest, slot_number, user)
        else:
            await message.answer(f"❌ Слот #{slot_number} был занят. Возврат будет произведён Telegram.")
            try:
                await bot.refund_star_payment(user_id=user.id, telegram_payment_charge_id=payment.telegram_payment_charge_id)
            except Exception:
                pass

    elif payload.startswith("lottery_"):
        parts = payload.split("_")
        try:
            contest_id, quantity = int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            return
        await add_lottery_tickets(contest_id, user.id, user.username, full_name, quantity, "paid", payment.telegram_payment_charge_id)
        from db.database import get_total_tickets
        total = await get_total_tickets(contest_id)
        await message.answer(f"✅ Оплата прошла! <b>{quantity}</b> билет(ов) добавлено.\nВсего в пуле: {total}")
