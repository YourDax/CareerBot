from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup, Message

from .. import db, digest, sources

router = Router()


async def _kb(uid: int) -> InlineKeyboardMarkup:
    p = await db.get_profile(uid)
    on = bool(p and p["digest"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🔎 Подобрать сейчас", callback_data="jb:now")],
        [Btn(text=f"🔔 Ежедневный дайджест: {'вкл' if on else 'выкл'}", callback_data="jb:tog")],
    ])


async def send_menu(message: Message) -> None:
    await message.answer("Вакансии и заказы по навыкам из профиля. Дайджест приходит в 11:00 МСК.",
                         reply_markup=await _kb(message.chat.id))


@router.message(Command("jobs"))
async def jobs_cmd(message: Message) -> None:
    await send_menu(message)


@router.callback_query(F.data == "jb:now")
async def on_now(cb: CallbackQuery) -> None:
    await cb.answer("Ищу…")
    uid = cb.from_user.id
    profile = await db.get_profile(uid)
    skills = digest.parse_skills(profile["skills"]) if profile else []
    if not skills:
        await cb.message.answer("Добавь навыки в профиле.")
        return
    await cb.bot.send_chat_action(cb.message.chat.id, "typing")
    items = await digest.pick_jobs(uid, skills, await sources.fetch_all(skills))
    if not items:
        await cb.message.answer("Новых подходящих вакансий нет.")
        return
    await digest.send_items(cb.bot, uid, items)


@router.callback_query(F.data == "jb:tog")
async def on_toggle(cb: CallbackQuery) -> None:
    p = await db.get_profile(cb.from_user.id)
    if not p:
        await cb.answer("Сначала заполни профиль")
        return
    await db.set_digest(cb.from_user.id, not p["digest"])
    await cb.message.edit_reply_markup(reply_markup=await _kb(cb.from_user.id))
    await cb.answer("Готово")
