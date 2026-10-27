import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
CRON_SECRET = os.getenv("CRON_SECRET", "")
HH_TOKEN = os.getenv("HH_TOKEN", "")  # необязательно: без него hh.ru пропускается
OWNER_ID = int(os.getenv("OWNER_ID") or 0)  # бот личный: все остальные игнорируются
GITHUB_USER = os.getenv("GITHUB_USER", "YourDax")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # необязательно: поднимает лимит GitHub API
PORTFOLIO_URL = os.getenv("PORTFOLIO_URL", "https://careerbot-green.vercel.app/portfolio")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://careerbot-green.vercel.app/app")


def _clean_dsn(dsn: str) -> str:
    # Neon добавляет channel_binding, который asyncpg воспринимает как неизвестный параметр.
    parts = urlsplit(dsn)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "channel_binding"]
    return urlunsplit(parts._replace(query=urlencode(query)))


DATABASE_URL = _clean_dsn(os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL", ""))
