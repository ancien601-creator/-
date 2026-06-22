import asyncio
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

_tasks: dict[int, asyncio.Task] = {}


def _task_done_callback(task: asyncio.Task, contest_id: int):
    """Логирует если таск упал с исключением."""
    if task.cancelled():
        logger.info(f"Contest #{contest_id}: task was cancelled")
        return
    exc = task.exception()
    if exc:
        logger.error(
            f"Contest #{contest_id}: task CRASHED with {type(exc).__name__}: {exc}\n"
            + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        )
    else:
        logger.info(f"Contest #{contest_id}: task completed successfully")


async def _run_finish(bot, contest_id: int, finish_dt: datetime):
    now = datetime.now()
    delay = (finish_dt - now).total_seconds()
    logger.info(f"Contest #{contest_id}: scheduled, delay={delay:.0f}s, fires at {finish_dt}")

    if delay > 0:
        await asyncio.sleep(delay)

    logger.info(f"Contest #{contest_id}: timer fired!")
    await _do_finish(bot, contest_id)
    _tasks.pop(contest_id, None)


async def _do_finish(bot, contest_id: int):
    import random
    import aiosqlite
    from config import DB_PATH

    logger.info(f"Contest #{contest_id}: _do_finish started")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,)) as cur:
            row = await cur.fetchone()

        if not row:
            logger.warning(f"Contest #{contest_id}: not found in DB")
            return

        contest = dict(row)
        logger.info(f"Contest #{contest_id}: status={contest['status']}")

        if contest["status"] != "active":
            logger.info(f"Contest #{contest_id}: already finished, skipping")
            return

        async with db.execute(
            "SELECT * FROM participants WHERE contest_id = ?", (contest_id,)
        ) as cur:
            participants = [dict(r) for r in await cur.fetchall()]

        logger.info(f"Contest #{contest_id}: {len(participants)} participants")

        await db.execute(
            "UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,)
        )
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
            logger.info(f"Contest #{contest_id}: removed buttons from post")
        except Exception as e:
            logger.warning(f"Contest #{contest_id}: could not remove buttons: {e}")

    if not participants:
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

    winners_count = min(contest.get("winners_count") or 1, len(participants))
    winners = random.sample(participants, winners_count)

    def mention(w):
        if w.get("username"):
            return f"@{w['username']}"
        return f"<a href=\"tg://user?id={w['user_id']}\">{w.get('full_name', 'Участник')}</a>"

    winners_text = "\n".join(f"{i+1}. {mention(w)}" for i, w in enumerate(winners))

    result_msg = (
        f"🏆 <b>Итоги розыгрыша #{contest_id}!</b>\n\n"
        f"Победител{'и' if len(winners) > 1 else 'ь'}:\n{winners_text}\n\n"
        f"Поздравляем! 🎉"
    )

    await bot.send_message(chat_id=channel_id, text=result_msg)
    logger.info(f"Contest #{contest_id}: results posted to channel")

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
            chat_id=admin_id,
            text=f"🏆 Розыгрыш <b>#{contest_id}</b> завершён по времени!\n\n"
                 f"Победители:\n{winners_text}"
        )
    except Exception:
        pass

    logger.info(f"Contest #{contest_id}: _do_finish done")


def schedule_contest(bot, contest_id: int, finish_dt: datetime):
    cancel_contest(contest_id)
    task = asyncio.create_task(_run_finish(bot, contest_id, finish_dt))
    task.add_done_callback(lambda t: _task_done_callback(t, contest_id))
    _tasks[contest_id] = task
    logger.info(f"Contest #{contest_id}: task created, fires at {finish_dt}")


def cancel_contest(contest_id: int):
    task = _tasks.pop(contest_id, None)
    if task and not task.done():
        task.cancel()


async def restore_schedules(bot):
    import aiosqlite
    from config import DB_PATH

    now = datetime.now()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, finish_value FROM contests "
            "WHERE type='classic' AND status='active' AND finish_condition='time'"
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        logger.info("restore_schedules: no active timed contests")
        return

    now = datetime.now()
    for row in rows:
        contest_id = row["id"]
        try:
            finish_dt = datetime.strptime(row["finish_value"], "%d.%m.%Y %H:%M")
            if finish_dt > now:
                schedule_contest(bot, contest_id, finish_dt)
            else:
                logger.info(f"Contest #{contest_id}: overdue by {(now - finish_dt).seconds}s, finishing now")
                task = asyncio.create_task(_do_finish(bot, contest_id))
                task.add_done_callback(lambda t: _task_done_callback(t, contest_id))
        except Exception as e:
            logger.error(f"restore_schedules: contest #{contest_id}: {e}")

    logger.info(f"restore_schedules: processed {len(rows)} contests")
