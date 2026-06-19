from aiogram import Router, Bot, F
from aiogram.types import Message
from aiogram.filters import Command, CommandObject

from database import Database

router = Router()

@router.message(Command("start"))
async def handle_client_start(message: Message, command: CommandObject, bot: Bot):
    args = command.args
    # Если аргументов нет или команда пришла не по ссылке на конкурс — переадресуем в админку/главное меню
    if not args or not args.startswith("contest_"):
        return

    try:
        contest_id = int(args.split("_")[1])
    except (ValueError, IndexError):
        await message.answer("❌ Некорректная ссылка на конкурс.")
        return

    contest = await Database.get_contest(contest_id)
    if not contest:
        await message.answer("❌ Конкурс не найден.")
        return

    if contest['status'] == 'finished':
        await message.answer("😔 К сожалению, этот розыгрыш уже завершен.")
        return

    # Собираем список всех каналов для проверки (Главный канал + Спонсоры)
    sponsors = await Database.get_sponsors(contest_id)
    channels_to_check = [{"id": contest['chat_id'], "username": "Основной канал"}]
    for sp in sponsors:
        channels_to_check.append({"id": sp[0], "username": sp[1]})

    not_subscribed = []
    
    for channel in channels_to_check:
        try:
            member = await bot.get_chat_member(chat_id=channel['id'], user_id=message.from_user.id)
            if member.status in ["left", "kicked"]:
                not_subscribed.append(channel)
        except Exception:
            # На случай, если бот потерял доступ к какому-то каналу
            not_subscribed.append(channel)

    if not_subscribed:
        links = []
        for ch in not_subscribed:
            if str(ch['username']).startswith("@"):
                links.append(f"🔗 {ch['username']}")
            else:
                links.append(f"🔗 Канал [ID: {ch['id']}]")
                
        channels_list = "\n".join(links)
        await message.answer(
            f"⚠️ Вы не можете участвовать, так как не подписались на обязательные каналы:\n\n"
            f"{channels_list}\n\n"
            f"Подпишитесь и нажмите на кнопку в канале снова!"
        )
    else:
        is_added = await Database.add_participant(message.from_user.id, contest_id)
        if is_added:
            await message.answer("🎉 Вы успешно участвуете в розыгрыше! Желаем удачи!")
        else:
            await message.answer("ℹ️ Вы уже являетесь участником этого розыгрыша.")
