import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# contest_id -> asyncio.Task
_tasks: dict[int, asyncio.Task] = {}


async def _finish_classic_at_time(bot, contest_id: int, run_at: datetime):
    """Ждёт до нужного времени, потом подводит итоги."""
    now = datetime.now()
    delay = (run_at - now).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)

    from db.database import get_contest, get_participants, finish_contest
    from utils.helpers import pick_winners, format_user_mention
    from handlers.participation import _post_winner_message

    contest = await get_contest(contest_id)
    if not contest or contest["status"] != "active":
        return

    participants = await get_participants(contest_id)
    if not participants:
        # Нет участников — просто закрываем
        await finish_contest(contest_id)
        try:
            if contest.get("message_id"):
                await bot.edit_message_reply_markup(
                    chat_id=contest["channel_id"],
                    message_id=contest["message_id"],
                    reply_markup=None
                )
            await bot.send_message(
                chat_id=contest["channel_id"],
                text=f"🔒 Розыгрыш #{contest_id} завершён. Участников не было."
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                chat_id=contest["admin_id"],
                text=f"🔒 Розыгрыш <b>#{contest_id}</b> завершён по времени.\nУчастников не было."
            )
        except Exception:
            pass
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
            text=f"🏆 Розыгрыш <b>#{contest_id}</b> завершён по времени!\n\n"
                 f"Победители:\n{winners_text}"
        )
    except Exception:
        pass

    _tasks.pop(contest_id, None)
    logger.info(f"Contest #{contest_id} finished by timer")


def schedule_contest(bot, contest_id: int, finish_dt: datetime):
    """Запланировать автозавершение конкурса."""
    cancel_contest(contest_id)
    task = asyncio.create_task(
        _finish_classic_at_time(bot, contest_id, finish_dt)
    )
    _tasks[contest_id] = task
    logger.info(f"Scheduled contest #{contest_id} finish at {finish_dt}")


def cancel_contest(contest_id: int):
    task = _tasks.pop(contest_id, None)
    if task:
        task.cancel()


async def restore_schedules(bot):
    """Восстановить таймеры после перезапуска бота."""
    from db.database import get_db
    import aiosqlite

    async with aiosqlite.connect(__import__('config').DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, finish_value FROM contests "
            "WHERE type='classic' AND status='active' AND finish_condition='time'"
        ) as cur:
            rows = await cur.fetchall()

    now = datetime.now()
    for row in rows:
        contest_id = row["id"]
        try:
            finish_dt = datetime.strptime(row["finish_value"], "%d.%m.%Y %H:%M")
            if finish_dt > now:
                schedule_contest(bot, contest_id, finish_dt)
                logger.info(f"Restored schedule for contest #{contest_id}")
            else:
                # Время уже прошло — запускаем немедленно
                schedule_contest(bot, contest_id, now)
        except Exception as e:
            logger.error(f"Failed to restore schedule for #{contest_id}: {e}")
