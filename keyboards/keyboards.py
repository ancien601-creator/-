from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Создать проект", callback_data="create_project")
    b.button(text="📋 Мои проекты", callback_data="my_projects")
    b.button(text="📡 Мои каналы", callback_data="my_channels")
    b.adjust(1)
    return b.as_markup()


def contest_type_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Классический розыгрыш", callback_data="type_classic")
    b.button(text="🎰 Лотерея по слотам", callback_data="type_slots")
    b.button(text="🎟 Обычная лотерея", callback_data="type_lottery")
    b.button(text="⚔️ Битва юзернеймов", callback_data="type_battle")
    b.button(text="◀️ Назад", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


def channels_list_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        label = ch.get("channel_title") or ch.get("channel_username") or str(ch["channel_id"])
        b.button(text=f"📢 {label}", callback_data=f"ch:{ch['channel_id']}")
    b.button(text="➕ Добавить канал", callback_data="add_channel")
    b.button(text="◀️ Назад", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


def ask_content_kb(prefix: str = "") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📝 Добавить текст / фото", callback_data=f"{prefix}content_yes")
    b.button(text="⏩ Без текста", callback_data=f"{prefix}content_no")
    b.adjust(1)
    return b.as_markup()


def finish_condition_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⏰ По времени", callback_data="finish_time")
    b.button(text="👥 По количеству участников", callback_data="finish_count")
    b.adjust(1)
    return b.as_markup()


def button_text_kb() -> InlineKeyboardMarkup:
    opts = ["Участвовать", "Подключаюсь", "Хочу участвовать", "Войти в розыгрыш"]
    b = InlineKeyboardBuilder()
    for o in opts:
        b.button(text=o, callback_data=f"btn:{o}")
    b.button(text="✏️ Свой текст", callback_data="btn:custom")
    b.adjust(2)
    return b.as_markup()


def show_count_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Показывать счётчик", callback_data="show_count:yes")
    b.button(text="❌ Не показывать", callback_data="show_count:no")
    b.adjust(1)
    return b.as_markup()


def payment_type_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🆓 Бесплатно", callback_data="pay_free")
    b.button(text="⭐ Платно (Telegram Stars)", callback_data="pay_paid")
    b.adjust(1)
    return b.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Опубликовать", callback_data="confirm_publish")
    b.button(text="❌ Отмена", callback_data="cancel_creation")
    b.adjust(1)
    return b.as_markup()


def skip_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⏩ Пропустить", callback_data="skip")
    b.adjust(1)
    return b.as_markup()


def participate_kb(bot_username: str, contest_id: int, button_text: str = "Участвовать") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"🎯 {button_text}", url=f"https://t.me/{bot_username}?start=join_{contest_id}")
    return b.as_markup()


def lottery_join_kb(bot_username: str, contest_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎟 Взять билет", url=f"https://t.me/{bot_username}?start=lottery_{contest_id}")
    return b.as_markup()


def battle_join_kb(bot_username: str, contest_id: int, spots_left: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"⚔️ Подать заявку ({spots_left} мест)", url=f"https://t.me/{bot_username}?start=battle_{contest_id}")
    return b.as_markup()


def slots_grid_kb(bot_username: str, contest_id: int, total: int, booked: set[int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i in range(1, total + 1):
        if i in booked:
            b.button(text=f"❌ {i}", callback_data="slot_taken")
        else:
            b.button(text=str(i), url=f"https://t.me/{bot_username}?start=slot_{contest_id}_{i}")
    b.adjust(5)
    return b.as_markup()


def sponsors_check_kb(sponsors: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for sp in sponsors:
        uname = sp["channel_username"]
        b.button(text=f"📢 {uname}", url=f"https://t.me/{uname.lstrip('@')}")
    b.button(text="✅ Я подписался — проверить", callback_data="check_subscriptions")
    b.adjust(1)
    return b.as_markup()


def my_projects_kb(contests: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    icons = {"classic": "🎯", "slots": "🎰", "lottery": "🎟", "battle": "⚔️"}
    for c in contests:
        icon = icons.get(c["type"], "📌")
        status = "✅" if c["status"] == "active" else "🔒"
        label = c.get("title") or f"#{c['id']}"
        b.button(text=f"{status} {icon} {label}", callback_data=f"proj:{c['id']}")
    b.button(text="◀️ Назад", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


def project_actions_kb(contest: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if contest["status"] == "active":
        if contest["type"] in ("classic", "lottery"):
            b.button(text="🏆 Подвести итоги", callback_data=f"draw:{contest['id']}")
        b.button(text="🔒 Закрыть", callback_data=f"close:{contest['id']}")
    b.button(text="◀️ Назад", callback_data="my_projects")
    b.adjust(1)
    return b.as_markup()


def manage_channels_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        label = ch.get("channel_title") or ch.get("channel_username") or str(ch["channel_id"])
        b.button(text=f"🗑 {label}", callback_data=f"del_ch:{ch['channel_id']}")
    b.button(text="➕ Добавить канал", callback_data="add_channel")
    b.button(text="◀️ Назад", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


def battle_vote_kb(contest_id: int, round_num: int, c1: dict, c2: dict, votes1: int, votes2: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    name1 = f"@{c1['username']}" if c1.get("username") else c1.get("full_name", "Участник 1")
    name2 = f"@{c2['username']}" if c2.get("username") else c2.get("full_name", "Участник 2")
    b.button(text=f"{name1} · {votes1} 🗳", callback_data=f"bv:{contest_id}:{c1['user_id']}:{round_num}")
    b.button(text=f"{name2} · {votes2} 🗳", callback_data=f"bv:{contest_id}:{c2['user_id']}:{round_num}")
    b.adjust(2)
    return b.as_markup()


def battle_final_kb(contest_id: int, round_num: int, finalists: list[dict], votes: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for f in finalists:
        name = f"@{f['username']}" if f.get("username") else f.get("full_name", "Участник")
        v = votes.get(f["user_id"], 0)
        b.button(text=f"{name} · {v} 🗳", callback_data=f"bv:{contest_id}:{f['user_id']}:{round_num}")
    b.adjust(2)
    return b.as_markup()
