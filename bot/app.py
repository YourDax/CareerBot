from html import escape

from aiogram import Bot, Dispatcher

from . import db
from .digest import send_digests
from .handlers import applications, interview, jobs, menu, profile, start, timer
from .middleware import OwnerOnly
from .storage import PgStorage


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=PgStorage())
    dp.update.outer_middleware(OwnerOnly())
    # menu и profile первыми: кнопки меню сбрасывают ввод, а /cancel работает в любом состоянии
    dp.include_routers(menu.router, profile.router, applications.router, interview.router, jobs.router,
                       timer.router, start.router)
    return dp


async def send_due_reminders(bot: Bot) -> int:
    sent = 0
    for app in await db.due_reminders():
        await bot.send_message(
            app["user_id"],
            f"Напоминание: по отклику #{app['id']} ({escape(app['company'])} — "
            f"{escape(app['position'])}) нет ответа. Самое время написать follow-up.\n"
            f"Обновить статус: /status {app['id']} replied",
            parse_mode="HTML",
        )
        await db.mark_reminded(app["id"])
        sent += 1
    return sent


async def run_cron(bot: Bot) -> dict:
    return {"reminders": await send_due_reminders(bot), "digests": await send_digests(bot)}
