import random
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards import main_menu_kb, my_projects_kb, project_actions_kb
from db.database import (
    get_admin_contests, get_contest, get_participants, finish_contest,
    count_participants, get_booked_slots_count, get_total_tickets,
    count_battle_participants, get_all_tickets_pool
)
from utils.helpers import pick_winners, format_user_mention

router = Router()


@router.callback_query(F.data == "my_projects")
async def my_projects(call: CallbackQuery, state: FSMContext):
    await state.clear()
    contests = await get_admin_contests(call.from_user.id)
    if not contests:
        await call.message.edit_text("📋 Нет проектов. Создайте первый!", reply_markup=main_menu_kb())
        await call.answer()
        return
    await call.message.edit_text("📋 <b>Мои проекты:</b>", reply_markup=my_projects_kb(contests))
    await call.answer()


@router.callback_query(F.data.startswith("proj:"))
async def project_detail(call: CallbackQuery):
    contest_id = int(call.data.split(":")[1])
    contest = await get_contest(contest_id)
    if not contest or contest["admin_id"] != call.from_user.id:
        await call.answer("Не найдено.", show_alert=True)
        return

    icons = {"classic": "🎯", "slots": "🎰", "lottery": "🎟", "battle": "⚔️"}
    icon = icons.get(contest["type"], "📌")
    status_str = "✅ Активен" if contest["status"] == "active" else "🔒 Завершён"
    title = contest.get("title") or f"#{contest['id']}"
    t = contest["type"]

    if t == "classic":
        count = await count_participants(contest_id)
        cond = contest.get("finish_condition")
        extra = f"\n👥 Участников: <b>{count}</b>"
        if cond == "time":
            extra += f"\n⏰ До: {contest.get('finish_value')}"
        elif cond == "count":
            extra += f"\n🎯 Лимит: {contest.get('finish_value')}"
        extra += f"\n🏆 Победителей: {contest.get('winners_count', 1)}"
    elif t == "slots":
        booked = await get_booked_slots_count(contest_id)
        total = contest.get("total_slots", 0)
        pay = "бесплатно" if contest.get("payment_type") == "free" else f"{contest.get('slot_price')} ⭐"
        extra = f"\n🎰 Слотов: <b>{booked}/{total}</b>\n💰 {pay}\n🎯 Попыток: {contest.get('max_attempts',1)}"
    elif t == "lottery":
        total_tickets = await get_total_tickets(contest_id)
        pay = "бесплатно" if contest.get("payment_type") == "free" else f"{contest.get('slot_price')} ⭐/билет"
        extra = f"\n🎟 Билетов в пуле: <b>{total_tickets}</b>\n💰 {pay}\n🎯 Макс: {contest.get('max_attempts',1)}"
    else:  # battle
        count = await count_battle_participants(contest_id)
        rnd = contest.get("current_round", 0)
        extra = (
            f"\n👥 Участников: <b>{count}/{contest.get('participant_limit','?')}</b>"
            f"\n⚔️ Текущий раунд: {rnd if rnd > 0 else 'набор'}"
        )

    text = f"{icon} <b>{title}</b>\n\n📌 Тип: {t}\n📊 Статус: {status_str}{extra}"
    await call.message.edit_text(text, reply_markup=project_actions_kb(contest))
    await call.answer()


@router.callback_query(F.data.startswith("draw:"))
async def draw_winners(call: CallbackQuery, bot: Bot):
    contest_id = int(call.data.split(":")[1])
    contest = await get_contest(contest_id)
    if not contest or contest["admin_id"] != call.from_user.id:
        await call.answer("Нет доступа.", show_alert=True)
        return
    if contest["status"] != "active":
        await call.answer("Уже завершён.", show_alert=True)
        return

    t = contest["type"]
    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")

    if message_id:
        try:
            await bot.edit_message_reply_markup(chat_id=channel_id, message_id=message_id, reply_markup=None)
        except Exception:
            pass

    if t == "classic":
        participants = await get_participants(contest_id)
        if not participants:
            await call.answer("Нет участников.", show_alert=True)
            return
        winners = pick_winners(participants, contest.get("winners_count", 1))
        winners_text = "\n".join(
            f"{i+1}. {format_user_mention(w.get('username'), w.get('full_name',''), w['user_id'])}"
            for i, w in enumerate(winners)
        )
        await bot.send_message(
            chat_id=channel_id,
            text=f"🏆 <b>Итоги розыгрыша #{contest_id}!</b>\n\nПобедители:\n{winners_text}\n\n🎉"
        )
        for w in winners:
            try:
                await bot.send_message(chat_id=w["user_id"], text=f"🎉 Вы победили в розыгрыше <b>#{contest_id}</b>!")
            except Exception:
                pass

    elif t == "lottery":
        pool = await get_all_tickets_pool(contest_id)
        if not pool:
            await call.answer("Нет билетов.", show_alert=True)
            return
        winner_ticket = random.choice(pool)
        mention = format_user_mention(winner_ticket.get("username"), winner_ticket.get("full_name","?"), winner_ticket["user_id"])
        await bot.send_message(
            chat_id=channel_id,
            text=f"🎟 <b>Итоги лотереи #{contest_id}!</b>\n\nПобедитель: {mention} 🎉\n\nПоздравляем!"
        )
        try:
            await bot.send_message(chat_id=winner_ticket["user_id"], text=f"🎉 Вы победили в лотерее <b>#{contest_id}</b>!")
        except Exception:
            pass

    await finish_contest(contest_id)
    await call.message.edit_text(f"🏆 Итоги подведены для проекта <b>#{contest_id}</b>!", reply_markup=main_menu_kb())
    await call.answer("Готово!")


@router.callback_query(F.data.startswith("close:"))
async def close_contest(call: CallbackQuery, bot: Bot):
    contest_id = int(call.data.split(":")[1])
    contest = await get_contest(contest_id)
    if not contest or contest["admin_id"] != call.from_user.id:
        await call.answer("Нет доступа.", show_alert=True)
        return

    await finish_contest(contest_id)
    if contest.get("message_id"):
        try:
            await bot.edit_message_reply_markup(chat_id=contest["channel_id"], message_id=contest["message_id"], reply_markup=None)
        except Exception:
            pass

    await call.message.edit_text(f"🔒 Проект <b>#{contest_id}</b> закрыт.", reply_markup=main_menu_kb())
    await call.answer("Закрыто")
