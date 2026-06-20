from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from db.database import upsert_admin


class AdminMiddleware(BaseMiddleware):
    """Upserts admin record on every interaction."""

    async def __call__(
        self,
        handler: Callable[[Any, dict], Awaitable[Any]],
        event: Any,
        data: dict,
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            await upsert_admin(
                user_id=user.id,
                username=user.username or ""
            )

        return await handler(event, data)
