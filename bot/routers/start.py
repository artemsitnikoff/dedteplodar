"""Start command and help."""
import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

logger = logging.getLogger("teplodarbot")
router = Router()

WELCOME = (
    "👋 Привет! Я консультант магазина <b>Теплодар</b>.\n\n"
    "Задайте любой вопрос о наших печах, котлах и каминах:\n"
    "• характеристики и сравнения моделей\n"
    "• монтаж и установка\n"
    "• доставка, оплата, гарантия\n"
    "• адреса магазинов в вашем городе\n\n"
    "Просто напишите свой вопрос ✍️"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(WELCOME)
