import random
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from database import Database
from states import CreateContest
import keyboards as kb

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Добро пожаловать в панель управления розыгрышами!", reply_markup=kb.get_main_menu())

# --- ВЕТКА «СОЗДАТЬ КОНКУРС» ---

@router.message(F.text == "🎁 Создать конкурс")
async def start_contest_creation(message: Message, state: FSMContext):
    await state.set_state(CreateContest.channel)
    await message.answer(
        "Шаг 1: Перешлите сообщение из канала, в котором планируете конкурс, "
        "или отправьте его ID / @username.\n\n"
        "Важно: Бот должен быть назначен администратором этого канала!"
    )

@router.message(CreateContest.channel)
async def process_channel(message: Message, state: FSMContext, bot: Bot):
    chat_id = None
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
    else:
        chat_id = message.text

    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
        if member.status not in ["administrator", "creator"]:
            await message.answer("Ошибка: Бот не является администратором в указанном канале. Попробуйте еще раз.")
            return
    except TelegramBadRequest:
        await message.answer("Не удалось найти канал или бот не имеет к нему доступа. Проверьте данные и права бота.")
        return

    await state.update_data(channel_id=chat_id)
    await state.set_state(CreateContest.content)
    await message.answer("Шаг 2: Отправьте текст конкурса. Вы также можете прикрепить к тексту одно фото.")

@router.message(CreateContest.content)
async def process_content(message: Message, state: FSMContext):
    text = message.html_text if message.text else message.caption
    photo_id = message.photo[-1].file_id if message.photo else None

    if not text:
        await message.answer("Пожалуйста, введите текстовое описание конкурса.")
        return

    await state.update_data(text=text, photo_id=photo_id)
    await state.set_state(CreateContest.finish_type)
    await message.answer("Шаг 3: Выберите условие завершения конкурса:", reply_markup=kb.get_finish_type_kb())

@router.callback_query(CreateContest.finish_type, F.data.startswith("finish_"))
async def process_finish_type(callback: CallbackQuery, state: FSMContext):
    await state.update_data(finish_type=callback.data)
    await state.set_state(CreateContest.winners_count)
    await callback.message.answer("Шаг 4: Укажите количество победителей (введите число):")
    await callback.answer()

@router.message(CreateContest.winners_count)
async def process_winners_count(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("Пожалуйста, введите корректное число больше нуля.")
        return

    await state.update_data(winners_count=int(message.text))
    await state.set_state(CreateContest.button_text)
    await message.answer("Шаг 5: Выберите текст для инлайн-кнопки участия под постом:", reply_markup=kb.get_preset_buttons_kb())

@router.callback_query(CreateContest.button_text, F.data.startswith("btn_"))
async def process_button_text(callback: CallbackQuery, state: FSMContext):
    btn_text = callback.data.split("_")[1]
    await state.update_data(button_text=btn_text)
    
    await state.update_data(sponsors_list=[])  # Инициализируем пустой список спонсоров
    await state.set_state(CreateContest.sponsors)
    await callback.message.answer(
        "Шаг 6: Настройка обязательных подписок.\n"
        "Вы можете добавить спонсорские каналы, на которые юзер обязан подписаться.",
        reply_markup=kb.get_sponsors_kb()
    )
    await callback.answer()

@router.callback_query(CreateContest.sponsors, F.data == "add_sponsor")
async def ask_sponsor_username(callback: CallbackQuery):
    await callback.message.answer("Отправьте @username спонсорского канала (включая @, например @my_sponsor_channel):")
    await callback.answer()

@router.message(CreateContest.sponsors)
async def process_sponsor_add(message: Message, state: FSMContext, bot: Bot):
    username = message.text.strip()
    if not username.startswith("@"):
        await message.answer("Юзернейм должен начинаться с @. Попробуйте еще раз.")
        return

    try:
        chat = await bot.get_chat(username)
        member = await bot.get_chat_member(chat_id=chat.id, user_id=bot.id)
        if member.status not in ["administrator", "creator"]:
            await message.answer("Бот должен быть администратором в этом спонсорском канале для проверки подписок! Назначьте его и отправьте юзернейм снова.")
            return
        
        data = await state.get_data()
        sponsors_list = data.get("sponsors_list", [])
        sponsors_list.append({"id": chat.id, "username": username})
        await state.update_data(sponsors_list=sponsors_list)
        
        await message.answer(f"Канал {username} успешно добавлен как спонсор!", reply_markup=kb.get_sponsors_kb())
    except Exception:
        await message.answer("Не удалось найти канал или бот не добавлен в него. Убедитесь в корректности @username.")

@router.callback_query(CreateContest.sponsors, F.data == "finish_sponsors")
async def final_publish(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    bot_user = await bot.get_me()
    
    # 1. Запись конкурса в БД
    contest_id = await Database.add_contest(
        chat_id=data['channel_id'],
        text=data['text'],
        photo_id=data['photo_id'],
        finish_type=data['finish_type'],
        winners_count=data['winners_count'],
        button_text=data['button_text']
    )
    
    # 2. Запись спонсоров в БД
    for sponsor in data['sponsors_list']:
        await Database.add_sponsor(contest_id, sponsor['id'], sponsor['username'])

    # 3. Публикация в целевой канал
    reply_markup = kb.get_participate_kb(bot_user.username, contest_id, data['button_text'])
    
    try:
        if data['photo_id']:
            msg = await bot.send_photo(chat_id=data['channel_id'], photo=data['photo_id'], caption=data['text'], reply_markup=reply_markup)
        else:
            msg = await bot.send_message(chat_id=data['channel_id'], text=data['text'], reply_markup=reply_markup)
        
        await Database.update_contest_message(contest_id, msg.message_id)
        await callback.message.answer("🎉 Конкурс успешно опубликован в канале!")
    except Exception as e:
        await callback.message.answer(f"Произошла ошибка при публикации: {e}")
    
    await state.clear()
    await callback.answer()


# --- ВЕТКА «МОИ КОНКУРСЫ» И ИТОГИ ---

@router.message(F.text == "📊 Мои конкурсы")
async def list_contests(message: Message):
    contests = await Database.get_active_contests()
    if not contests:
        await message.answer("У вас нет активных конкурсов.")
        return
    await message.answer("Выберите конкурс для управления:", reply_markup=kb.get_contests_list_kb(contests))

@router.callback_query(F.data.startswith("manage_"))
async def manage_contest(callback: CallbackQuery):
    contest_id = int(callback.data.split("_")[1])
    contest = await Database.get_contest(contest_id)
    participants = await Database.get_participants(contest_id)
    
    text = (
        f"📋 <b>Управление конкурсом #{contest['id']}</b>\n\n"
        f"Канал: {contest['chat_id']}\n"
        f"Кол-во победителей: {contest['winners_count']}\n"
        f"Участников на данный момент: {len(participants)}\n"
    )
    await callback.message.answer(text, reply_markup=kb.get_contest_manage_kb(contest_id))
    await callback.answer()

@router.callback_query(F.data.startswith("stop_"))
async def stop_contest(callback: CallbackQuery, bot: Bot):
    contest_id = int(callback.data.split("_")[1])
    contest = await Database.get_contest(contest_id)
    
    if contest['status'] == 'finished':
        await callback.message.answer("Этот конкурс уже завершен.")
        await callback.answer()
        return

    participants = await Database.get_participants(contest_id)
    if not participants:
        await callback.message.answer("В конкурсе никто не принял участие. Невозможно выбрать победителей.")
        await callback.answer()
        return

    # Выбор победителей
    winners_count = min(contest['winners_count'], len(participants))
    winners_ids = random.sample(participants, winners_count)
    
    winners_mentions = []
    for w_id in winners_ids:
        try:
            chat_member = await bot.get_chat_member(chat_id=contest['chat_id'], user_id=w_id)
            user = chat_member.user
            name = user.first_name
            winners_mentions.append(f"<a href='tg://user?id={w_id}'>{name}</a>")
        except Exception:
            winners_mentions.append(f"Пользователь ID: {w_id}")

    winners_text = "\n🎉 <b>Победители розыгрыша:</b>\n" + "\n".join(f"▫️ {m}" for m in winners_mentions)
    
    # Обновление оригинального поста в канале
    updated_text = f"{contest['text']}\n\n{winners_text}"
    try:
        if contest['photo_id']:
            await bot.edit_message_caption(chat_id=contest['chat_id'], message_id=contest['message_id'], caption=updated_text, reply_markup=None)
        else:
            await bot.edit_message_text(chat_id=contest['chat_id'], message_id=contest['message_id'], text=updated_text, reply_markup=None)
        
        await Database.close_contest(contest_id)
        await callback.message.answer("✅ Итоги подведены, пост в канале успешно обновлен!")
    except Exception as e:
        await callback.message.answer(f"Ошибка при обновлении поста в канале: {e}")

    await callback.answer()
