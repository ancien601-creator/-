from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards import main_menu_kb, my_projects_kb, project_actions_kb
from db.database import (
    get_admin_contests, get_contest, get_participants,
    finish_contest, count_participants, get_booked_slots_count
)
from utils.helpers import pick_winners, format_user_mention

router = Router()


@router.callback_query(F.data == "my_projects")
async def my_projects(call: CallbackQuery, state: FSMContext):
    await state.clear()
    contests = await get_admin_contests(call.from_user.id)
    if not contests:
        await call.message.edit_text(
            "📋 У вас пока нет проектов.\n\nСоздайте первый через «Создать проект».",
            reply_markup=main_menu_kb()
        )
        await call.answer()
        return

    await call.message.edit_text("📋 <b>Мои проекты:</b>", reply_markup=my_projects_kb(contests))
    await call.answer()


@router.callback_query(F.data.startswith("proj:"))
async def project_detail(call: CallbackQuery):
    contest_id = int(call.data.split(":")[1])
    contest = await get_contest(contest_id)
    if not contest or contest["admin_id"] != call.from_user.id:
        await call.answer("Проект не найден.", show_alert=True)
        return

    icon = "🎯" if contest["type"] == "classic" else "🎰"
    status_str = "✅ Активен" if contest["status"] == "active" else "🔒 Завершён"
    type_str = "Классический розыгрыш" if contest["type"] == "classic" else "Лотерея по слотам"
    title = contest.get("title") or f"#{contest['id']}"

    if contest["type"] == "classic":
        count = await count_participants(contest_id)
        cond = contest.get("finish_condition")
        extra = f"\n👥 Участников: <b>{count}</b>"
        if cond == "time":
            extra += f"\n⏰ Завершение: {contest.get('finish_value')}"
        elif cond == "count":
            extra += f"\n🎯 Лимит: {contest.get('finish_value')}"
        extra += f"\n🏆 Победителей: {contest.get('winners_count', 1)}"
        extra += f"\n👁 Счётчик на кнопке: {'да' if contest.get('show_count') else 'нет'}"
    else:
        booked = await get_booked_slots_count(contest_id)
        total = contest.get("total_slots", 0)
        pay = "бесплатные" if contest.get("payment_type") == "free" else f"{contest.get('slot_price')} ⭐"
        max_att = contest.get("max_attempts") or 1
        extra = (
            f"\n🎰 Слотов: <b>{booked}/{total}</b> занято"
            f"\n🎯 Попыток на участника: <b>{max_att}</b>"
            f"\n💰 Участие: {pay}"
        )

    text = (
        f"{icon} <b>{title}</b>\n\n"
        f"📌 Тип: {type_str}\n"
        f"📊 Статус: {status_str}"
        f"{extra}"
    )
    await call.message.edit_text(text, reply_markup=project_actions_kb(contest))
    await call.answer()


# ──────────────────────── DRAW WINNERS ────────────────────────

@router.callback_query(F.data.startswith("draw:"))
async def draw_winners(call: CallbackQuery, bot: Bot):
    contest_id = int(call.data.split(":")[1])
    contest = await get_contest(contest_id)
    if not contest or contest["admin_id"] != call.from_user.id:
        await call.answer("Нет доступа.", show_alert=True)
        return
    if contest["status"] != "active":
        await call.answer("Розыгрыш уже завершён.", show_alert=True)
        return

    participants = await get_participants(contest_id)
    if not participants:
        await call.answer("Нет участников.", show_alert=True)
        return

    winners = pick_winners(participants, contest.get("winners_count", 1))
    winners_text = "\n".join(
        f"{i+1}. {format_user_mention(w.get('username'), w.get('full_name', ''), w['user_id'])}"
        for i, w in enumerate(winners)
    )

    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")

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

    # Новый пост с победителями
    await bot.send_message(
        chat_id=channel_id,
        text=(
            f"🏆 <b>Итоги розыгрыша #{contest_id}!</b>\n\n"
            f"Победител{'и' if len(winners) > 1 else 'ь'}:\n{winners_text}\n\n"
            f"Поздравляем! 🎉"
        )
    )

    await finish_contest(contest_id)

    # Уведомить победителей
    for w in winners:
        try:
            await bot.send_message(
                chat_id=w["user_id"],
                text=f"🎉 Поздравляем! Вы победили в розыгрыше <b>#{contest_id}</b>!\n"
                     f"С вами свяжется организатор."
            )
        except Exception:
            pass

    await call.message.edit_text(
        f"🏆 Итоги подведены!\n\nПобедители:\n{winners_text}",
        reply_markup=main_menu_kb()
    )
    await call.answer("Готово!")


# ──────────────────────── CLOSE ────────────────────────

@router.callback_query(F.data.startswith("close:"))
async def close_contest(call: CallbackQuery, bot: Bot):
    contest_id = int(call.data.split(":")[1])
    contest = await get_contest(contest_id)
    if not contest or contest["admin_id"] != call.from_user.id:
        await call.answer("Нет доступа.", show_alert=True)
        return

    await finish_contest(contest_id)

    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")
    if message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=None
            )
        except Exception:
            pass

    await call.message.edit_text(
        f"🔒 Проект <b>#{contest_id}</b> закрыт.",
        reply_markup=main_menu_kb()
    )
    await call.answer("Закрыто")
