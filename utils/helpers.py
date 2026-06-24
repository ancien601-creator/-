import random
from aiogram import Bot
from aiogram.types import ChatMemberLeft, ChatMemberBanned, ChatMemberAdministrator, ChatMemberOwner


async def check_user_subscription(bot: Bot, user_id: int, channel_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return not isinstance(member, (ChatMemberLeft, ChatMemberBanned))
    except Exception:
        return False


async def check_bot_admin(bot: Bot, channel_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=channel_id, user_id=me.id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


async def resolve_channel(bot: Bot, username: str) -> dict | None:
    try:
        chat = await bot.get_chat(username if username.startswith("@") else f"@{username}")
        return {"id": chat.id, "title": chat.title, "username": chat.username}
    except Exception:
        return None


def pick_winners(participants: list[dict], count: int) -> list[dict]:
    count = min(count, len(participants))
    return random.sample(participants, count)


def format_user_mention(username: str | None, full_name: str, user_id: int) -> str:
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">{full_name}</a>'


def make_deep_link(bot_username: str, payload: str) -> str:
    return f"https://t.me/{bot_username}?start={payload}"
