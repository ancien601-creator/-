import json
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.filters import CommandObject, CommandStart
from aiogram.utils.deep_linking import decode_payload
from db import (get_contest, add_participant, get_participants_count,
                reserve_slot, get_slot_owner, get_occupied_slots, update_contest,
                add_user)
from keyboards import subscription_check, slot_buttons
from utils import check_subscriptions, update_post_message, generate_contest_post
from datetime import datetime

router = Router()

# Обработка deep link
@router.message(CommandStart(deep_link=True))
async def deep_link_handler(message: Message, bot: Bot, command: CommandObject):
    args = command.args
    if not args:
        return
    if args.startswith("contest_"):
        contest_id = int(args.split("_")[1])
        await handle_classic_join(message, bot, contest_id)
    elif args.startswith("slot_"):
        _, contest_id_str, slot_str = args.split("_")
        contest_id = int(contest_id_str)
        slot_num = int(slot_str)
        await handle_slot_click(message, bot, contest_id, slot_num)

async def handle_classic_join(message: Message, bot: Bot, contest_id: int):
    user = message.from_user
    await add_user(user.id, user.username)
    contest = await get_contest(contest_id)
    if not contest or contest['status'] != 'active':
        await message.answer("Розыгрыш не найден или завершён.")
        return
    # Каналы для проверки: основной + спонсоры
    main_channel = await bot.get_chat(contest['channel_id'])
    main_username = f"@{main_channel.username}" if main_channel.username else None
    sponsors = json.loads(contest['sponsor_channels'])
    all_channels = [main_username] + [f"@{sp}" for sp in sponsors] if main_username else [f"@{sp}" for sp in sponsors]
    all_channels = [ch for ch in all_channels if ch]  # убираем None
    
    if not await check_subscriptions(bot, user.id, all_channels):
        await message.answer(
            "⚠️ Вы не подписаны на обязательные каналы. Подпишитесь и нажмите «Проверить».",
            reply_markup=subscription_check(all_channels)
        )
        return
    success = await add_participant(contest_id, user.id)
    if success:
        await message.answer("✅ Вы участвуете!")
        # Автофиниш по количеству
        if contest['end_condition'] == 'participants':
            current = await get_participants_count(contest_id)
            if current >= int(contest['end_value']):
                await finish_classic_auto(bot, contest_id)
    else:
        await message.answer("Вы уже участвуете.")

async def finish_classic_auto(bot: Bot, contest_id: int):
    from handlers.admin import finish_contest  # упростим: вызываем логику финиша
    # Создаём фейковый callback не можем, поэтому дублируем код
    contest = await get_contest(contest_id)
    if not contest or contest['status'] != 'active': return
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

async def handle_slot_click(message: Message, bot: Bot, contest_id: int, slot_num: int):
    user = message.from_user
    await add_user(user.id, user.username)
    contest = await get_contest(contest_id)
    if not contest or contest['status'] != 'active':
        await message.answer("Лотерея не активна.")
        return
    if await get_slot_owner(contest_id, slot_num):
        await message.answer("Слот уже занят.")
        return
    # Подписки
    main_channel = await bot.get_chat(contest['channel_id'])
    main_username = f"@{main_channel.username}" if main_channel.username else None
    sponsors = json.loads(contest['sponsor_channels'])
    all_channels = [main_username] + [f"@{sp}" for sp in sponsors] if main_username else [f"@{sp}" for sp in sponsors]
    all_channels = [ch for ch in all_channels if ch]
    if not await check_subscriptions(bot, user.id, all_channels):
        await message.answer(
            "⚠️ Подпишитесь на каналы.",
            reply_markup=subscription_check(all_channels)
        )
        return

    if contest['payment_required']:
        price = contest['slot_price']  # копейки
        await bot.send_invoice(
            chat_id=user.id,
            title=f"Слот №{slot_num}",
            description=f"Бронирование слота №{slot_num} в лотерее",
            payload=f"slot_{contest_id}_{slot_num}",
            provider_token="",  # тестовый режим (или укажите токен)
            currency="RUB",
            prices=[LabeledPrice(label="Слот", amount=price)],
            start_parameter=f"slot_{contest_id}_{slot_num}",
            need_name=False,
            need_phone_number=False,
            is_flexible=False
        )
    else:
        await reserve_and_check(bot, contest, user.id, slot_num, message)

async def reserve_and_check(bot: Bot, contest: dict, user_id: int, slot_num: int, message: Message = None):
    success = await reserve_slot(contest['id'], slot_num, user_id)
    if not success:
        if message:
            await message.answer("Слот только что заняли.")
        return
    # Обновить кнопки в канале
    occupied = await get_occupied_slots(contest['id'])
   # было: kb = slot_buttons(contest['id'], contest['slots_count'], occupied)
# стало:
    me = await bot.get_me()
    kb = slot_url_buttons(contest['id'], contest['slots_count'], occupied, me.username)
    await update_post_message(bot, contest, reply_markup=kb)

    # Проверка победы
    if slot_num == contest['winning_slot']:
        creator_id = contest['created_by']
        winner = await bot.get_chat(user_id)
        winner_name = f"@{winner.username}" if winner.username else winner.first_name
        await bot.send_message(
            creator_id,
            f"🚨 Победитель! {winner_name} выбрал слот №{slot_num} в проекте «{contest['title']}»."
        )
        await bot.send_message(user_id, "🎉 Поздравляем! Ваш слот выигрышный! Создатель свяжется с вами.")
        new_text = generate_contest_post(contest) + f"\n\n🎉 Лотерея окончена! Выигрышный слот №{slot_num}. Победитель: {winner_name}"
        await update_post_message(bot, contest, new_text=new_text, reply_markup=None)
        await update_contest(contest['id'], status='finished', finished_at=datetime.now())
    else:
        if message:
            await message.answer(f"✅ Слот №{slot_num} забронирован! Ожидайте.")

# Платежи
@router.pre_checkout_query()
async def pre_checkout(pre_checkout: PreCheckoutQuery, bot: Bot):
    payload = pre_checkout.invoice_payload
    if payload.startswith("slot_"):
        _, contest_id_str, slot_str = payload.split("_")
        contest_id = int(contest_id_str)
        slot_num = int(slot_str)
        contest = await get_contest(contest_id)
        if not contest or contest['status'] != 'active':
            await pre_checkout.answer(ok=False, error_message="Лотерея завершена.")
            return
        if await get_slot_owner(contest_id, slot_num):
            await pre_checkout.answer(ok=False, error_message="Слот занят.")
            return
        await pre_checkout.answer(ok=True)
    else:
        await pre_checkout.answer(ok=False, error_message="Неизвестный платёж.")

@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    payload = message.successful_payment.invoice_payload
    _, contest_id_str, slot_str = payload.split("_")
    contest_id = int(contest_id_str)
    slot_num = int(slot_str)
    contest = await get_contest(contest_id)
    if not contest:
        await message.answer("Проект не найден.")
        return
    await reserve_and_check(bot, contest, message.from_user.id, slot_num, message)

# Проверка подписки (при нажатии "Проверить")
@router.callback_query(F.data == "check_sub")
async def check_sub_again(callback: CallbackQuery, bot: Bot):
    await callback.answer("Перезапустите бота командой /start для перепроверки.", show_alert=True)
