# CareerBot

Личный Telegram-бот для работы и карьеры. Работает на Vercel 24/7 (webhook, без постоянного процесса).

## Возможности

- **Профиль** и **трекер откликов** со статусами и напоминанием, если на отклик не ответили.
- **Тайм-трекер** для фриланса: часы по проектам, доход и ставка в час.
- **Агрегатор вакансий и заказов** (Хабр Карьера, FL.ru, Remotive, RemoteOK, hh.ru по токену): фильтр по навыкам из профиля, дедупликация, ежедневный дайджест.
- **Мок-интервью** по Python, SQL и аналитике: тесты, SQL-задачи с проверкой запуском в песочнице, открытые вопросы с самооценкой.
- **Мини-приложение** Telegram (`/app`) и **портфолио-сайт** (`/portfolio`), который сам подтягивает проекты с GitHub.

Бот личный: все пользователи, кроме `OWNER_ID`, игнорируются.

## Устройство

| Часть | Файлы |
| --- | --- |
| Точка входа FastAPI (webhook, cron) | `api/index.py` |
| Обработчики бота (aiogram 3) | `bot/handlers/` |
| Мини-приложение и его API | `bot/webapp.py`, `bot/webapp_html.py` |
| Портфолио | `bot/portfolio.py`, `bot/portfolio_content.py` |
| Postgres (asyncpg), FSM-хранилище в базе | `bot/db.py`, `bot/storage.py` |
| Источники вакансий | `bot/sources.py`, `bot/digest.py` |
| Мок-интервью | `bot/interview_data.py`, `bot/sqlcheck.py` |

Состояние диалогов хранится в Postgres, потому что функции Vercel не помнят память между запросами.
Напоминания и дайджест запускает Vercel Cron раз в сутки (`/api/cron`, 08:00 UTC).

## Переменные окружения

См. `.env.example`.

| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | токен бота от @BotFather |
| `DATABASE_URL` | строка подключения к Postgres (Neon) |
| `WEBHOOK_SECRET` | секрет заголовка webhook Telegram |
| `CRON_SECRET` | секрет для `/api/cron` |
| `OWNER_ID` | Telegram ID владельца |
| `HH_TOKEN` | необязательно, токен приложения hh.ru |
| `GITHUB_USER`, `GITHUB_TOKEN` | аккаунт для портфолио и необязательный токен API |

## Деплой

1. `vercel link`, подключить Postgres (Neon) через Marketplace.
2. Добавить переменные в Vercel, затем `vercel deploy --prod`.
3. Поставить webhook, обязательно с `allowed_updates: ["message", "callback_query"]`, иначе кнопки под сообщениями не работают:

```
POST https://api.telegram.org/bot<BOT_TOKEN>/setWebhook
{"url": "https://<домен>/webhook", "secret_token": "<WEBHOOK_SECRET>",
 "allowed_updates": ["message", "callback_query"]}
```

## Локальная разработка

Нужен Python 3.12 (на 3.15 нет готовых сборок `aiohttp` и `pydantic-core`).

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
