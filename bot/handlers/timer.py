from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup, Message

from .. import db

router = Router()


class TimerForm(StatesGroup):
    project = State()
    income = State()


def _fmt(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    return f"{h}:{rem // 60:02d}"


async def view(uid: int):
    active = await db.active_entry(uid)
    if active:
        elapsed = (db.now() - active["started_at"]).total_seconds()
        return (f"Идёт таймер: <b>{escape(active['project'])}</b> — {_fmt(elapsed)}",
                InlineKeyboardMarkup(inline_keyboard=[[Btn(text="⏹ Стоп", callback_data="tm:stop")]]))
    recent = await db.recent_projects(uid)
    rows = [[Btn(text=f"▶ {r['project'][:20]}", callback_data=f"tm:r:{r['id']}") for r in recent[i:i + 2]]
            for i in range(0, len(recent), 2)]
    rows.append([Btn(text="➕ Новый проект", callback_data="tm:new"), Btn(text="📊 Статистика", callback_data="tm:stats")])
    rows.append([Btn(text="💰 Записать доход", callback_data="tm:inc")])
    return "Таймер остановлен. Выбери проект:", InlineKeyboardMarkup(inline_keyboard=rows)


async def send_view(message: Message) -> None:
    text, kb = await view(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def stats_text(uid: int) -> str:
    rows = await db.project_stats(uid)
    if not rows:
        return "Данных пока нет."
    lines = []
    for r in rows:
        rate = f"{r['rate']:.0f}/ч" if r["rate"] is not None else "—"
        lines.append(f"<b>{escape(r['project'])}</b>: {r['hours']:.1f} ч · доход {r['earned']:g} · {rate}")
    return "\n".join(lines)


async def _start(message: Message, project: str) -> None:
    await db.start_entry(message.chat.id, project)
    await send_view(message)


@router.callback_query(F.data.startswith("tm:r:"))
async def on_restart(cb: CallbackQuery) -> None:
    entry = await db.get_entry(cb.from_user.id, int(cb.data.split(":")[2]))
    if not entry or await db.active_entry(cb.from_user.id):
        await cb.answer("Таймер уже идёт или проект не найден")
        return
    await db.start_entry(cb.from_user.id, entry["project"])
    text, kb = await view(cb.from_user.id)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer("Запущен")


@router.callback_query(F.data == "tm:stop")
async def on_stop(cb: CallbackQuery) -> None:
    active = await db.active_entry(cb.from_user.id)
    if active:
        await db.stop_entry(active["id"])
    text, kb = await view(cb.from_user.id)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer("Остановлен")


@router.callback_query(F.data == "tm:new")
async def on_new(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(TimerForm.project)
    await cb.message.answer("Название проекта? (/cancel — отмена)")


@router.callback_query(F.data == "tm:stats")
async def on_stats(cb: CallbackQuery) -> None:
    await cb.answer()
    await cb.message.answer(await stats_text(cb.from_user.id), parse_mode="HTML")


@router.callback_query(F.data == "tm:inc")
async def on_income(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(TimerForm.income)
    await cb.message.answer("Напиши проект и сумму, например: Лендинг 15000 (/cancel — отмена)")


@router.message(TimerForm.project)
async def f_project(message: Message, state: FSMContext) -> None:
    await state.clear()
    if await db.active_entry(message.from_user.id):
        await message.answer("Таймер уже идёт, сначала останови его.")
        return
    await _start(message, message.text.strip()[:100])


@router.message(TimerForm.income)
async def f_income(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").rsplit(maxsplit=1)
    try:
        project, amount = parts[0].strip(), float(parts[1].replace(",", "."))
    except (IndexError, ValueError):
        await message.answer("Формат: проект сумма, например: Лендинг 15000")
        return
    await state.clear()
    await db.add_income(message.from_user.id, project, amount)
    await message.answer(f"Записано: {amount:g} по проекту «{escape(project)}».", parse_mode="HTML")


@router.message(Command("stats"))
async def stats_cmd(message: Message) -> None:
    await message.answer(await stats_text(message.from_user.id), parse_mode="HTML")
