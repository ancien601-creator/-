import random
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards import (
    main_menu_kb, channels_list_kb, confirm_kb, skip_kb,
    battle_join_kb, battle_vote_kb, battle_final_kb
)
from db.database import (
    get_admin_channels, create_contest, set_contest_message_id, add_sponsor,
    get_contest, finish_contest, set_contest_current_round,
    add_battle_participant, get_battle_participants, count_battle_participants,
    is_battle_participant, eliminate_battle_participant,
    add_battle_vote, get_vote_count,
    add_battle_message, get_battle_messages, delete_battle_messages_db
)
from utils.states import BattleContest
from utils.helpers import resolve_channel, check_user_subscription, format_user_mention
from utils.scheduler import schedule_battle_round

logger = logging.getLogger(__name__)

router = Router()


def ask_content_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="📝 Добавить текст / фото", callback_data="bat_content_yes")
    b.button(text="⏩ Без текста", callback_data="bat_content_no")
    b.adjust(1)
    return b.as_markup()


# ──────────────────────── FSM СОЗДАНИЯ ────────────────────────

@router.callback_query(F.data == "type_battle")
async def start_battle(call: CallbackQuery, state: FSMContext):
    channels = await get_admin_channels(call.from_user.id)
    if not channels:
        await call.message.edit_text("📡 Нет каналов. Добавьте через «Мои каналы».", reply_markup=main_menu_kb())
        await call.answer()
        return
    await state.set_state(BattleContest.select_channel)
    await call.message.edit_text("📢 Шаг 1/8: Выберите канал:", reply_markup=channels_list_kb(channels))
    await call.answer()


@router.callback_query(BattleContest.select_channel, F.data.startswith("ch:"))
async def battle_channel(call: CallbackQuery, state: FSMContext):
    cid = int(call.data.split(":")[1])
    channels = await get_admin_channels(call.from_user.id)
    ch = next((c for c in channels if c["channel_id"] == cid), None)
    if not ch:
        await call.answer("Канал не найден", show_alert=True)
        return
    await state.update_data(channel_id=cid, channel_title=ch.get("channel_title",""), channel_username=ch.get("channel_username",""))
    await state.set_state(BattleContest.ask_content)
    await call.message.edit_text(
        f"✅ Канал: <b>{ch.get('channel_title', cid)}</b>\n\n📝 Шаг 2/8: Добавить описание баттла?",
        reply_markup=ask_content_kb()
    )
    await call.answer()


@router.callback_query(BattleContest.ask_content, F.data == "bat_content_no")
async def battle_no_content(call: CallbackQuery, state: FSMContext):
    await state.update_data(text=None, photo_id=None, title="Битва юзернеймов")
    await state.set_state(BattleContest.enter_limit)
    await call.message.edit_text(
        "👥 Шаг 3/8: Введите количество мест (чётное число):\n\nПример: <code>8</code>, <code>16</code>, <code>32</code>"
    )
    await call.answer()


@router.callback_query(BattleContest.ask_content, F.data == "bat_content_yes")
async def battle_ask_content(call: CallbackQuery, state: FSMContext):
    await state.set_state(BattleContest.enter_content)
    await call.message.edit_text("📝 Введите описание баттла (можно с фото):")
    await call.answer()


@router.message(BattleContest.enter_content)
async def battle_enter_content(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    if not text and not photo_id:
        await message.answer("❌ Введите текст или фото.")
        return
    title = (text[:50] + "...") if len(text) > 50 else text
    await state.update_data(text=text, photo_id=photo_id, title=title)
    await state.set_state(BattleContest.enter_limit)
    await message.answer("👥 Шаг 3/8: Количество мест (чётное):\n\nПример: <code>8</code>, <code>16</code>")


@router.message(BattleContest.enter_limit)
async def battle_enter_limit(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 2:
        await message.answer("❌ Введите целое число от 2 и выше.")
        return
    n = int(val)
    if n % 2 != 0:
        await message.answer(f"❌ Число должно быть чётным! Например: <code>{n+1}</code> или <code>{n-1}</code>")
        return
    await state.update_data(participant_limit=n)
    await state.set_state(BattleContest.enter_round1_time)
    await message.answer("⏱ Шаг 4/8: Длительность Раунда 1 (в минутах):\n\nПример: <code>60</code>")


@router.message(BattleContest.enter_round1_time)
async def battle_round1_time(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите количество минут.")
        return
    await state.update_data(round1_minutes=int(val))
    await state.set_state(BattleContest.enter_round2_time)
    await message.answer("⏱ Шаг 5/8: Длительность Раунда 2 (в минутах):\n\nПример: <code>60</code>")


@router.message(BattleContest.enter_round2_time)
async def battle_round2_time(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите количество минут.")
        return
    await state.update_data(round2_minutes=int(val))
    await state.set_state(BattleContest.enter_round3_time)
    await message.answer("⏱ Шаг 6/8: Длительность Финала (в минутах):\n\nПример: <code>120</code>")


@router.message(BattleContest.enter_round3_time)
async def battle_round3_time(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите количество минут.")
        return
    await state.update_data(round3_minutes=int(val))
    await state.set_state(BattleContest.enter_sponsors)
    await message.answer("📡 Шаг 7/8: Введите @username спонсоров или пропустите:", reply_markup=skip_kb())


@router.callback_query(BattleContest.enter_sponsors, F.data == "skip")
async def battle_skip_sponsors(call: CallbackQuery, state: FSMContext):
    await state.update_data(sponsors=[])
    await state.set_state(BattleContest.confirm)
    await _show_battle_preview(call.message, state)
    await call.answer()


@router.message(BattleContest.enter_sponsors)
async def battle_sponsors(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip()
    usernames = [u.strip().lstrip("@") for u in raw.replace(",", " ").split() if u.strip()]
    valid, invalid = [], []
    for u in usernames:
        info = await resolve_channel(bot, f"@{u}")
        if info:
            valid.append({"username": u, "id": info["id"]})
        else:
            invalid.append(u)
    if invalid:
        await message.answer(f"⚠️ Не найдены: {', '.join('@'+u for u in invalid)}", reply_markup=skip_kb())
        return
    await state.update_data(sponsors=valid)
    await state.set_state(BattleContest.confirm)
    await _show_battle_preview(message, state)


async def _show_battle_preview(target, state: FSMContext):
    data = await state.get_data()
    sp = ", ".join(f"@{s['username']}" for s in data.get("sponsors", [])) or "нет"
    text = (
        f"📋 <b>Предпросмотр битвы юзернеймов:</b>\n\n"
        f"📢 Канал: <b>{data.get('channel_title')}</b>\n"
        f"👥 Мест: <b>{data.get('participant_limit')}</b>\n"
        f"⏱ Раунд 1: {data.get('round1_minutes')} мин\n"
        f"⏱ Раунд 2: {data.get('round2_minutes')} мин\n"
        f"⏱ Финал: {data.get('round3_minutes')} мин\n"
        f"📡 Спонсоры: {sp}"
    )
    kb = confirm_kb()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.edit_text(text, reply_markup=kb)


@router.callback_query(BattleContest.confirm, F.data == "cancel_creation")
async def battle_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.", reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(BattleContest.confirm, F.data == "confirm_publish")
async def battle_publish(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    contest_id = await create_contest({
        "admin_id": call.from_user.id,
        "type": "battle",
        "title": data.get("title", "Битва юзернеймов"),
        "text": data.get("text"),
        "photo_id": data.get("photo_id"),
        "channel_id": data["channel_id"],
        "channel_username": data.get("channel_username", ""),
        "participant_limit": data["participant_limit"],
        "round1_minutes": data["round1_minutes"],
        "round2_minutes": data["round2_minutes"],
        "round3_minutes": data["round3_minutes"],
    })

    for sp in data.get("sponsors", []):
        await add_sponsor(contest_id, sp["username"], sp.get("id"))

    me = await bot.get_me()
    limit = data["participant_limit"]
    kb = battle_join_kb(me.username, contest_id, limit)
    post_text = (data.get("text") or "") + (
        f"\n\n⚔️ <b>Битва Юзернеймов!</b>\n"
        f"Набор открыт. Мест осталось: <b>{limit}</b>\n"
        f"Нажмите кнопку, чтобы подать заявку!"
    )

    if data.get("photo_id"):
        msg = await bot.send_photo(chat_id=data["channel_id"], photo=data["photo_id"], caption=post_text, reply_markup=kb)
    else:
        msg = await bot.send_message(chat_id=data["channel_id"], text=post_text, reply_markup=kb)

    await set_contest_message_id(contest_id, msg.message_id)
    await call.message.edit_text(f"⚔️ Битва <b>#{contest_id}</b> опубликована! Ожидайте участников.", reply_markup=main_menu_kb())
    await call.answer("Опубликовано!")


# ──────────────────────── ВСТУПЛЕНИЕ В БАТТЛ ────────────────────────

async def join_battle(message: Message, bot: Bot, contest_id: int):
    contest = await get_contest(contest_id)
    if not contest or contest["type"] != "battle":
        await message.answer("❌ Баттл не найден.")
        return
    if contest["status"] != "active":
        await message.answer("🔒 Набор в этот баттл уже закрыт.")
        return
    if contest.get("current_round", 0) > 0:
        await message.answer("⚔️ Баттл уже идёт, набор закрыт.")
        return

    user = message.from_user
    limit = contest.get("participant_limit", 0)
    current = await count_battle_participants(contest_id)

    if current >= limit:
        await message.answer("😔 Все места уже заняты.")
        return

    already = await is_battle_participant(contest_id, user.id)
    if already:
        await message.answer("✅ Вы уже в списке участников!")
        return

    # Проверка подписок на спонсоров
    from db.database import get_sponsors
    from utils.helpers import check_user_subscription
    sponsors = await get_sponsors(contest_id)
    missing = []
    for sp in sponsors:
        if sp.get("channel_id"):
            ok = await check_user_subscription(bot, user.id, sp["channel_id"])
            if not ok:
                missing.append(sp)
    if missing:
        from keyboards import sponsors_check_kb
        await message.answer("❌ Подпишитесь на все обязательные каналы:", reply_markup=sponsors_check_kb(missing))
        return

    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    added = await add_battle_participant(contest_id, user.id, user.username, full_name)
    if not added:
        await message.answer("✅ Вы уже в списке участников!")
        return

    current += 1
    spots_left = limit - current

    # Обновить пост набора
    me = await bot.get_me()
    channel_id = contest["channel_id"]
    message_id = contest.get("message_id")
    base_text = (contest.get("text") or "") + (
        f"\n\n⚔️ <b>Битва Юзернеймов!</b>\n"
        f"Мест осталось: <b>{spots_left}</b>"
    )

    if spots_left > 0:
        kb = battle_join_kb(me.username, contest_id, spots_left)
        if message_id:
            try:
                if contest.get("photo_id"):
                    await bot.edit_message_caption(chat_id=channel_id, message_id=message_id, caption=base_text, reply_markup=kb)
                else:
                    await bot.edit_message_text(chat_id=channel_id, message_id=message_id, text=base_text, reply_markup=kb)
            except Exception:
                pass
        await message.answer(f"✅ Вы записались в баттл! Мест осталось: <b>{spots_left}</b>")
    else:
        # Набор завершён — закрываем пост и стартуем
        if message_id:
            try:
                closed_text = (contest.get("text") or "") + "\n\n⚔️ <b>Набор закрыт! Баттл начинается!</b>"
                if contest.get("photo_id"):
                    await bot.edit_message_caption(chat_id=channel_id, message_id=message_id, caption=closed_text, reply_markup=None)
                else:
                    await bot.edit_message_text(chat_id=channel_id, message_id=message_id, text=closed_text, reply_markup=None)
            except Exception:
                pass

        await message.answer("✅ Вы последний участник! Баттл начинается! ⚔️")
        import asyncio
        asyncio.create_task(start_battle_round(bot, contest_id, 1))


# ──────────────────────── РАУНДЫ ────────────────────────

async def start_battle_round(bot: Bot, contest_id: int, round_num: int):
    contest = await get_contest(contest_id)
    if not contest or contest["status"] != "active":
        return

    await set_contest_current_round(contest_id, round_num)
    participants = await get_battle_participants(contest_id, status="active")
    channel_id = contest["channel_id"]

    if round_num <= 2:
        # Парные раунды
        random.shuffle(participants)
        pairs = [(participants[i], participants[i+1]) for i in range(0, len(participants)-1, 2)]

        round_label = f"Раунд {round_num}"
        await bot.send_message(
            chat_id=channel_id,
            text=f"⚔️ <b>Битва Юзернеймов — {round_label} начался!</b>\n\n"
                 f"Голосуйте за участников в парах ниже 👇"
        )

        for idx, (c1, c2) in enumerate(pairs, 1):
            name1 = f"@{c1['username']}" if c1.get("username") else c1.get("full_name", "Участник")
            name2 = f"@{c2['username']}" if c2.get("username") else c2.get("full_name", "Участник")
            kb = battle_vote_kb(contest_id, round_num, c1, c2, 0, 0)
            msg = await bot.send_message(
                chat_id=channel_id,
                text=f"⚔️ <b>{round_label} · Пара #{idx}</b>\n\n{name1} vs {name2}\n\nКто круче?",
                reply_markup=kb
            )
            await add_battle_message(contest_id, round_num, msg.message_id, c1["user_id"], c2["user_id"])

        # Запланировать конец раунда
        minutes_key = f"round{round_num}_minutes"
        minutes = contest.get(minutes_key, 60)
        schedule_battle_round(bot, contest_id, round_num, minutes)
        logger.info(f"Battle #{contest_id} round {round_num} started, {len(pairs)} pairs, {minutes}min")

    elif round_num == 3:
        # Финал — один пост со всеми финалистами
        votes = {p["user_id"]: 0 for p in participants}
        kb = battle_final_kb(contest_id, round_num, participants, votes)
        names = ", ".join(
            f"@{p['username']}" if p.get("username") else p.get("full_name","?")
            for p in participants
        )
        msg = await bot.send_message(
            chat_id=channel_id,
            text=f"🏆 <b>ФИНАЛ Битвы Юзернеймов!</b>\n\nФиналисты: {names}\n\nЗа кого голосуете?",
            reply_markup=kb
        )
        await add_battle_message(contest_id, round_num, msg.message_id)
        minutes = contest.get("round3_minutes", 60)
        schedule_battle_round(bot, contest_id, round_num, minutes)
        logger.info(f"Battle #{contest_id} FINAL started, {len(participants)} finalists, {minutes}min")


async def finish_battle_round(bot: Bot, contest_id: int, round_num: int):
    contest = await get_contest(contest_id)
    if not contest or contest["status"] != "active":
        return

    channel_id = contest["channel_id"]
    messages = await get_battle_messages(contest_id, round_num)
    participants = await get_battle_participants(contest_id, status="active")

    if round_num <= 2:
        # Подсчёт голосов по парам, выбывание
        for bm in messages:
            c1_id = bm.get("candidate1_id")
            c2_id = bm.get("candidate2_id")
            if not c1_id or not c2_id:
                continue
            v1 = await get_vote_count(contest_id, round_num, c1_id)
            v2 = await get_vote_count(contest_id, round_num, c2_id)
            # Выбывает тот у кого меньше; при ничье — случайно
            if v1 < v2:
                loser_id = c1_id
            elif v2 < v1:
                loser_id = c2_id
            else:
                loser_id = random.choice([c1_id, c2_id])
            await eliminate_battle_participant(contest_id, loser_id)

        # Удалить все посты раунда
        for bm in messages:
            try:
                await bot.delete_message(chat_id=channel_id, message_id=bm["message_id"])
            except Exception:
                pass
        await delete_battle_messages_db(contest_id, round_num)

        survivors = await get_battle_participants(contest_id, status="active")
        names = ", ".join(
            f"@{p['username']}" if p.get("username") else p.get("full_name","?")
            for p in survivors
        )
        await bot.send_message(
            chat_id=channel_id,
            text=f"✅ <b>Раунд {round_num} завершён!</b>\n\nПроходят дальше ({len(survivors)}):\n{names}"
        )

        if len(survivors) < 2:
            # Недостаточно для следующего раунда — объявляем победителя
            winner = survivors[0] if survivors else None
            await _post_battle_winner(bot, contest, winner)
        else:
            next_round = round_num + 1
            import asyncio
            asyncio.create_task(start_battle_round(bot, contest_id, next_round))

    elif round_num == 3:
        # Финал
        votes = {}
        for p in participants:
            votes[p["user_id"]] = await get_vote_count(contest_id, round_num, p["user_id"])

        # Удалить финальный пост
        for bm in messages:
            try:
                await bot.delete_message(chat_id=channel_id, message_id=bm["message_id"])
            except Exception:
                pass
        await delete_battle_messages_db(contest_id, round_num)

        winner = max(participants, key=lambda p: votes.get(p["user_id"], 0)) if participants else None
        await _post_battle_winner(bot, contest, winner)


async def _post_battle_winner(bot: Bot, contest: dict, winner: dict | None):
    contest_id = contest["id"]
    channel_id = contest["channel_id"]

    if winner:
        mention = format_user_mention(winner.get("username"), winner.get("full_name","?"), winner["user_id"])
        await bot.send_message(
            chat_id=channel_id,
            text=f"🎉 <b>Битва Юзернеймов официально завершена!</b>\n\n"
                 f"🏆 Победителем стал {mention}!\n\n"
                 f"Поздравляем! 🥇"
        )
        try:
            await bot.send_message(
                chat_id=winner["user_id"],
                text=f"🏆 Поздравляем! Вы победили в Битве Юзернеймов <b>#{contest_id}</b>!"
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                chat_id=contest["admin_id"],
                text=f"🏆 Битва <b>#{contest_id}</b> завершена!\n\nПобедитель: {mention}"
            )
        except Exception:
            pass
    else:
        await bot.send_message(chat_id=channel_id, text=f"⚔️ Битва #{contest_id} завершена.")

    await finish_contest(contest_id)


# ──────────────────────── ГОЛОСОВАНИЕ ────────────────────────

@router.callback_query(F.data.startswith("bv:"))
async def battle_vote_handler(call: CallbackQuery, bot: Bot):
    # bv:{contest_id}:{candidate_id}:{round}
    parts = call.data.split(":")
    if len(parts) < 4:
        await call.answer("Ошибка", show_alert=True)
        return

    try:
        contest_id = int(parts[1])
        candidate_id = int(parts[2])
        round_num = int(parts[3])
    except ValueError:
        await call.answer("Ошибка", show_alert=True)
        return

    contest = await get_contest(contest_id)
    if not contest or contest["status"] != "active":
        await call.answer("⚔️ Голосование уже закрыто.", show_alert=True)
        return

    if contest.get("current_round") != round_num:
        await call.answer("Этот раунд уже завершён.", show_alert=True)
        return

    recorded = await add_battle_vote(contest_id, round_num, call.from_user.id, candidate_id)
    if not recorded:
        await call.answer("Вы уже проголосовали в этом раунде!", show_alert=True)
        return

    await call.answer("✅ Голос засчитан!")

    # Обновить сообщение с актуальным счётом
    messages = await get_battle_messages(contest_id, round_num)
    target_msg = None
    for bm in messages:
        if bm.get("candidate1_id") == candidate_id or bm.get("candidate2_id") == candidate_id:
            target_msg = bm
            break
        # Финальный пост (candidate1_id=None)
        if bm.get("candidate1_id") is None:
            target_msg = bm
            break

    if not target_msg:
        return

    try:
        if target_msg.get("candidate1_id") and target_msg.get("candidate2_id"):
            # Парный пост
            c1_id = target_msg["candidate1_id"]
            c2_id = target_msg["candidate2_id"]
            v1 = await get_vote_count(contest_id, round_num, c1_id)
            v2 = await get_vote_count(contest_id, round_num, c2_id)

            # Найти данные участников
            all_p = await get_battle_participants(contest_id)
            p_map = {p["user_id"]: p for p in all_p}
            c1 = p_map.get(c1_id, {"user_id": c1_id, "username": None, "full_name": "?"})
            c2 = p_map.get(c2_id, {"user_id": c2_id, "username": None, "full_name": "?"})
            kb = battle_vote_kb(contest_id, round_num, c1, c2, v1, v2)
            await bot.edit_message_reply_markup(
                chat_id=contest["channel_id"],
                message_id=target_msg["message_id"],
                reply_markup=kb
            )
        else:
            # Финальный пост
            finalists = await get_battle_participants(contest_id, status="active")
            votes = {p["user_id"]: await get_vote_count(contest_id, round_num, p["user_id"]) for p in finalists}
            kb = battle_final_kb(contest_id, round_num, finalists, votes)
            await bot.edit_message_reply_markup(
                chat_id=contest["channel_id"],
                message_id=target_msg["message_id"],
                reply_markup=kb
            )
    except Exception as e:
        logger.warning(f"battle vote update message: {e}")
