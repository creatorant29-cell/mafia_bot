import os
from telebot import types
from dotenv import load_dotenv

# Загрузка переменных из .env файла (если они используются)
load_dotenv()

# Безопасное получение токена
API_TOKEN = os.getenv('API_TOKEN')

# Игровые настройки тайм-аутов и лимитов
INACTIVITY_TIMEOUT = 300
MIN_USER_IN_GAME = 5
MAX_USER_IN_GAME = 8
LOSE_MAFIA = 0

# === ИСПРАВЛЕННЫЙ БЛОК: Автоматическое определение путей ===
# Этот код сам находит, где запущен бот, и файлы баз данных никогда не потеряются
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)  # Выходим из папки cfg в корень проекта

DB_NAME_SQLITE = os.path.join(BASE_DIR, "database.db")
DB_NAME_JSON = os.path.join(BASE_DIR, "data_base.json")
# ==========================================================

# Кнопка со ссылкой на бота
MARKUP_TG = types.InlineKeyboardMarkup()
MARKUP_TG.add(types.InlineKeyboardButton(text="🤖💬", url='https://t.me'))
