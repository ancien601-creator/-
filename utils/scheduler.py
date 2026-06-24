import asyncio
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

# contest_id -> asyncio.Task
_tasks: dict[int, asyncio.Task] = {}
# battle round tasks: (contest_id, round) -> Task
_battle_tasks: dict[tuple, asyncio.Task] = {}


# ──────────────────────── CLASSIC TIMED CONTEST ────────────────────────

def _done_callback(task: asyncio.Task, label: str):
    if task.cancelled():
        logger.info(f"[scheduler] {label}: task cancelled")
        return
    exc = task.exception()
    if exc:
        logger.error(
            f"[scheduler] {label}: CRASHED — {type(exc).__name__}: {exc}\n"
            + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        )
    else:
        logger.info(f"[scheduler] {label}: completed ok")


async def _run_classic(bot, contest_id: int, finish_dt: datetime):
    now = datetime.now()
    delay = (finish_dt - now).total_seconds()
    logger.info(f"[scheduler] contest #{contest_id}: sleeping {delay:.0f}s until {finish_dt}")
    if delay > 0:
        await asyncio.sleep(delay)
    logger.info(f"[scheduler] contest #{contest_id}: timer fired, finishing")
    await _finish_classic(bot, contest_id)
    _tasks.pop(contest_id, None)


async def _finish_classic(bot, contest_id: int):
    import random
    import aiosqlite
    from config import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM contests WHERE id=?", (contest_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            logger.warning(f"[scheduler] contest #{contest_id}: not found in DB")
            return
        contest = dict(row)
        if contest["status"] != "active":
            logger.info(f"[scheduler] contest #{contest_id}: already finished")
            return
        async with db.execute("SELECT * FROM participants WHERE contest_id=?", (contest_id,)) as cur:
            participants = [dict(r) for r in await cur.fetchall()]
        await db.execute("UPDATE contests SET status='finished' WHERE id=?", (contest_id,))
        await db.commit()

    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")
    admin_id = contest["admin_id"]

    # Убрать кнопки со старого поста
    if message_id:
        try:
            await bot.edit_message_reply_markup(chat_id=channel_id, message_id=message_id, reply_markup=None)
        except Exception as e:
            logger.warning(f"[scheduler] remove buttons: {e}")

    if not participants:
        await bot.send_message(chat_id=channel_id, text=f"🔒 Розыгрыш #{contest_id} завершён. Участников не было.")
        try:
            await bot.send_message(chat_id=admin_id, text=f"🔒 Розыгрыш <b>#{contest_id}</b> завершён по времени.\nУчастников не было.")
        except Exception:
            pass
        return

    winners_count = min(contest.get("winners_count") or 1, len(participants))
    winners = random.sample(participants, winners_count)

    def mention(w):
        return f"@{w['username']}" if w.get("username") else f"<a href=\"tg://user?id={w['user_id']}\">{w.get('full_name','Участник')}</a>"

    winners_text = "\n".join(f"{i+1}. {mention(w)}" for i, w in enumerate(winners))

    await bot.send_message(
        chat_id=channel_id,
        text=f"🏆 <b>Итоги розыгрыша #{contest_id}!</b>\n\nПобедител{'и' if len(winners)>1 else 'ь'}:\n{winners_text}\n\n🎉"
    )
    logger.info(f"[scheduler] contest #{contest_id}: results posted")

    for w in winners:
        try:
            await bot.send_message(chat_id=w["user_id"], text=f"🎉 Поздравляем! Вы победили в розыгрыше <b>#{contest_id}</b>!\nС вами свяжется организатор.")
        except Exception:
            pass
    try:
        await bot.send_message(chat_id=admin_id, text=f"🏆 Розыгрыш <b>#{contest_id}</b> завершён по времени!\n\nПобедители:\n{winners_text}")
    except Exception:
        pass


def schedule_contest(bot, contest_id: int, finish_dt: datetime):
    cancel_contest(contest_id)
    task = asyncio.create_task(_run_classic(bot, contest_id, finish_dt))
    task.add_done_callback(lambda t: _done_callback(t, f"classic#{contest_id}"))
    _tasks[contest_id] = task
    logger.info(f"[scheduler] contest #{contest_id}: task created, fires at {finish_dt}")


def cancel_contest(contest_id: int):
    task = _tasks.pop(contest_id, None)
    if task and not task.done():
        task.cancel()


# ──────────────────────── BATTLE ROUND SCHEDULER ────────────────────────

async def _run_battle_round(bot, contest_id: int, round_num: int, minutes: int):
    logger.info(f"[scheduler] battle #{contest_id} round {round_num}: sleeping {minutes}min")
    await asyncio.sleep(minutes * 60)
    logger.info(f"[scheduler] battle #{contest_id} round {round_num}: timer fired")
    from handlers.battle import finish_battle_round
    await finish_battle_round(bot, contest_id, round_num)
    _battle_tasks.pop((contest_id, round_num), None)


def schedule_battle_round(bot, contest_id: int, round_num: int, minutes: int):
    key = (contest_id, round_num)
    old = _battle_tasks.pop(key, None)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(_run_battle_round(bot, contest_id, round_num, minutes))
    task.add_done_callback(lambda t: _done_callback(t, f"battle#{contest_id}_r{round_num}"))
    _battle_tasks[key] = task
    logger.info(f"[scheduler] battle #{contest_id} round {round_num}: task created ({minutes}min)")


# ──────────────────────── RESTORE ON RESTART ────────────────────────

async def restore_schedules(bot):
    """Восстанавливает таймеры после перезапуска бота."""
    import aiosqlite
    from config import DB_PATH

    now = datetime.now()
    restored = 0

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, finish_value FROM contests WHERE type='classic' AND status='active' AND finish_condition='time'"
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    for row in rows:
        cid = row["id"]
        try:
            finish_dt = datetime.strptime(row["finish_value"], "%d.%m.%Y %H:%M")
            if finish_dt > now:
                schedule_contest(bot, cid, finish_dt)
            else:
                logger.info(f"[scheduler] contest #{cid}: overdue, finishing immediately")
                t = asyncio.create_task(_finish_classic(bot, cid))
                t.add_done_callback(lambda t: _done_callback(t, f"classic#{cid}_overdue"))
            restored += 1
        except Exception as e:
            logger.error(f"[scheduler] restore contest #{cid}: {e}")

    logger.info(f"[scheduler] restore_schedules: {restored} contests")


# ──────────────────────── BACKGROUND SAFETY NET ────────────────────────

async def background_checker(bot):
    """Каждые 60 сек проверяет просроченные конкурсы — подстраховка на случай потери task."""
    import aiosqlite
    from config import DB_PATH

    logger.info("[scheduler] background_checker started")
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now()
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, finish_value FROM contests WHERE type='classic' AND status='active' AND finish_condition='time'"
                ) as cur:
                    rows = [dict(r) for r in await cur.fetchall()]

            for row in rows:
                cid = row["id"]
                if cid in _tasks:
                    continue  # уже есть активный task
                try:
                    finish_dt = datetime.strptime(row["finish_value"], "%d.%m.%Y %H:%M")
                    if finish_dt <= now:
                        logger.info(f"[bg_checker] contest #{cid}: overdue and no task! finishing")
                        t = asyncio.create_task(_finish_classic(bot, cid))
                        t.add_done_callback(lambda t: _done_callback(t, f"classic#{cid}_bg"))
                    else:
                        # Task потерялся — пересоздаём
                        logger.warning(f"[bg_checker] contest #{cid}: task missing, rescheduling")
                        schedule_contest(bot, cid, finish_dt)
                except Exception as e:
                    logger.error(f"[bg_checker] contest #{cid}: {e}")
        except Exception as e:
            logger.error(f"[bg_checker] error: {e}")
