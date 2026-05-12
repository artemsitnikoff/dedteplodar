"""Bot and Dispatcher factory."""
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.core.config import settings


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    from bot.routers.start import router as start_router
    from bot.routers.consultant import router as consultant_router

    dp.include_routers(
        start_router,
        consultant_router,  # catch-all — must be last
    )

    return dp
