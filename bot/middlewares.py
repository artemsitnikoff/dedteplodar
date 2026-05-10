"""Bot middlewares."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("teplodarbot")


class ErrorMiddleware(BaseMiddleware):
    """Catch unhandled exceptions, log them, reply with a generic error message."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            chat_id = user_id = "?"
            if isinstance(event, Message):
                chat_id = event.chat.id
                user_id = event.from_user.id if event.from_user else "?"
            elif isinstance(event, CallbackQuery):
                chat_id = event.message.chat.id if event.message else "?"
                user_id = event.from_user.id if event.from_user else "?"

            logger.error("Unhandled error chat=%s user=%s", chat_id, user_id, exc_info=True)

            try:
                if isinstance(event, Message):
                    await event.reply("❌ Что-то пошло не так. Попробуйте ещё раз.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Произошла ошибка", show_alert=True)
            except Exception:
                pass
            return None
