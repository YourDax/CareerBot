import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

import aiohttp
from defusedxml import ElementTree as ET

from .config import HH_TOKEN

log = logging.getLogger(__name__)

UA = "CareerBot/1.0 (personal job digest)"
TIMEOUT = aiohttp.ClientTimeout(total=15)
TAG_RE = re.compile(r"<[^>]+>")

SOURCE_NAMES = {
    "habr": "Хабр Карьера",
    "hh": "hh.ru",
    "remotive": "Remotive",
    "remoteok": "RemoteOK",
    "fl": "FL.ru",
}


@dataclass
class Job:
    key: str  # "источник:id", уникален
    source: str
    title: str
    company: str
    url: str
    text: str
    published: datetime | None
    freelance: bool = False


def _clean(text: str, limit: int = 1500) -> str:
    return unescape(TAG_RE.sub(" ", text or "")).strip()[:limit]


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _rss_date(value: str | None) -> datetime | None:
    try:
        return _utc(parsedate_to_datetime(value)) if value else None
    except (TypeError, ValueError):
        return None


def _iso_date(value: str | None) -> datetime | None:
    try:
        return _utc(datetime.fromisoformat(value)) if value else None
    except ValueError:
        return None


async def _get(session: aiohttp.ClientSession, url: str, **kwargs) -> bytes | None:
    try:
        async with session.get(url, **kwargs) as resp:
            resp.raise_for_status()
            return await resp.read()
    except Exception as exc:  # источник недоступен — остальные продолжают работать
        log.warning("source %s failed: %s", url.split("?")[0], exc)
        return None


def _rss_items(data: bytes):
    try:
        return ET.fromstring(data).iter("item")
    except Exception as exc:
        log.warning("bad rss: %s", exc)
        return []


async def fetch_habr(session, skills: list[str]) -> list[Job]:
    jobs = []
    for body in await asyncio.gather(
        *[_get(session, "https://career.habr.com/vacancies/rss", params={"q": s, "type": "all"}) for s in skills]
    ):
        for it in _rss_items(body or b""):
            guid = it.findtext("guid") or it.findtext("link") or ""
            jobs.append(Job(f"habr:{guid}", "habr", it.findtext("title", "").strip(), it.findtext("author", ""),
                            it.findtext("link", ""), _clean(it.findtext("description", "")),
                            _rss_date(it.findtext("pubDate"))))
    return jobs


async def fetch_fl(session, skills: list[str]) -> list[Job]:
    body = await _get(session, "https://www.fl.ru/rss/all.xml")
    jobs = []
    for it in _rss_items(body or b""):
        link = it.findtext("link", "")
        text = f"{_clean(it.findtext('description', ''))} {it.findtext('category', '')}"
        jobs.append(Job(f"fl:{link}", "fl", it.findtext("title", "").strip(), "", link, text,
                        _rss_date(it.findtext("pubDate")), freelance=True))
    return jobs


async def fetch_remotive(session, skills: list[str]) -> list[Job]:
    jobs = []
    for body in await asyncio.gather(
        *[_get(session, "https://remotive.com/api/remote-jobs", params={"search": s, "limit": 30}) for s in skills]
    ):
        if not body:
            continue
        try:
            items = (await asyncio.to_thread(_json, body)).get("jobs", [])
        except ValueError:
            continue
        for j in items:
            text = f"{j.get('category', '')} {' '.join(j.get('tags') or [])} {_clean(j.get('description', ''))}"
            jobs.append(Job(f"remotive:{j['id']}", "remotive", j.get("title", ""), j.get("company_name", ""),
                            j.get("url", ""), text, _iso_date(j.get("publication_date")),
                            freelance=j.get("job_type") == "freelance"))
    return jobs


async def fetch_remoteok(session, skills: list[str]) -> list[Job]:
    body = await _get(session, "https://remoteok.com/api")
    if not body:
        return []
    try:
        items = await asyncio.to_thread(_json, body)
    except ValueError:
        return []
    jobs = []
    for j in items:
        if not isinstance(j, dict) or "position" not in j:  # первый элемент — юридическая заметка
            continue
        text = f"{' '.join(j.get('tags') or [])} {_clean(j.get('description', ''))}"
        jobs.append(Job(f"remoteok:{j['id']}", "remoteok", j["position"], j.get("company", ""),
                        j.get("url", ""), text, _iso_date(j.get("date"))))
    return jobs


async def fetch_hh(session, skills: list[str]) -> list[Job]:
    if not HH_TOKEN:  # hh.ru закрыл анонимный API: нужен токен приложения
        return []
    headers = {"Authorization": f"Bearer {HH_TOKEN}", "HH-User-Agent": UA}
    jobs = []
    for body in await asyncio.gather(
        *[_get(session, "https://api.hh.ru/vacancies",
               params={"text": s, "per_page": 30, "order_by": "publication_time"}, headers=headers)
          for s in skills]
    ):
        if not body:
            continue
        try:
            items = (await asyncio.to_thread(_json, body)).get("items", [])
        except ValueError:
            continue
        for j in items:
            snip = j.get("snippet") or {}
            jobs.append(Job(f"hh:{j['id']}", "hh", j.get("name", ""), (j.get("employer") or {}).get("name", ""),
                            j.get("alternate_url", ""),
                            _clean(f"{snip.get('requirement', '')} {snip.get('responsibility', '')}"),
                            _iso_date(j.get("published_at"))))
    return jobs


def _json(body: bytes):
    import json

    return json.loads(body)


async def fetch_all(skills: list[str]) -> list[Job]:
    skills = skills[:10]
    async with aiohttp.ClientSession(timeout=TIMEOUT, headers={"User-Agent": UA}) as session:
        results = await asyncio.gather(
            fetch_habr(session, skills), fetch_fl(session, skills), fetch_remotive(session, skills),
            fetch_remoteok(session, skills), fetch_hh(session, skills),
        )
    unique: dict[str, Job] = {}
    for batch in results:
        for job in batch:
            if job.url and job.title:
                unique.setdefault(job.key, job)
    return list(unique.values())
