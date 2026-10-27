import hmac
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot  # noqa: E402
from aiogram.types import Update  # noqa: E402
from fastapi import FastAPI, Header, HTTPException, Request  # noqa: E402

from bot import db  # noqa: E402
from bot.app import build_dispatcher, run_cron  # noqa: E402
from bot.config import BOT_TOKEN, CRON_SECRET, WEBHOOK_SECRET  # noqa: E402
from bot.webapp import router as webapp_router  # noqa: E402

app = FastAPI()
app.include_router(webapp_router)
dp = build_dispatcher()


async def _ensure_db() -> None:
    await db.ensure()


def _same(a: str | None, b: str) -> bool:
    return bool(b) and a is not None and hmac.compare_digest(a, b)


@app.get("/")
async def health():
    return {"ok": True}


@app.post("/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if not _same(x_telegram_bot_api_secret_token, WEBHOOK_SECRET):
        raise HTTPException(status_code=403)
    await _ensure_db()
    bot = Bot(BOT_TOKEN)
    try:
        update = Update.model_validate(await request.json(), context={"bot": bot})
        await dp.feed_update(bot, update)
    finally:
        await bot.session.close()
    return {"ok": True}


@app.get("/api/cron")
async def cron(authorization: str | None = Header(default=None)):
    # Vercel Cron шлёт "Authorization: Bearer <CRON_SECRET>"
    if not _same(authorization, f"Bearer {CRON_SECRET}"):
        raise HTTPException(status_code=401)
    await _ensure_db()
    bot = Bot(BOT_TOKEN)
    try:
        return await run_cron(bot)
    finally:
        await bot.session.close()
