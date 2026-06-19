from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎁 Создать конкурс"), KeyboardButton(text="📊 Мои конкурсы")]
        ],
        resize_keyboard=True
    )

def get_finish_type_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏳ В определенное время", callback_data="finish_time")],
            [InlineKeyboardButton(text="👥 По количеству участников", callback_data="finish_count")]
        ]
    )

def get_preset_buttons_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Участвовать", callback_data="btn_Участвовать")],
            [InlineKeyboardButton(text="Испытать удачу", callback_data="btn_Испытать удачу")],
            [InlineKeyboardButton(text="Принять участие", callback_data="btn_Принять участие")]
        ]
    )

def get_sponsors_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_sponsor")],
            [InlineKeyboardButton(text="✅ Завершить и опубликовать", callback_data="finish_sponsors")]
        ]
    )

def get_participate_kb(bot_username: str, contest_id: int, text: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, url=f"https://t.me/{bot_username}?start=contest_{contest_id}")]
        ]
    )

def get_contests_list_kb(contests):
    builder = InlineKeyboardBuilder()
    for contest in contests:
        builder.button(text=f"Конкурс #{contest['id']} (Канал: {contest['chat_id']})", callback_data=f"manage_{contest['id']}")
    builder.adjust(1)
    return builder.as_markup()

def get_contest_manage_kb(contest_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Подвести итоги", callback_data=f"stop_{contest_id}")]
        ]
    )
