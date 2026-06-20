import random
from aiogram import Bot
from aiogram.types import (
    ChatMemberLeft, ChatMemberBanned,
    ChatMemberAdministrator, ChatMemberOwner
)


async def check_user_subscription(bot: Bot, user_id: int, channel_id: int) -> bool:
    """Check if user is subscribed to a channel."""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return not isinstance(member, (ChatMemberLeft, ChatMemberBanned))
    except Exception:
        return False


async def check_bot_admin(bot: Bot, channel_id: int) -> bool:
    """Check if bot is admin in channel."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=channel_id, user_id=me.id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


async def resolve_channel(bot: Bot, username: str) -> dict | None:
    """Resolve channel username to id and title."""
    try:
        chat = await bot.get_chat(username if username.startswith("@") else f"@{username}")
        return {"id": chat.id, "title": chat.title, "username": chat.username}
    except Exception:
        return None


def pick_winners(participants: list[dict], count: int) -> list[dict]:
    """Randomly pick winners from participants list."""
    count = min(count, len(participants))
    return random.sample(participants, count)


def build_slot_grid(total: int, booked: set[int]) -> list[list]:
    """Build inline keyboard grid for slots."""
    buttons = []
    row = []
    cols = 5
    for i in range(1, total + 1):
        if i in booked:
            text = f"❌ {i}"
            cb = f"slot_taken:{i}"
        else:
            text = f"{i}"
            cb = f"slot_pick:{i}"
        row.append({"text": text, "callback_data": cb})
        if len(row) == cols:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


def format_user_mention(username: str | None, full_name: str, user_id: int) -> str:
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">{full_name}</a>'


def make_deep_link(bot_username: str, payload: str) -> str:
    return f"https://t.me/{bot_username}?start={payload}"
