import random
from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup, Message

from .. import db, sqlcheck
from ..interview_data import BY_ID, QUESTIONS, TOPICS

router = Router()

TITLES = {**TOPICS, "mix": "Микс"}
LETTERS = "ABCD"


class Interview(StatesGroup):
    sql = State()


def _kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def _next_btn(topic: str) -> Btn:
    return Btn(text="➡ Следующий вопрос", callback_data=f"iv:n:{topic}")


async def send_menu(message: Message) -> None:
    await message.answer(
        "Мок-интервью. Выбери тему: вопросы подбираются так, чтобы сначала шли новые, затем те, где была ошибка.",
        reply_markup=_kb(
            [Btn(text="Python", callback_data="iv:t:py"), Btn(text="SQL", callback_data="iv:t:sql")],
            [Btn(text="Аналитика", callback_data="iv:t:an"), Btn(text="Микс", callback_data="iv:t:mix")],
            [Btn(text="📊 Прогресс", callback_data="iv:p")],
        ),
    )


async def pick(uid: int, topic: str) -> dict:
    pool = [q for q in QUESTIONS if topic == "mix" or q["topic"] == topic]
    progress = await db.interview_progress(uid)
    new = [q for q in pool if q["id"] not in progress]
    if new:
        return random.choice(new)
    wrong = [q for q in pool if not progress[q["id"]]["last_ok"]]
    if wrong:
        return random.choice(wrong)
    return min(pool, key=lambda q: progress[q["id"]]["last_at"])


def render(q: dict) -> str:
    text = f"<b>{TITLES[q['topic']]}</b>\n\n{escape(q['q'])}"
    if q.get("code"):
        text += f"\n\n<pre>{escape(q['code'])}</pre>"
    if q["type"] == "choice":
        text += "\n\n" + "\n".join(f"{LETTERS[i]}) {escape(o)}" for i, o in enumerate(q["options"]))
    elif q["type"] == "sql":
        text += f"\n\nСхема:\n<pre>{escape(sqlcheck.SCHEMA_DOC)}</pre>\nПришли SQL-запрос одним сообщением (SQLite)."
    return text


async def send_question(message: Message, uid: int, topic: str, state: FSMContext) -> None:
    q = await pick(uid, topic)
    await state.clear()
    if q["type"] == "choice":
        row = [Btn(text=LETTERS[i], callback_data=f"iv:c:{q['id']}:{i}:{topic}") for i in range(len(q["options"]))]
        kb = _kb(row, [Btn(text="⏭ Пропустить", callback_data=f"iv:n:{topic}")])
    elif q["type"] == "open":
        kb = _kb([Btn(text="Показать ответ", callback_data=f"iv:s:{q['id']}:{topic}")])
    else:
        await state.set_state(Interview.sql)
        await state.update_data(qid=q["id"], topic=topic)
        kb = _kb([Btn(text="Показать решение", callback_data=f"iv:s:{q['id']}:{topic}"),
                  Btn(text="⏭ Пропустить", callback_data=f"iv:n:{topic}")])
    await message.answer(render(q), parse_mode="HTML", reply_markup=kb)


async def _strip_buttons(cb: CallbackQuery) -> None:
    with suppress(TelegramBadRequest):
        await cb.message.edit_reply_markup(reply_markup=None)


@router.message(Command("interview"))
async def interview_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_menu(message)


@router.callback_query(F.data.startswith("iv:t:") | F.data.startswith("iv:n:"))
async def on_topic(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _strip_buttons(cb)
    await send_question(cb.message, cb.from_user.id, cb.data.split(":")[2], state)


@router.callback_query(F.data.startswith("iv:c:"))
async def on_choice(cb: CallbackQuery) -> None:
    _, _, qid, idx, topic = cb.data.split(":")
    q = BY_ID.get(qid)
    if not q:
        await cb.answer("Вопрос не найден")
        return
    await cb.answer()
    await _strip_buttons(cb)
    ok = int(idx) == q["answer"]
    await db.record_answer(cb.from_user.id, qid, ok)
    right = f"{LETTERS[q['answer']]}) {escape(q['options'][q['answer']])}"
    head = "✅ Верно!" if ok else f"❌ Неверно. Правильный ответ: {right}"
    await cb.message.answer(f"{head}\n\n{escape(q['explain'])}", parse_mode="HTML", reply_markup=_kb([_next_btn(topic)]))


@router.callback_query(F.data.startswith("iv:s:"))
async def on_show(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, qid, topic = cb.data.split(":")
    q = BY_ID.get(qid)
    if not q:
        await cb.answer("Вопрос не найден")
        return
    await cb.answer()
    await _strip_buttons(cb)
    if q["type"] == "open":
        kb = _kb([Btn(text="✅ Знал", callback_data=f"iv:r:{qid}:2:{topic}"),
                  Btn(text="🤔 Частично", callback_data=f"iv:r:{qid}:1:{topic}"),
                  Btn(text="❌ Не знал", callback_data=f"iv:r:{qid}:0:{topic}")])
        await cb.message.answer(f"<b>Ключевые пункты ответа</b>\n\n{escape(q['answer'])}\n\nКак ты ответил?",
                                parse_mode="HTML", reply_markup=kb)
    else:  # sql: показ решения засчитывается как неудача
        await state.clear()
        await db.record_answer(cb.from_user.id, qid, False)
        await cb.message.answer(f"<b>Решение</b>\n<pre>{escape(q['ref'])}</pre>", parse_mode="HTML",
                                reply_markup=_kb([_next_btn(topic)]))


@router.callback_query(F.data.startswith("iv:r:"))
async def on_rate(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, qid, score, topic = cb.data.split(":")
    await cb.answer("Записано")
    await _strip_buttons(cb)
    await db.record_answer(cb.from_user.id, qid, score == "2")
    await send_question(cb.message, cb.from_user.id, topic, state)


@router.message(Interview.sql, F.text, ~F.text.startswith("/"))
async def on_sql(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    q = BY_ID.get(data.get("qid"))
    if not q:
        await state.clear()
        return
    ok, feedback = sqlcheck.check(message.text, q["ref"])
    topic = data.get("topic", "sql")
    if ok:
        await state.clear()
        await db.record_answer(message.from_user.id, q["id"], True)
        await message.answer(f"✅ Верно! {feedback}\n\nЭталонное решение:\n<pre>{escape(q['ref'])}</pre>",
                             parse_mode="HTML", reply_markup=_kb([_next_btn(topic)]))
    else:
        await message.answer(f"❌ {escape(feedback)}\n\nПопробуй ещё раз или открой решение.", parse_mode="HTML",
                             reply_markup=_kb([Btn(text="Показать решение", callback_data=f"iv:s:{q['id']}:{topic}"),
                                               Btn(text="⏭ Пропустить", callback_data=f"iv:n:{topic}")]))


@router.callback_query(F.data == "iv:p")
async def on_progress(cb: CallbackQuery) -> None:
    await cb.answer()
    progress = await db.interview_progress(cb.from_user.id)
    lines = []
    for code, title in TOPICS.items():
        ids = [q["id"] for q in QUESTIONS if q["topic"] == code]
        seen = [i for i in ids if i in progress]
        right = sum(1 for i in seen if progress[i]["last_ok"])
        lines.append(f"<b>{title}</b>: пройдено {len(seen)} из {len(ids)}, последний ответ верный в {right}")
    total = sum(r["attempts"] for r in progress.values())
    lines.append(f"\nВсего попыток: {total}")
    await cb.message.answer("\n".join(lines), parse_mode="HTML")
