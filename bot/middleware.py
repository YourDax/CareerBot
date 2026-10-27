from aiogram import BaseMiddleware

from .config import OWNER_ID


class OwnerOnly(BaseMiddleware):
    """Бот личный: апдейты от чужих пользователей отбрасываются. Без OWNER_ID не работает никто."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not OWNER_ID or user is None or user.id != OWNER_ID:
            return None
        return await handler(event, data)
