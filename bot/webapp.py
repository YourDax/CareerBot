import hashlib
import hmac
import json
import time
from datetime import datetime
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db, digest, portfolio, sources
from .config import BOT_TOKEN, OWNER_ID
from .webapp_html import INDEX_HTML

router = APIRouter()


def current_user(x_init_data: str = Header(default="")) -> int:
    """Проверка подписи Telegram WebApp initData и что это владелец бота."""
    data = dict(parse_qsl(x_init_data, keep_blank_values=True))
    received = data.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(calc, received):
        raise HTTPException(status_code=401)
    try:
        fresh = time.time() - int(data.get("auth_date", "0")) < 86400
        user_id = json.loads(data.get("user", "{}")).get("id")
    except (ValueError, TypeError):
        raise HTTPException(status_code=401)
    if not fresh:
        raise HTTPException(status_code=401)
    if not OWNER_ID or user_id != OWNER_ID:
        raise HTTPException(status_code=403)
    return user_id


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _dict(row) -> dict:
    return {k: _iso(v) for k, v in dict(row).items()}


class ApplyIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    position: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    remind_days: int = Field(default=7, ge=1, le=90)


class StatusIn(BaseModel):
    id: int
    status: str


class ProjectIn(BaseModel):
    project: str = Field(min_length=1, max_length=100)


class IncomeIn(ProjectIn):
    amount: float = Field(gt=0, lt=1e12)


class ProfileIn(BaseModel):
    full_name: str = Field(max_length=200)
    title: str = Field(max_length=200)
    skills: str = Field(max_length=1000)
    about: str = Field(max_length=3000)


class DigestIn(BaseModel):
    enabled: bool


@router.get("/app", response_class=HTMLResponse)
async def app_page():
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-store"})


@router.get("/api/app/state")
async def state(uid: int = Depends(current_user)):
    await db.ensure()
    profile = await db.get_profile(uid)
    active = await db.active_entry(uid)
    return {
        "profile": _dict(profile) if profile else None,
        "apps": [_dict(r) for r in await db.list_applications(uid)],
        "timer": _dict(active) if active else None,
        "recent_projects": [r["project"] for r in await db.recent_projects(uid, 10)],
        "stats": await db.project_stats(uid),
        "statuses": db.STATUSES,
    }


@router.post("/api/app/apply")
async def apply(body: ApplyIn, uid: int = Depends(current_user)):
    await db.ensure()
    url = body.url.strip() if body.url and body.url.strip().startswith(("http://", "https://")) else None
    return {"id": await db.add_application(uid, body.company.strip(), body.position.strip(), url, body.remind_days)}


@router.post("/api/app/status")
async def status(body: StatusIn, uid: int = Depends(current_user)):
    await db.ensure()
    if not await db.get_application(uid, body.id) or not await db.set_status(uid, body.id, body.status):
        raise HTTPException(status_code=404)
    return {"ok": True}


@router.post("/api/app/timer/start")
async def timer_start(body: ProjectIn, uid: int = Depends(current_user)):
    await db.ensure()
    if await db.active_entry(uid):
        raise HTTPException(status_code=409, detail="Таймер уже идёт")
    await db.start_entry(uid, body.project.strip())
    return {"ok": True}


@router.post("/api/app/timer/stop")
async def timer_stop(uid: int = Depends(current_user)):
    await db.ensure()
    active = await db.active_entry(uid)
    if active:
        await db.stop_entry(active["id"])
    return {"ok": True}


@router.post("/api/app/income")
async def income(body: IncomeIn, uid: int = Depends(current_user)):
    await db.ensure()
    await db.add_income(uid, body.project.strip(), body.amount)
    return {"ok": True}


@router.post("/api/app/profile")
async def save_profile(body: ProfileIn, uid: int = Depends(current_user)):
    await db.ensure()
    await db.save_profile(uid, body.full_name.strip(), body.title.strip(), body.skills.strip(), body.about.strip())
    return {"ok": True}


@router.post("/api/app/digest")
async def set_digest(body: DigestIn, uid: int = Depends(current_user)):
    await db.ensure()
    await db.set_digest(uid, body.enabled)
    return {"ok": True}


@router.get("/api/app/jobs")
async def jobs(uid: int = Depends(current_user)):
    await db.ensure()
    profile = await db.get_profile(uid)
    skills = digest.parse_skills(profile["skills"]) if profile else []
    if not skills:
        return []
    items = await digest.pick_jobs(uid, skills, await sources.fetch_all(skills), limit=25)
    return [
        {"title": j.title, "company": j.company, "source": sources.SOURCE_NAMES[j.source], "url": j.url,
         "hits": hits, "freelance": j.freelance}
        for j, hits in items
    ]


@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page():
    """Публичная страница: без авторизации, данные только из публичного GitHub."""
    try:
        profile, repos = await portfolio.fetch()
    except Exception:
        return HTMLResponse("<h1>Портфолио временно недоступно</h1><p>Не удалось получить данные GitHub, попробуй позже.</p>",
                            status_code=503, headers={"Cache-Control": "no-store"})
    html = portfolio.render(profile, portfolio.select_repos(repos, profile.get("login", "")))
    return HTMLResponse(html, headers={"Cache-Control": "public, s-maxage=1800, stale-while-revalidate=86400"})
