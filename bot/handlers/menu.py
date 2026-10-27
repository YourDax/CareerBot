from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards as kb
from . import applications, interview, jobs, profile, timer

router = Router()


@router.message(F.text == kb.BTN_APPS)
async def m_apps(message: Message, state: FSMContext) -> None:
    await state.clear()
    await applications.send_apps(message)


@router.message(F.text == kb.BTN_TIME)
async def m_time(message: Message, state: FSMContext) -> None:
    await state.clear()
    await timer.send_view(message)


@router.message(F.text == kb.BTN_JOBS)
async def m_jobs(message: Message, state: FSMContext) -> None:
    await state.clear()
    await jobs.send_menu(message)


@router.message(F.text == kb.BTN_PROFILE)
async def m_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    await profile.show_profile(message)


@router.message(F.text == kb.BTN_INTERVIEW)
async def m_interview(message: Message, state: FSMContext) -> None:
    await state.clear()
    await interview.send_menu(message)
