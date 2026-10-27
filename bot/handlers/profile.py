from html import escape

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from .. import db
from ..config import PORTFOLIO_URL, WEBAPP_URL

router = Router()


class ProfileForm(StatesGroup):
    full_name = State()
    title = State()
    skills = State()
    about = State()


@router.message(Command("cancel"), StateFilter("*"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


async def show_profile(message: Message) -> None:
    p = await db.get_profile(message.chat.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="pf:edit")],
        [InlineKeyboardButton(text="📱 Открыть в приложении", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="🌐 Портфолио-сайт", url=PORTFOLIO_URL)],
    ])
    if not p:
        await message.answer("Профиль пуст.", reply_markup=kb)
        return
    await message.answer(
        f"<b>{escape(p['full_name'])}</b> — {escape(p['title'])}\n"
        f"<b>Навыки:</b> {escape(p['skills'])}\n\n{escape(p['about'])}",
        parse_mode="HTML", reply_markup=kb,
    )


async def start_form(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileForm.full_name)
    await message.answer("Как тебя зовут? (/cancel — отмена)")


@router.callback_query(F.data == "pf:edit")
async def on_edit(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await start_form(cb.message, state)


@router.message(ProfileForm.full_name)
async def p_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=message.text)
    await state.set_state(ProfileForm.title)
    await message.answer("Желаемая должность?")


@router.message(ProfileForm.title)
async def p_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    await state.set_state(ProfileForm.skills)
    await message.answer("Навыки через запятую (по ним ищутся вакансии).")


@router.message(ProfileForm.skills)
async def p_skills(message: Message, state: FSMContext) -> None:
    await state.update_data(skills=message.text)
    await state.set_state(ProfileForm.about)
    await message.answer("Коротко о себе и опыте.")


@router.message(ProfileForm.about)
async def p_about(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db.save_profile(message.from_user.id, data["full_name"], data["title"], data["skills"], message.text)
    await state.clear()
    await message.answer("Профиль сохранён.")
    await show_profile(message)
