from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import db

router = Router()

QUICK = [("replied", "Ответили"), ("interview", "Собес"), ("offer", "Оффер"), ("rejected", "Отказ")]


class ApplyForm(StatesGroup):
    company = State()
    position = State()
    url = State()
    remind = State()


def card(r) -> str:
    url = f"\n{escape(r['url'])}" if r["url"] else ""
    return (f"#{r['id']} <b>{escape(r['company'])}</b> — {escape(r['position'])}\n"
            f"{db.STATUSES[r['status']]} · {r['applied_at'].strftime('%d.%m')}{url}")


def card_kb(r) -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(text=t, callback_data=f"st:{r['id']}:{s}") for s, t in QUICK if s != r["status"]]
    return InlineKeyboardMarkup(inline_keyboard=[btns[i:i + 2] for i in range(0, len(btns), 2)])


async def send_apps(message: Message) -> None:
    rows = await db.list_applications(message.chat.id)
    add = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить отклик", callback_data="ap:new")]])
    await message.answer("Отклики" if rows else "Откликов пока нет.", reply_markup=add)
    for r in rows[:8]:
        await message.answer(card(r), parse_mode="HTML", reply_markup=card_kb(r), disable_web_page_preview=True)


@router.message(Command("apps"))
async def apps_cmd(message: Message) -> None:
    await send_apps(message)


@router.callback_query(F.data == "ap:new")
async def on_new(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(ApplyForm.company)
    await cb.message.answer("Компания? (/cancel — отмена)")


@router.callback_query(F.data.startswith("st:"))
async def on_status(cb: CallbackQuery) -> None:
    _, app_id, status = cb.data.split(":")
    r = await db.get_application(cb.from_user.id, int(app_id))
    if not r:
        await cb.answer("Отклик не найден")
        return
    await db.set_status(cb.from_user.id, r["id"], status)
    r = await db.get_application(cb.from_user.id, r["id"])
    await cb.message.edit_text(card(r), parse_mode="HTML", reply_markup=card_kb(r), disable_web_page_preview=True)
    await cb.answer("Готово")


@router.message(ApplyForm.company)
async def a_company(message: Message, state: FSMContext) -> None:
    await state.update_data(company=message.text)
    await state.set_state(ApplyForm.position)
    await message.answer("Позиция?")


@router.message(ApplyForm.position)
async def a_position(message: Message, state: FSMContext) -> None:
    await state.update_data(position=message.text)
    await state.set_state(ApplyForm.url)
    await message.answer("Ссылка на вакансию (или «-»).")


@router.message(ApplyForm.url)
async def a_url(message: Message, state: FSMContext) -> None:
    await state.update_data(url=None if message.text.strip() == "-" else message.text.strip())
    await state.set_state(ApplyForm.remind)
    await message.answer("Через сколько дней напомнить, если не ответят? (число, по умолчанию 7)")


@router.message(ApplyForm.remind)
async def a_remind(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    days = int(text) if text.isdigit() and 0 < int(text) <= 90 else 7
    data = await state.get_data()
    app_id = await db.add_application(message.from_user.id, data["company"], data["position"], data["url"], days)
    await state.clear()
    r = await db.get_application(message.from_user.id, app_id)
    await message.answer(f"Сохранено, напомню через {days} дн.\n\n{card(r)}", parse_mode="HTML",
                         reply_markup=card_kb(r), disable_web_page_preview=True)
