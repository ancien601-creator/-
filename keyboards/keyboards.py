from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать проект", callback_data="create_project")
    builder.button(text="📋 Мои проекты", callback_data="my_projects")
    builder.button(text="📡 Мои каналы", callback_data="my_channels")
    builder.adjust(1)
    return builder.as_markup()


def contest_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Классический розыгрыш", callback_data="type_classic")
    builder.button(text="🎰 Лотерея по слотам", callback_data="type_slots")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def channels_list_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        label = ch.get("channel_title") or ch.get("channel_username") or str(ch["channel_id"])
        builder.button(text=f"📢 {label}", callback_data=f"ch:{ch['channel_id']}")
    builder.button(text="➕ Добавить канал", callback_data="add_channel")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def finish_condition_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏰ По времени", callback_data="finish_time")
    builder.button(text="👥 По количеству участников", callback_data="finish_count")
    builder.adjust(1)
    return builder.as_markup()


def button_text_kb() -> InlineKeyboardMarkup:
    options = ["Участвовать", "Подключаюсь", "Хочу участвовать", "Беру слот", "Войти в розыгрыш"]
    builder = InlineKeyboardBuilder()
    for opt in options:
        builder.button(text=opt, callback_data=f"btn:{opt}")
    builder.button(text="✏️ Свой текст", callback_data="btn:custom")
    builder.adjust(2)
    return builder.as_markup()


def payment_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🆓 Бесплатный", callback_data="pay_free")
    builder.button(text="💰 Платный (Telegram Stars)", callback_data="pay_paid")
    builder.adjust(1)
    return builder.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm_publish")
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(1)
    return builder.as_markup()


def skip_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏩ Пропустить", callback_data="skip")
    builder.adjust(1)
    return builder.as_markup()


def participate_kb(bot_username: str, contest_id: int, button_text: str = "Участвовать") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"🎯 {button_text}",
        url=f"https://t.me/{bot_username}?start=join_{contest_id}"
    )
    return builder.as_markup()


def slots_grid_kb(bot_username: str, contest_id: int, total: int, booked_slots: set[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    cols = 5
    for i in range(1, total + 1):
        if i in booked_slots:
            builder.button(text=f"❌ {i}", callback_data=f"slot_taken")
        else:
            builder.button(
                text=f"{i}",
                url=f"https://t.me/{bot_username}?start=slot_{contest_id}_{i}"
            )
    builder.adjust(cols)
    return builder.as_markup()


def my_projects_kb(contests: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in contests:
        icon = "🎯" if c["type"] == "classic" else "🎰"
        status = "✅" if c["status"] == "active" else "🔒"
        label = c.get("title") or f"#{c['id']}"
        builder.button(text=f"{status} {icon} {label}", callback_data=f"proj:{c['id']}")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def project_actions_kb(contest: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if contest["status"] == "active":
        if contest["type"] == "classic":
            builder.button(text="🏆 Подвести итоги", callback_data=f"draw:{contest['id']}")
        builder.button(text="🗑 Завершить / закрыть", callback_data=f"close:{contest['id']}")
    builder.button(text="◀️ Назад", callback_data="my_projects")
    builder.adjust(1)
    return builder.as_markup()


def sponsors_check_kb(sponsors: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sp in sponsors:
        uname = sp["channel_username"]
        link = f"https://t.me/{uname.lstrip('@')}"
        builder.button(text=f"📢 {uname}", url=link)
    builder.button(text="✅ Я подписался — проверить", callback_data="check_subscriptions")
    builder.adjust(1)
    return builder.as_markup()


def manage_channels_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        label = ch.get("channel_title") or ch.get("channel_username") or str(ch["channel_id"])
        builder.button(text=f"🗑 {label}", callback_data=f"del_ch:{ch['channel_id']}")
    builder.button(text="➕ Добавить канал", callback_data="add_channel")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()
