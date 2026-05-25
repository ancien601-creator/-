import asyncio
import logging
import sqlite3
import random
import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import Bot, Dispatcher, F, types, BaseMiddleware
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, LabeledPrice,
    PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# === НАСТРОЙКИ ===
BOT_TOKEN = "8976298819:AAHBu4guxbgyZVsoIhT4CO0WaU6LBDPGW_0"
ADMIN_ID = 5891736406  # ЗАМЕНИ НА СВОЙ ID

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

GIFTS = ["❤️ Сердце", "🐭 Мышка", "🏆 Кубок", "🎂 Торт", "🌹 Роза", "🎁 Коробочка", "💍 Кольцо", "🚀 Ракета"]

# === СИСТЕМА ЛОББИ ===
lobbies = {}


class TopUpStates(StatesGroup):
    waiting_for_amount = State()


# === БАЗА ДАННЫХ ===
conn = sqlite3.connect('casino.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT "Игрок",
        stars INTEGER DEFAULT 0,
        last_free_case REAL DEFAULT 0
    )
''')
conn.commit()

try:
    cursor.execute('ALTER TABLE users ADD COLUMN username TEXT DEFAULT "Игрок"')
    conn.commit()
except sqlite3.OperationalError:
    pass


def get_user(user_id, username="Игрок"):
    cursor.execute('SELECT stars, last_free_case FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute('INSERT INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
        conn.commit()
        return (0, 0.0)
    cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
    conn.commit()
    return user


def update_balance(user_id, amount):
    cursor.execute('UPDATE users SET stars = stars + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()


def update_free_case_time(user_id):
    cursor.execute('UPDATE users SET last_free_case = ? WHERE user_id = ?', (time.time(), user_id))
    conn.commit()


# === ЗАЩИТА ОТ DDOS / ФЛУДА ===
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit=0.6):
        self.limit = limit
        self.users = {}

    async def __call__(self, handler, event: types.Message, data: Dict[str, Any]) -> Any:
        user_id = event.from_user.id
        current_time = time.time()
        if user_id in self.users and (current_time - self.users[user_id] < self.limit):
            return
        self.users[user_id] = current_time
        return await handler(event, data)


dp.message.middleware(ThrottlingMiddleware(limit=0.6))

# === КЛАВИАТУРЫ ===
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💳 Пополнить ⭐️")],
    [KeyboardButton(text="🎮 Игры"), KeyboardButton(text="🎁 Фри Кейс (24ч)")]
], resize_keyboard=True)

games_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📦 Кейсы"), KeyboardButton(text="🎰 ПВП 777")],
    [KeyboardButton(text="🪙 ПВП Орел и Решка"), KeyboardButton(text="🔙 Назад")]
], resize_keyboard=True)

cases_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🌱 Бомж (5 ⭐️)"), KeyboardButton(text="🥉 Бронза (15 ⭐️)")],
    [KeyboardButton(text="🥈 Серебро (50 ⭐️)"), KeyboardButton(text="🥇 Золото (120 ⭐️)")],
    [KeyboardButton(text="💎 Элитный (250 ⭐️)"), KeyboardButton(text="👑 СУПЕР-ИМБА (500 ⭐️)")],
    [KeyboardButton(text="🔙 Назад")]
], resize_keyboard=True)


# === АДМИН-КОМАНДА /give ===
@dp.message(Command("give"))
async def give_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ Формат: <code>/give [ID] [Кол-во]</code>", parse_mode="HTML")
        return
    try:
        target_id, amount = int(args[1]), int(args[2])
    except ValueError:
        await message.answer("❌ ID и количество должны быть числами.")
        return
    update_balance(target_id, amount)
    await message.answer(f"✅ Успешно начислено <b>{amount} ⭐️</b> для ID <code>{target_id}</code>.", parse_mode="HTML")


# === ОБРАБОТЧИКИ ИНТЕРФЕЙСА ===

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    get_user(message.from_user.id, message.from_user.username or "Игрок")
    await message.answer(
        "👋 <b>Добро пожаловать в ИМБОВОЕ Telegram Stars Casino!</b>\n\n"
        "🔥 У нас играют только реальные люди друг против друга! Создавай лобби или заходи в существующие!\n\n"
        "👨‍💻 <i>Создатель бота:</i> @Vados4433",
        reply_markup=main_kb, parse_mode="HTML"
    )


@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_kb)


@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    stars, _ = get_user(message.from_user.id, message.from_user.username or "Игрок")
    await message.answer(
        f"👤 <b>Твой игровой профиль:</b>\n\n"
        f"🎯 Твой ID: <code>{message.from_user.id}</code>\n"
        f"💰 Баланс: <b>{stars} ⭐️ Stars</b>\n\n"
        f"⚙️ <i>Програмист казино:</i> @Vados4433",
        parse_mode="HTML"
    )


@dp.message(F.text.in_(["🎮 Игры", "🎮 Игры от 2-х игроков"]))
async def games_menu(message: types.Message):
    await message.answer("🎰 Выбери игровой режим (Все игры проходят в режиме PvP между игроками):",
                         reply_markup=games_kb)


@dp.message(F.text == "📦 Кейсы")
async def cases_menu(message: types.Message):
    await message.answer(
        "📦 <b>Магазин Имбовых Кейсов</b>\n\n"
        "Здесь ты можешь выиграть гору ⭐️ Звезд или редкие Telegram-Подарки!\n"
        "Выигрыши не ограничены, крути сколько угодно раз подряд! 🎰🔥",
        reply_markup=cases_kb, parse_mode="HTML"
    )


# === ОБРАБОТЧИК КНОПКИ ПОПОЛНЕНИЯ (ИЗМЕНЕНО НА МИНИМУМ 5) ===
@dp.message(F.text.in_(["💳 Пополнить ⭐️", "💳 Пополниться ⭐️"]))
async def topup_init(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ <b>Введите количество ⭐️ Stars, на которое хотите пополнить баланс:</b>\n<i>(Минимум 5)</i>",
        parse_mode="HTML")
    await state.set_state(TopUpStates.waiting_for_amount)


@dp.message(TopUpStates.waiting_for_amount)
async def topup_amount_received(message: types.Message, state: FSMContext):
    text = message.text.strip()
    # Проверка изменена с 10 на 5 звезд
    if not text.isdigit() or int(text) < 5:
        await message.answer("❌ Ошибка! Введите числовое значение от 5 ⭐️.")
        return
    amount = int(text)
    await state.clear()
    await message.answer(f"⏳ Формирую счет на оплату {amount} ⭐️...")
    try:
        prices = [LabeledPrice(label=f"{amount} Telegram Stars", amount=amount)]
        await bot.send_invoice(
            chat_id=message.chat.id, title="Пополнение баланса",
            description=f"Покупка {amount} игровых звезд в казино",
            payload=f"topup_{amount}", provider_token="", currency="XTR", prices=prices
        )
    except Exception:
        await message.answer("❌ Ошибка платежной системы.")


@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    amount = message.successful_payment.total_amount
    update_balance(message.from_user.id, amount)
    await message.answer(f"🎉 <b>Успешно!</b> Баланс пополнен на <b>{amount} ⭐️</b>.", parse_mode="HTML")


# === ФРИ КЕЙС ===
@dp.message(F.text == "🎁 Фри Кейс (24ч)")
async def free_case(message: types.Message):
    user_id = message.from_user.id
    _, last_time = get_user(user_id)
    if time.time() - last_time < 86400:
        left = int(86400 - (time.time() - last_time))
        await message.answer(f"⏳ Бонус будет доступен через {left // 3600} ч. {(left % 3600) // 60} мин.")
        return
    win = random.randint(1, 7)
    update_balance(user_id, win)
    update_free_case_time(user_id)
    await message.answer(f"🎁 Выиграно: <b>{win} ⭐️</b>!", parse_mode="HTML")


# ==========================================
# МУЛЬТИПЛЕЕР: ЛОББИ ИГР (PvP)
# ==========================================

@dp.message(F.text == "🎰 ПВП 777")
async def pvp_777_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ставка 10 ⭐️", callback_data="create_777_10"),
         InlineKeyboardButton(text="Ставка 50 ⭐️", callback_data="create_777_50")],
        [InlineKeyboardButton(text="Ставка 100 ⭐️", callback_data="create_777_100"),
         InlineKeyboardButton(text="Ставка 250 ⭐️", callback_data="create_777_250")]
    ])
    await message.answer(
        "🎰 <b>ПВП Слоты (777)</b>\nУ кого выпадет комбинация больше — тот забирает банк (минус 5% комиссия казино)!\n\nВыбери ставку для создания лобби:",
        reply_markup=kb, parse_mode="HTML")


@dp.message(F.text == "🪙 ПВП Орел и Решка")
async def pvp_coin_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Орел (10 ⭐️)", callback_data="create_coin_10_o"),
         InlineKeyboardButton(text="Решка (10 ⭐️)", callback_data="create_coin_10_r")],
        [InlineKeyboardButton(text="Орел (50 ⭐️)", callback_data="create_coin_50_o"),
         InlineKeyboardButton(text="Решка (50 ⭐️)", callback_data="create_coin_50_r")],
        [InlineKeyboardButton(text="Орел (100 ⭐️)", callback_data="create_coin_100_o"),
         InlineKeyboardButton(text="Решка (100 ⭐️)", callback_data="create_coin_100_r")]
    ])
    await message.answer(
        "🪙 <b>ПВП Орел и Решка</b>\nВы выбираете сторону, а соперник ставит на противоположную. Победитель забирает всё за вычетом 5% комиссии!\n\nВыбери ставку и сторону:",
        reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("create_"))
async def create_lobby_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    stars, _ = get_user(user_id, callback.from_user.username or "Игрок")
    data_parts = callback.data.split("_")

    game_type = data_parts[1]
    bet = int(data_parts[2])
    choice = data_parts[3] if len(data_parts) == 4 else None

    if stars < bet:
        await callback.answer("❌ Недостаточно звезд на балансе!", show_alert=True)
        return

    update_balance(user_id, -bet)

    lobby_id = str(random.randint(100000, 999999))
    lobbies[lobby_id] = {
        "type": game_type,
        "creator": user_id,
        "creator_name": callback.from_user.username or "Игрок",
        "bet": bet,
        "choice": choice
    }

    join_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Присоединиться к игре", callback_data=f"join_{lobby_id}")]
    ])

    game_name = "🎰 Слоты 777" if game_type == "777" else "🪙 Орел и Решка"
    side_text = f" (Выбрал: {'Орел' if choice == 'o' else 'Решка'})" if choice else ""

    await callback.message.answer(
        f"🚀 <b>Лобби создано для игры от 2-х человек!</b>\n\n"
        f"👾 Игра: {game_name}\n"
        f"👑 Создатель: @{callback.from_user.username}\n"
        f"💰 Ставка: <b>{bet} ⭐️</b>{side_text}\n\n"
        f"<i>Ожидаем второго игрока...</i>",
        reply_markup=join_kb, parse_mode="HTML"
    )
    await callback.message.delete()
    await callback.answer()


@dp.callback_query(F.data.startswith("join_"))
async def join_lobby_handler(callback: CallbackQuery):
    lobby_id = callback.data.split("_")[1]
    user2_id = callback.from_user.id
    user2_name = callback.from_user.username or "Игрок"

    if lobby_id not in lobbies:
        await callback.answer("❌ Лобби уже не активно!", show_alert=True)
        return

    lobby = lobbies[lobby_id]
    user1_id = lobby["creator"]
    bet = lobby["bet"]

    if user2_id == user1_id:
        await callback.answer("❌ Вы не можете играть сами с собой!", show_alert=True)
        return

    stars, _ = get_user(user2_id, user2_name)
    if stars < bet:
        await callback.answer("❌ Недостаточно звезд!", show_alert=True)
        return

    lobbies.pop(lobby_id)
    update_balance(user2_id, -bet)

    full_bank = bet * 2
    win_pool = int(full_bank * 0.95)

    await callback.message.delete()

    if lobby["type"] == "777":
        roll1 = random.randint(1, 64)
        roll2 = random.randint(1, 64)

        if roll1 > roll2:
            update_balance(user1_id, win_pool)
            winner_text = f"🏆 Победил @{lobby['creator_name']}! Выигрыш: <b>{win_pool} ⭐️</b>!"
        elif roll2 > roll1:
            update_balance(user2_id, win_pool)
            winner_text = f"🏆 Победил @{user2_name}! Выигрыш: <b>{win_pool} ⭐️</b>!"
        else:
            update_balance(user1_id, bet)
            update_balance(user2_id, bet)
            winner_text = "🤝 <b>Ничья! Ставки возвращены игрокам!</b>"

        result_msg = (
            f"🏁 <b>Игра 777 (PvP) Завершена!</b>\n\n"
            f"👤 @{lobby['creator_name']} выбил комбинацию № {roll1}\n"
            f"👤 @{user2_name} выбил комбинацию № {roll2}\n\n"
            f"{winner_text}"
        )
        await bot.send_message(user1_id, result_msg, parse_mode="HTML")
        await bot.send_message(user2_id, result_msg, parse_mode="HTML")

    elif lobby["type"] == "coin":
        result = random.choice(["o", "r"])
        result_text = "🦅 ОРЕЛ" if result == "o" else "🪙 РЕШКА"

        if lobby["choice"] == result:
            update_balance(user1_id, win_pool)
            winner_name = f"@{lobby['creator_name']}"
            loser_name = f"@{user2_name}"
        else:
            update_balance(user2_id, win_pool)
            winner_name = f"@{user2_name}"
            loser_name = f"@{lobby['creator_name']}"

        result_msg = (
            f"🏁 <b>Орел и Решка (PvP) Результат!</b>\n\n"
            f"🪙 На монетке выпадает: <b>{result_text}</b>\n\n"
            f"🏆 Победитель: {winner_name} (Забирает <b>{win_pool} ⭐️</b>)\n"
            f"💀 Проигравший: {loser_name} (Теряет {bet} ⭐️)"
        )
        await bot.send_message(user1_id, result_msg, parse_mode="HTML")
        await bot.send_message(user2_id, result_msg, parse_mode="HTML")


# === МАГАЗИН КЕЙСОВ ===
@dp.message(F.text.in_([
    "🌱 Бомж (5 ⭐️)", "🥉 Бронза (15 ⭐️)", "🥈 Серебро (50 ⭐️)",
    "🥇 Золото (120 ⭐️)", "💎 Элитный (250 ⭐️)", "👑 СУПЕР-ИМБА (500 ⭐️)"
]))
async def open_case(message: types.Message):
    text = message.text
    if "Бомж" in text:
        cost, gift_chance, star_range, case_name = 5, 0.5, (1, 6), "🌱 Бомж"
    elif "Бронза" in text:
        cost, gift_chance, star_range, case_name = 15, 1, (3, 20), "🥉 Бронза"
    elif "Серебро" in text:
        cost, gift_chance, star_range, case_name = 50, 3, (10, 70), "🥈 Серебро"
    elif "Золото" in text:
        cost, gift_chance, star_range, case_name = 120, 6, (30, 160), "🥇 Золото"
    elif "Элитный" in text:
        cost, gift_chance, star_range, case_name = 250, 10, (70, 330), "💎 Элитный"
    else:
        cost, gift_chance, star_range, case_name = 500, 15, (150, 700), "👑 СУПЕР-ИМБА"

    user_id = message.from_user.id
    stars, _ = get_user(user_id, message.from_user.username or "Игрок")

    if stars < cost:
        await message.answer(f"❌ Недостаточно звезд! Этот кейс стоит {cost} ⭐️.")
        return

    update_balance(user_id, -cost)
    roll = random.randint(1, 100)

    if roll <= gift_chance:
        gift = random.choice(GIFTS)
        await message.answer(
            f"🎊 <b>ОБОЖЕМОЙ! УЛЬТРА ДРОП!</b>\nИз кейса {case_name} тебе выпал Telegram-подарок: <b>{gift}</b>!",
            parse_mode="HTML")
        try:
            await bot.send_message(ADMIN_ID,
                                   f"🚨 <b>ВЫИГРЫШ ПОДАРКА!</b>\nЮзер: @{message.from_user.username}\nКейс: {case_name}\nПриз: <b>{gift}</b>",
                                   parse_mode="HTML")
        except Exception:
            pass
    else:
        win_stars = random.randint(*star_range)
        update_balance(user_id, win_stars)
        status = "🔥 <b>МЕГА ОКУП!</b>" if win_stars > cost * 1.3 else "✨ <b>В ПЛЮСЕ!</b>" if win_stars > cost else "📉 <b>Минус, повезет в следующий раз!</b>"
        await message.answer(f"📦 <b>Кейс {case_name} открыт!</b>\n💰 Твой выигрыш: <b>{win_stars} ⭐️</b>\n\n{status}",
                             parse_mode="HTML")


async def main():
    print("Исправленный ИМБОВЫЙ бот-казино запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
