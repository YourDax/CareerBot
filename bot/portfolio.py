"""Портфолио-страница: данные берутся из публичного GitHub API при каждом (кешированном) запросе."""
import time
from datetime import datetime, timezone
from html import escape

import aiohttp

from . import portfolio_content as c
from .config import GITHUB_TOKEN, GITHUB_USER

TTL = 1800  # секунд: кеш в памяти экземпляра, плюс CDN-кеш Vercel через заголовки ответа
MAX_REPOS = 18
_cache: dict = {"at": 0.0, "data": None}


async def _get_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.json()


async def fetch(user: str = GITHUB_USER):
    """(profile, repos). При сбое GitHub отдаёт последние удачные данные, если они есть."""
    if _cache["data"] and time.time() - _cache["at"] < TTL:
        return _cache["data"]
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "CareerBot-portfolio"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as session:
            profile = await _get_json(session, f"https://api.github.com/users/{user}")
            repos = await _get_json(session, f"https://api.github.com/users/{user}/repos?per_page=100&sort=pushed")
    except Exception:
        if _cache["data"]:
            return _cache["data"]
        raise
    _cache.update(at=time.time(), data=(profile, repos))
    return profile, repos


def select_repos(repos: list, user: str) -> list:
    """Без форков, архивных и профильного README-репозитория. Тема `portfolio` ограничивает выбор."""
    items = [r for r in repos if not r.get("fork") and not r.get("archived") and r["name"].lower() != user.lower()]
    marked = [r for r in items if "portfolio" in (r.get("topics") or [])]
    items = marked or items
    items.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
    return items[:MAX_REPOS]


def _ago(iso: str | None) -> str:
    if not iso:
        return ""
    days = (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    if days < 1:
        return "сегодня"
    if days < 31:
        return f"{days} дн. назад"
    if days < 365:
        return f"{days // 30} мес. назад"
    return f"{days // 365} г. назад"


def _safe_url(url: str | None) -> str:
    return escape(url, quote=True) if url and url.startswith(("https://", "http://")) else "#"


CSS = """
:root{--bg:#fff;--text:#1a1a1a;--hint:#6b7280;--card:#f4f5f7;--accent:#2563eb;--border:#e5e7eb}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--text:#e8e8ea;--hint:#9ca3af;--card:#181b22;--accent:#60a5fa;--border:#262a33}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 -apple-system,system-ui,"Segoe UI",sans-serif}
main{max-width:900px;margin:0 auto;padding:40px 20px 60px}
header{display:flex;gap:20px;align-items:center;margin-bottom:28px;flex-wrap:wrap}
header img{width:96px;height:96px;border-radius:50%;border:1px solid var(--border)}
h1{margin:0 0 4px;font-size:28px}
.bio{margin:0;color:var(--hint)}
.stats{color:var(--hint);font-size:14px;margin-top:6px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 28px}
.chip{background:var(--card);border-radius:999px;padding:4px 12px;font-size:14px}
h2{font-size:20px;margin:0 0 14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.repo{display:block;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px;color:inherit;text-decoration:none}
.repo:hover{border-color:var(--accent)}
.repo b{display:block;color:var(--accent);margin-bottom:6px;word-break:break-word}
.repo p{margin:0 0 10px;font-size:14px;color:var(--hint)}
.meta{display:flex;gap:12px;flex-wrap:wrap;font-size:13px;color:var(--hint)}
section{margin:0 0 34px}
.lead{margin:0 0 22px;font-size:17px}
.tag{display:inline-block;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:2px 10px;font-size:13px;color:var(--hint);margin:0 6px 6px 0}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.btn{background:var(--accent);color:#fff;text-decoration:none;border-radius:10px;padding:8px 16px;font-size:15px}
.btn.alt{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.skills{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}
.skills h3,.exp h3{margin:0 0 8px;font-size:15px;color:var(--hint);font-weight:600}
.exp{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px}
.exp h3{color:var(--text);font-size:16px}
.exp p{margin:0 0 8px;color:var(--hint);font-size:14px}
.exp ul{margin:0;padding-left:18px;font-size:14px}
.edu{display:flex;gap:16px;margin-bottom:12px}
.edu .year{min-width:48px;color:var(--accent);font-weight:600}
.edu small{display:block;color:var(--hint)}
footer{margin-top:36px;color:var(--hint);font-size:13px}
a{color:var(--accent)}
"""


def _tags(items) -> str:
    return "".join(f'<span class="tag">{escape(t)}</span>' for t in items)


def render(profile: dict, repos: list) -> str:
    user = profile.get("login", GITHUB_USER)
    gh_url = _safe_url(profile.get("html_url") or f"https://github.com/{user}")
    cards = []
    for r in repos:
        topics = " ".join(f"#{escape(t)}" for t in (r.get("topics") or [])[:4])
        meta = [f"★ {r.get('stargazers_count', 0)}"]
        if r.get("language"):
            meta.insert(0, escape(r["language"]))
        meta.append(f"обновлён {_ago(r.get('pushed_at'))}")
        cards.append(
            f'<a class="repo" href="{_safe_url(r.get("html_url"))}" rel="noopener" target="_blank">'
            f'<b>{escape(r["name"])}</b><p>{escape(r.get("description") or "Без описания")}</p>'
            f'<div class="meta">{" · ".join(meta)}</div>'
            f'{f"<div class=meta>{topics}</div>" if topics else ""}</a>'
        )
    projects = "".join(cards) or '<p class="bio">Публичных проектов пока нет.</p>'
    skills = "".join(f"<div><h3>{escape(title)}</h3>{_tags(items)}</div>" for title, items in c.SKILLS)
    exp = "".join(
        f'<div class="exp"><h3>{escape(t)}</h3><p>{escape(d)}</p><ul>{"".join(f"<li>{escape(x)}</li>" for x in tasks)}</ul></div>'
        for t, d, tasks in c.EXPERIENCE)
    edu = "".join(
        f'<div class="edu"><div class="year">{escape(y)}</div><div><b>{escape(level)}</b><small>{escape(school)}</small>'
        f"<small>{escape(faculty)}</small></div></div>" for y, level, school, faculty in c.EDUCATION)
    langs = " · ".join(f"{escape(n)}: {escape(lvl)}" for n, lvl in c.LANGUAGES)
    desc = escape(f"{c.NAME}, {c.ROLE}. {c.ABOUT}")
    avatar = _safe_url(profile.get("avatar_url"))
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(c.NAME)} — {escape(c.ROLE)}</title>"
        f'<meta name="description" content="{desc}"><meta property="og:title" content="{escape(c.NAME)} — {escape(c.ROLE)}">'
        f'<meta property="og:description" content="{desc}">'
        f"<style>{CSS}</style></head><body><main>"
        f'<header><img src="{avatar}" alt="" width="96" height="96"><div><h1>{escape(c.NAME)}</h1>'
        f'<p class="bio">{escape(c.ROLE)}</p>'
        f'<div class="stats">{escape(c.LOCATION)} · {escape(c.STATUS)}</div>'
        f'<div class="btns"><a class="btn" href="https://t.me/{escape(c.TELEGRAM, quote=True)}" rel="noopener" target="_blank">Написать в Telegram</a>'
        f'<a class="btn alt" href="{gh_url}" rel="noopener" target="_blank">GitHub</a></div></div></header>'
        f'<section><p class="lead">{escape(c.ABOUT)}</p></section>'
        f'<section><h2>Навыки</h2><div class="skills">{skills}</div></section>'
        f'<section><h2>Практический опыт</h2><div class="grid">{exp}</div></section>'
        f'<section><h2>Проекты на GitHub</h2><div class="grid">{projects}</div></section>'
        f"<section><h2>Образование</h2>{edu}</section>"
        f'<section><h2>Дополнительно</h2><p>{langs}</p><div>{_tags(c.QUALITIES)}</div></section>'
        "<footer>Проекты обновляются автоматически из GitHub.</footer></main></body></html>"
    )
