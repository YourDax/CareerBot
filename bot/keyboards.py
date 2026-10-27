from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from .config import WEBAPP_URL

BTN_APPS = "📋 Отклики"
BTN_TIME = "🕒 Время"
BTN_JOBS = "🔎 Вакансии"
BTN_PROFILE = "👤 Профиль"
BTN_INTERVIEW = "🎓 Интервью"
BTN_APP = "📱 Приложение"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_APPS), KeyboardButton(text=BTN_TIME)],
            [KeyboardButton(text=BTN_JOBS), KeyboardButton(text=BTN_PROFILE)],
            [KeyboardButton(text=BTN_INTERVIEW), KeyboardButton(text=BTN_APP, web_app=WebAppInfo(url=WEBAPP_URL))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
