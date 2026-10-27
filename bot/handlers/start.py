from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards

router = Router()

TEXT = (
    "<b>CareerBot</b>\n\n"
    "Всё управляется кнопками внизу. Полный интерфейс — кнопка «Приложение».\n\n"
    "Отклики, таймер и вакансии работают и из чата, и из приложения. "
    "/cancel — отменить текущий ввод."
)


@router.message(CommandStart())
@router.message(Command("help"))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(TEXT, parse_mode="HTML", reply_markup=keyboards.main_menu())
