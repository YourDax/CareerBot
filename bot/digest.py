import asyncio
import re
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot

from . import db, sources
from .sources import Job

MAX_AGE = timedelta(days=7)
PER_USER = 10


def parse_skills(raw: str | None) -> list[str]:
    skills = [s.strip() for s in re.split(r"[,;\n]+", raw or "")]
    return [s for s in skills if len(s) >= 2][:10]


def matches(job: Job, skills: list[str]) -> list[str]:
    hay = f"{job.title} {job.text}".lower()
    return [s for s in skills if re.search(rf"(?<!\w){re.escape(s.lower())}(?!\w)", hay)]


async def pick_jobs(user_id: int, skills: list[str], jobs: list[Job], limit: int = PER_USER):
    """Свежие вакансии, совпавшие с навыками и ещё не показанные пользователю."""
    now = datetime.now(timezone.utc)
    scored = []
    for job in jobs:
        if job.published and now - job.published > MAX_AGE:
            continue
        hits = matches(job, skills)
        if hits:
            scored.append((job, hits))
    seen = await db.seen_keys(user_id, [j.key for j, _ in scored])
    fresh = [(j, h) for j, h in scored if j.key not in seen]
    fresh.sort(key=lambda p: (len(p[1]), p[0].published or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return fresh[:limit]


def render(items) -> list[str]:
    """HTML-сообщения не длиннее лимита Telegram."""
    messages, current = [], ""
    for job, hits in items:
        kind = "фриланс" if job.freelance else "вакансия"
        company = f"{escape(job.company)} · " if job.company else ""
        block = (
            f"<b>{escape(job.title[:150])}</b>\n"
            f"{company}{sources.SOURCE_NAMES[job.source]} · {kind}\n"
            f"Совпало: {escape(', '.join(hits))}\n{escape(job.url)}\n\n"
        )
        if len(current) + len(block) > 3800:
            messages.append(current)
            current = ""
        current += block
    if current:
        messages.append(current)
    return messages


async def send_items(bot: Bot, user_id: int, items) -> None:
    for text in render(items):
        await bot.send_message(user_id, text, parse_mode="HTML", disable_web_page_preview=True)
        await asyncio.sleep(0.05)
    await db.mark_seen(user_id, [j.key for j, _ in items])


async def send_digests(bot: Bot) -> int:
    users = {u["user_id"]: parse_skills(u["skills"]) for u in await db.digest_users()}
    users = {uid: sk for uid, sk in users.items() if sk}
    if not users:
        return 0
    all_skills = list(dict.fromkeys(s for sk in users.values() for s in sk))
    jobs = await sources.fetch_all(all_skills)
    sent = 0
    for uid, skills in users.items():
        items = await pick_jobs(uid, skills, jobs)
        if items:
            await send_items(bot, uid, items)
            sent += 1
    await db.cleanup_seen()
    return sent
