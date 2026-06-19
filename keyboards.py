from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_admin:
        builder.button(text="📋 Создать проект", callback_data="create_project")
        builder.button(text="📂 Мои проекты", callback_data="my_projects")
    builder.button(text="➕ Добавить канал", callback_data="add_channel_menu")
    builder.button(text="📖 Помощь", callback_data="help")
    builder.adjust(1)
    return builder.as_markup()

def slot_url_buttons(contest_id: int, slots_count: int, occupied: dict[int, int], bot_username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(1, slots_count + 1):
        if i in occupied:
            builder.button(text=f"❌ {i}", callback_data="slot_occupied")
        else:
            url = f"https://t.me/{bot_username}?start=slot_{contest_id}_{i}"
            builder.button(text=str(i), url=url)
    builder.adjust(5)
    return builder.as_markup()

def project_type_choice() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Классический розыгрыш", callback_data="type_classic")
    builder.button(text="🎰 Лотерея по слотам", callback_data="type_slots")
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    return builder.as_markup()

def end_condition_choice() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏰ В определенное время", callback_data="cond_time")
    builder.button(text="👥 По количеству участников", callback_data="cond_participants")
    return builder.as_markup()

def button_text_choice() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Участвовать", callback_data="btn_participate")
    builder.button(text="Подключаюсь", callback_data="btn_join")
    builder.button(text="Испытать удачу", callback_data="btn_luck")
    builder.button(text="✏️ Свой текст", callback_data="btn_custom")
    return builder.as_markup()

def payment_choice() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🆓 Бесплатно", callback_data="pay_free")
    builder.button(text="💳 Платно", callback_data="pay_paid")
    return builder.as_markup()

def skip_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="skip")
    return builder.as_markup()

def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="publish")
    builder.button(text="❌ Отмена", callback_data="cancel_create")
    return builder.as_markup()

def my_projects_keyboard(contests: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in contests:
        text = f"{'🎁' if c['type']=='classic' else '🎰'} {c['title'] or 'Без названия'} (ID {c['id']})"
        builder.button(text=text, callback_data=f"project_{c['id']}")
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def project_actions(contest_id: int, contest_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏁 Подвести итоги", callback_data=f"finish_{contest_id}")
    builder.button(text="❌ Удалить", callback_data=f"delete_{contest_id}")
    builder.button(text="🔙 Назад", callback_data="my_projects")
    return builder.as_markup()

def slot_buttons(contest_id: int, slots_count: int, occupied: dict[int, int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(1, slots_count + 1):
        if i in occupied:
            text = f"❌ {i}"
            callback = "slot_occupied"
        else:
            text = str(i)
            callback = f"slot_{contest_id}_{i}"
        builder.button(text=text, callback_data=callback)
    builder.adjust(5)
    return builder.as_markup()

def subscription_check(channels: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(text=f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")
    builder.button(text="✅ Проверить подписку", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()
