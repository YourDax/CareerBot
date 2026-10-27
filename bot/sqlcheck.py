"""Проверка SQL-ответов: запрос выполняется на встроенной тестовой базе SQLite и сверяется с эталоном."""
import sqlite3

SCHEMA_DOC = (
    "customers(id, name, city)\n"
    "orders(id, customer_id, amount, status, created_at)  -- status: paid / refunded / new\n"
    "employees(id, name, dept, salary, manager_id)"
)

SEED = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount INTEGER, status TEXT, created_at TEXT);
CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, dept TEXT, salary INTEGER, manager_id INTEGER);
INSERT INTO customers VALUES (1,'Анна','Москва'),(2,'Борис','Казань'),(3,'Вера','Москва'),(4,'Глеб','Казань'),(5,'Дарья','Сочи');
INSERT INTO orders VALUES
 (1,1,1000,'paid','2026-01-05'),(2,1,2500,'paid','2026-02-10'),(3,2,700,'refunded','2026-01-20'),
 (4,2,1800,'paid','2026-02-15'),(5,3,3200,'paid','2026-03-01'),(6,3,400,'new','2026-03-05'),
 (7,4,1500,'paid','2026-03-12'),(8,1,900,'paid','2026-03-20');
INSERT INTO employees VALUES
 (1,'Ирина','IT',300000,NULL),(2,'Олег','IT',200000,1),(3,'Пётр','IT',180000,1),
 (4,'Света','Sales',150000,NULL),(5,'Тимур','Sales',120000,4),(6,'Улла','Sales',120000,4),
 (7,'Фёдор','HR',100000,NULL);
"""

MAX_ROWS = 200
# SELECT, READ, FUNCTION, RECURSIVE: любые другие операции (INSERT, DROP, ATTACH, PRAGMA…) запрещены
_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, 33}


def _auth(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(SEED)
    con.set_authorizer(_auth)
    budget = [3000]  # ограничение по времени: бесконечные рекурсивные запросы прерываются

    def tick():
        budget[0] -= 1
        return 1 if budget[0] <= 0 else 0

    con.set_progress_handler(tick, 1000)
    return con


def _norm(value):
    if isinstance(value, float):
        value = round(value, 2)
        return int(value) if value.is_integer() else value
    return value


def run(sql: str):
    con = _connect()
    try:
        cur = con.execute(sql)
        rows = cur.fetchmany(MAX_ROWS + 1)
        ncols = len(cur.description or [])
    finally:
        con.close()
    return ncols, [tuple(_norm(v) for v in r) for r in rows[:MAX_ROWS]]


def _fmt(rows, limit=5) -> str:
    if not rows:
        return "(пусто)"
    lines = [" | ".join("NULL" if v is None else str(v) for v in r) for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"… ещё {len(rows) - limit}")
    return "\n".join(lines)


def _key(row):
    return tuple("" if v is None else repr(v) for v in row)


def check(sql: str, reference: str) -> tuple[bool, str]:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        return False, "Пустой запрос."
    try:
        ncols, rows = run(sql)
    except sqlite3.Error as exc:
        return False, f"Ошибка SQL: {exc}"
    except Exception as exc:  # например, несколько операторов в одном запросе
        return False, f"Не удалось выполнить: {exc}"
    exp_cols, exp_rows = run(reference)
    if ncols != exp_cols:
        return False, f"Колонок в результате {ncols}, а ожидалось {exp_cols}.\nТвой результат:\n{_fmt(rows)}"
    ordered = "ORDER BY" in reference.upper()
    same = rows == exp_rows if ordered else sorted(rows, key=_key) == sorted(exp_rows, key=_key)
    if same:
        return True, "Результат совпал с эталонным."
    hint = " (порядок строк важен)" if ordered else ""
    return False, (f"Результат не совпал{hint}: строк у тебя {len(rows)}, ожидалось {len(exp_rows)}.\n"
                   f"Твой результат:\n{_fmt(rows)}")
