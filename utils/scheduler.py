import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_tasks: dict[int, asyncio.Task] = {}


async def _run_finish(bot, contest_id: int, finish_dt: datetime):
    now = datetime.now()
    delay = (finish_dt - now).total_seconds()
    logger.info(f"Contest #{contest_id}: will finish in {delay:.0f}s")

    if delay > 0:
        await asyncio.sleep(delay)

    logger.info(f"Contest #{contest_id}: timer fired, finishing now")
    await _do_finish(bot, contest_id)
    _tasks.pop(contest_id, None)


async def _do_finish(bot, contest_id: int):
    # Импорты здесь — избегаем цикличности
    import random
    import aiosqlite
    from config import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Получить конкурс
        async with db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            logger.warning(f"Contest #{contest_id} not found")
            return
        contest = dict(row)

        if contest["status"] != "active":
            logger.info(f"Contest #{contest_id} already finished")
            return

        # Получить участников
        async with db.execute(
            "SELECT * FROM participants WHERE contest_id = ?", (contest_id,)
        ) as cur:
            participants = [dict(r) for r in await cur.fetchall()]

        # Закрыть конкурс
        await db.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
        await db.commit()

    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")
    admin_id = contest["admin_id"]

    # Убрать кнопки со старого поста
    if message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=None
            )
        except Exception as e:
            logger.warning(f"Could not remove buttons: {e}")

    if not participants:
        logger.info(f"Contest #{contest_id}: no participants")
        await bot.send_message(
            chat_id=channel_id,
            text=f"🔒 Розыгрыш #{contest_id} завершён. Участников не было."
        )
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"🔒 Розыгрыш <b>#{contest_id}</b> завершён по времени.\nУчастников не было."
            )
        except Exception:
            pass
        return

    # Выбрать победителей
    winners_count = min(contest.get("winners_count") or 1, len(participants))
    winners = random.sample(participants, winners_count)

    def mention(w):
        if w.get("username"):
            return f"@{w['username']}"
        return f"<a href=\"tg://user?id={w['user_id']}\">{w.get('full_name', 'Участник')}</a>"

    winners_text = "\n".join(
        f"{i+1}. {mention(w)}" for i, w in enumerate(winners)
    )

    result_msg = (
        f"🏆 <b>Итоги розыгрыша #{contest_id}!</b>\n\n"
        f"Победител{'и' if len(winners) > 1 else 'ь'}:\n{winners_text}\n\n"
        f"Поздравляем! 🎉"
    )

    # Новый пост с результатами
    await bot.send_message(chat_id=channel_id, text=result_msg)
    logger.info(f"Contest #{contest_id}: posted results to channel")

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

    # Уведомить админа
    try:
        await bot.send_message(
            chat_id=admin_id,
            text=f"🏆 Розыгрыш <b>#{contest_id}</b> завершён по времени!\n\n"
                 f"Победители:\n{winners_text}"
        )
    except Exception:
        pass


def schedule_contest(bot, contest_id: int, finish_dt: datetime):
    cancel_contest(contest_id)
    task = asyncio.create_task(_run_finish(bot, contest_id, finish_dt))
    _tasks[contest_id] = task
    logger.info(f"Scheduled contest #{contest_id} at {finish_dt} (task created)")


def cancel_contest(contest_id: int):
    task = _tasks.pop(contest_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"Cancelled schedule for contest #{contest_id}")


async def restore_schedules(bot):
    import aiosqlite
    from config import DB_PATH

    now = datetime.now()
    restored = 0

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, finish_value FROM contests "
            "WHERE type='classic' AND status='active' AND finish_condition='time'"
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    for row in rows:
        contest_id = row["id"]
        try:
            finish_dt = datetime.strptime(row["finish_value"], "%d.%m.%Y %H:%M")
            if finish_dt > now:
                schedule_contest(bot, contest_id, finish_dt)
            else:
                # Время прошло пока бот был выключен — финишируем немедленно
                logger.info(f"Contest #{contest_id} overdue, finishing immediately")
                asyncio.create_task(_do_finish(bot, contest_id))
            restored += 1
        except Exception as e:
            logger.error(f"restore_schedules: contest #{contest_id} error: {e}")

    logger.info(f"Restored {restored} scheduled contests")
