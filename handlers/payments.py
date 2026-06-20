from aiogram import Router, F, Bot
from aiogram.types import Message, PreCheckoutQuery

from db.database import get_contest, get_slot, book_slot, set_slot_paid
from handlers.participation import process_slot_booked

router = Router()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    payload = pre_checkout_query.invoice_payload

    # Validate payload format: slot_<contest_id>_<slot_number>
    if not payload.startswith("slot_"):
        await pre_checkout_query.answer(ok=False, error_message="Неверный платёж.")
        return

    parts = payload.split("_")
    if len(parts) < 3:
        await pre_checkout_query.answer(ok=False, error_message="Неверный формат.")
        return

    try:
        contest_id = int(parts[1])
        slot_number = int(parts[2])
    except ValueError:
        await pre_checkout_query.answer(ok=False, error_message="Неверные данные.")
        return

    contest = await get_contest(contest_id)
    if not contest or contest["status"] != "active":
        await pre_checkout_query.answer(ok=False, error_message="Лотерея не найдена или завершена.")
        return

    existing = await get_slot(contest_id, slot_number)
    if existing and existing.get("user_id") and existing["user_id"] != pre_checkout_query.from_user.id:
        await pre_checkout_query.answer(ok=False, error_message=f"Слот #{slot_number} уже занят.")
        return

    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    payment = message.successful_payment
    payload = payment.invoice_payload

    parts = payload.split("_")
    if len(parts) < 3:
        return

    try:
        contest_id = int(parts[1])
        slot_number = int(parts[2])
    except ValueError:
        return

    contest = await get_contest(contest_id)
    if not contest:
        await message.answer("❌ Лотерея не найдена. Обратитесь к организатору.")
        return

    user = message.from_user
    full_name = f"{user.first_name} {user.last_name or ''}".strip()

    booked = await book_slot(
        contest_id, slot_number, user.id,
        user.username, full_name, "paid"
    )

    if booked:
        await set_slot_paid(contest_id, slot_number, payment.telegram_payment_charge_id)
        await message.answer(f"✅ Оплата прошла успешно! Слот <b>#{slot_number}</b> забронирован.")
        await process_slot_booked(bot, contest, slot_number, user)
    else:
        # Slot was taken between pre_checkout and payment — need to refund
        await message.answer(
            f"❌ К сожалению, слот #{slot_number} был занят другим участником.\n\n"
            f"Возврат средств будет произведён автоматически Telegram.\n"
            f"Попробуйте выбрать другой слот."
        )
        # Attempt refund
        try:
            await bot.refund_star_payment(
                user_id=user.id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id
            )
        except Exception:
            pass
