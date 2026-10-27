from datetime import datetime, timedelta, timezone

import asyncpg

from .config import DATABASE_URL

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    user_id BIGINT PRIMARY KEY,
    full_name TEXT, title TEXT, skills TEXT, about TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    company TEXT NOT NULL,
    position TEXT NOT NULL,
    url TEXT,
    status TEXT NOT NULL DEFAULT 'sent',
    applied_at TIMESTAMPTZ NOT NULL,
    remind_at TIMESTAMPTZ,
    reminded BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS time_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS income (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE profile ADD COLUMN IF NOT EXISTS digest BOOLEAN NOT NULL DEFAULT TRUE;
CREATE TABLE IF NOT EXISTS seen_jobs (
    user_id BIGINT NOT NULL,
    job_key TEXT NOT NULL,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_key)
);
CREATE TABLE IF NOT EXISTS interview_log (
    user_id BIGINT NOT NULL,
    qid TEXT NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    correct INT NOT NULL DEFAULT 0,
    last_ok BOOLEAN NOT NULL,
    last_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, qid)
);
CREATE TABLE IF NOT EXISTS fsm (
    key TEXT PRIMARY KEY,
    state TEXT,
    data TEXT NOT NULL DEFAULT '{}'
);
"""

STATUSES = {
    "sent": "Отправлен",
    "replied": "Ответили",
    "interview": "Собеседование",
    "offer": "Оффер",
    "rejected": "Отказ",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


async def _connect() -> asyncpg.Connection:
    # Serverless: соединение на каждый вызов; statement_cache_size=0 нужен для pgbouncer-пулера.
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


async def _run(method: str, sql: str, *params):
    conn = await _connect()
    try:
        return await getattr(conn, method)(sql, *params)
    finally:
        await conn.close()


async def init_db() -> None:
    await _run("execute", SCHEMA)


_ready = False


async def ensure() -> None:
    """Схема создаётся один раз на экземпляр функции."""
    global _ready
    if not _ready:
        await init_db()
        _ready = True


# ---- FSM storage ----
async def fsm_get(key: str):
    return await _run("fetchrow", "SELECT state, data FROM fsm WHERE key=$1", key)


async def fsm_set_state(key: str, state: str | None) -> None:
    await _run(
        "execute",
        "INSERT INTO fsm(key, state) VALUES($1,$2) ON CONFLICT(key) DO UPDATE SET state=excluded.state",
        key,
        state,
    )


async def fsm_set_data(key: str, data: str) -> None:
    await _run(
        "execute",
        "INSERT INTO fsm(key, data) VALUES($1,$2) ON CONFLICT(key) DO UPDATE SET data=excluded.data",
        key,
        data,
    )


# ---- profile ----
async def save_profile(user_id: int, full_name: str, title: str, skills: str, about: str) -> None:
    await _run(
        "execute",
        "INSERT INTO profile(user_id, full_name, title, skills, about) VALUES($1,$2,$3,$4,$5) "
        "ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, title=excluded.title, "
        "skills=excluded.skills, about=excluded.about",
        user_id, full_name, title, skills, about,
    )


async def get_profile(user_id: int):
    return await _run("fetchrow", "SELECT * FROM profile WHERE user_id=$1", user_id)


# ---- job digest ----
async def set_digest(user_id: int, enabled: bool) -> None:
    await _run("execute", "UPDATE profile SET digest=$1 WHERE user_id=$2", enabled, user_id)


async def digest_users():
    return await _run("fetch", "SELECT user_id, skills FROM profile WHERE digest")


async def seen_keys(user_id: int, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    rows = await _run("fetch", "SELECT job_key FROM seen_jobs WHERE user_id=$1 AND job_key = ANY($2::text[])",
                      user_id, keys)
    return {r["job_key"] for r in rows}


async def mark_seen(user_id: int, keys: list[str]) -> None:
    if keys:
        await _run(
            "execute",
            "INSERT INTO seen_jobs(user_id, job_key) SELECT $1, unnest($2::text[]) ON CONFLICT DO NOTHING",
            user_id, keys,
        )


async def cleanup_seen() -> None:
    await _run("execute", "DELETE FROM seen_jobs WHERE seen_at < now() - interval '60 days'")


# ---- mock interview ----
async def interview_progress(user_id: int) -> dict:
    rows = await _run("fetch", "SELECT qid, attempts, correct, last_ok, last_at FROM interview_log WHERE user_id=$1",
                      user_id)
    return {r["qid"]: r for r in rows}


async def record_answer(user_id: int, qid: str, ok: bool) -> None:
    await _run(
        "execute",
        "INSERT INTO interview_log(user_id, qid, attempts, correct, last_ok, last_at) VALUES($1,$2,1,$3,$4,$5) "
        "ON CONFLICT(user_id, qid) DO UPDATE SET attempts=interview_log.attempts+1, "
        "correct=interview_log.correct+excluded.correct, last_ok=excluded.last_ok, last_at=excluded.last_at",
        user_id, qid, 1 if ok else 0, ok, now(),
    )


# ---- applications ----
async def add_application(user_id: int, company: str, position: str, url: str | None, remind_days: int) -> int:
    t = now()
    return await _run(
        "fetchval",
        "INSERT INTO applications(user_id, company, position, url, applied_at, remind_at) "
        "VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
        user_id, company, position, url, t, t + timedelta(days=remind_days),
    )


async def list_applications(user_id: int):
    return await _run(
        "fetch", "SELECT * FROM applications WHERE user_id=$1 ORDER BY id DESC LIMIT 30", user_id
    )


async def get_application(user_id: int, app_id: int):
    return await _run("fetchrow", "SELECT * FROM applications WHERE id=$1 AND user_id=$2", app_id, user_id)


async def set_status(user_id: int, app_id: int, status: str) -> bool:
    if status not in STATUSES:
        return False
    # Любая смена статуса, кроме "sent", снимает напоминание: ответ уже получен.
    await _run(
        "execute",
        "UPDATE applications SET status=$1, reminded=$2 WHERE id=$3 AND user_id=$4",
        status, status != "sent", app_id, user_id,
    )
    return True


async def due_reminders():
    return await _run(
        "fetch",
        "SELECT * FROM applications WHERE status='sent' AND NOT reminded AND remind_at<=$1",
        now(),
    )


async def mark_reminded(app_id: int) -> None:
    await _run("execute", "UPDATE applications SET reminded=TRUE WHERE id=$1", app_id)


# ---- time tracking ----
async def active_entry(user_id: int):
    return await _run("fetchrow", "SELECT * FROM time_entries WHERE user_id=$1 AND ended_at IS NULL", user_id)


async def start_entry(user_id: int, project: str) -> None:
    await _run(
        "execute",
        "INSERT INTO time_entries(user_id, project, started_at) VALUES($1,$2,$3)",
        user_id, project, now(),
    )


async def get_entry(user_id: int, entry_id: int):
    return await _run("fetchrow", "SELECT * FROM time_entries WHERE id=$1 AND user_id=$2", entry_id, user_id)


async def recent_projects(user_id: int, limit: int = 6):
    return await _run(
        "fetch",
        "SELECT id, project FROM (SELECT DISTINCT ON (project) id, project FROM time_entries "
        "WHERE user_id=$1 ORDER BY project, id DESC) t ORDER BY id DESC LIMIT $2",
        user_id, limit,
    )


async def stop_entry(entry_id: int) -> None:
    await _run("execute", "UPDATE time_entries SET ended_at=$1 WHERE id=$2", now(), entry_id)


async def add_income(user_id: int, project: str, amount: float) -> None:
    await _run(
        "execute",
        "INSERT INTO income(user_id, project, amount, created_at) VALUES($1,$2,$3,$4)",
        user_id, project, amount, now(),
    )


async def project_stats(user_id: int) -> list[dict]:
    rows = await _run(
        "fetch",
        """
        SELECT COALESCE(t.project, i.project) AS project,
               COALESCE(t.seconds, 0) AS seconds,
               COALESCE(i.earned, 0) AS earned
        FROM (
            SELECT project, SUM(EXTRACT(EPOCH FROM (COALESCE(ended_at, $2) - started_at))) AS seconds
            FROM time_entries WHERE user_id=$1 GROUP BY project
        ) t
        FULL JOIN (
            SELECT project, SUM(amount) AS earned FROM income WHERE user_id=$1 GROUP BY project
        ) i ON t.project = i.project
        ORDER BY 1
        """,
        user_id, now(),
    )
    result = []
    for r in rows:
        hours = float(r["seconds"]) / 3600
        earned = float(r["earned"])
        result.append(
            {"project": r["project"], "hours": hours, "earned": earned,
             "rate": earned / hours if hours >= 0.01 else None}
        )
    return result
