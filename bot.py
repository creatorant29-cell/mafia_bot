import logging
import telebot
from time import time
import os
import threading
from aiohttp import web
import asyncio

# Импорты из проекта
from cfg.text_in_bot import *
from game import (start_new_game, handle_night_action_callback,
                  handle_vote, check_player_count,
                  update_last_active, get_admins)
from cfg.config import MAX_USER_IN_GAME, MARKUP_TG
from db.sqlite.repository import DataBase
from db.sqlite.schema import TABLE_NAME_USERS, USERS_TABLE_CREATE
from db.json.dynamic_database import Json

# Фейковый сервер для прохождения проверки портов Hugging Face
async def handle(request):
    return web.Response(text="Мафия онлайн и готова к игре!")

def run_fake_server():
    app = web.Application()
    app.router.add_get('/', handle)
    web.run_app(app, host='0.0.0.0', port=7860)

# Запуск веб-сервера в фоновом потоке
threading.Thread(target=run_fake_server, daemon=True).start()

# Инициализация баз данных
table_chat = Json()
table_users = DataBase(TABLE_NAME_USERS, USERS_TABLE_CREATE)
table_users.create_table()

# Безопасное получение токена из секретов Hugging Face
API_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(API_TOKEN)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



@bot.message_handler(commands=['start'])
def handler_start(message):
    chat_id = message.chat.id
    if str(chat_id)[0] == "-":
        bot.send_message(chat_id, "⚙️| Данная команда работает только в лс бота", reply_markup=MARKUP_TG)
        return
    bot.send_message(chat_id, start_text)
    result = table_users.get_data("user_id", message.from_user.id)
    if not result:
        table_users.create_user(message.from_user.id, 0, 0)
        bot.send_message(chat_id, "⚙️| Вы успешно авторизовались.")
    else:
        bot.send_message(chat_id, "⚙️| Вы уже авторизованы.")


@bot.message_handler(commands=['help'])
def handler_help(message):
    chat_id = str(message.chat.id)
    if chat_id[0] == "-":
        bot.send_message(chat_id, "⚙️| Данная команда работает только в лс бота", reply_markup=MARKUP_TG)
        return
    bot.send_message(chat_id, help_text)


@bot.message_handler(commands=['rules'])
def handler_rules(message):
    chat_id = str(message.chat.id)
    bot.send_message(chat_id, rules_text)


@bot.message_handler(commands=['start_game'])  # Проверка на чат это или нет, удаления чата
def start_game(message):
    chat_id = str(message.chat.id)
    if chat_id[0] != "-":
        bot.send_message(chat_id, "⚙️| Данная команда работает только в группе")
        return
    data = table_chat.open_json_file_and_write()
    data["chat_id"][chat_id] = {"players": {},
                                "game_in_progress": False,
                                "night_actions": {},
                                "votes": {},
                                "mafia": [],
                                "mute_users": [],
                                "admins": get_admins(chat_id)}
    table_chat.save_json_file_and_write(data)
    bot.send_message(chat_id,
                     "⚙️| Игра 'вычисли Яндэре' начинается!\n🔗| Все желающие присоединиться, напишите /join.\n🏁| Начать игру /begin")


@bot.message_handler(commands=['join'])
def join(message):
    chat_id = str(message.chat.id)
    if chat_id[0] != "-":
        bot.send_message(chat_id, "⚙️| Данная команда работает только в группе")
        return
    data = table_chat.open_json_file_and_write()

    if chat_id not in data["chat_id"]:
        bot.send_message(chat_id, "⚙️| Игру еще не начали.")
        return

    result = table_users.get_data("user_id", message.from_user.id)
    if not result:
        bot.send_message(chat_id, "⚙️| Вы не авторизовались в боте.\nНапишите /start боту в лс.",
                         reply_markup=MARKUP_TG)
        return

    if data["chat_id"][chat_id]["game_in_progress"]:
        bot.send_message(chat_id, "⚙️| Игра уже идет. Вы не можете присоединиться.")
        return

    if len(data["chat_id"][chat_id]["players"]) >= MAX_USER_IN_GAME:
        bot.send_message(chat_id, f"⚙️| Игра уже достигла максимального количества игроков ({MAX_USER_IN_GAME}).")
        return

    player_id = str(message.from_user.id)
    if player_id in data["chat_id"][chat_id]["players"]:
        bot.send_message(chat_id, "⚙️| Вы уже присоединились к игре.")
    else:
        data["chat_id"][chat_id]["players"][player_id] = {
            'name': message.from_user.first_name,
            'last_active': None,
            "roles": None
        }
        bot.send_message(chat_id, f"🔗| {message.from_user.first_name} присоединился к игре.")
        table_chat.save_json_file_and_write(data)


@bot.message_handler(commands=['top'])
def get_top(message):
    players_name = [i for i in table_users.get_data("user_id")]
    players_result = table_users.get_data("win")
    players = dict(sorted({bot.get_chat(players_name[num][0]).first_name: players_result[num][0] for num in
                           range(len(players_result))}.items(), key=lambda x: x[1], reverse=True))
    top = "🔝| Топ нашего бота:\n"
    count = 0
    for player in players:
        top += f"  \n\n{player} - {players[player]} 🏆"
        count += 1
        if count > 10:
            break
    bot.send_message(message.chat.id, top)


@bot.message_handler(commands=['stats'])
def get_stats(message):
    chat_id = message.chat.id
    if str(chat_id)[0] == "-":
        bot.send_message(chat_id, "⚙️| Данная команда работает только в лс бота", reply_markup=MARKUP_TG)
        return
    stats = table_users.get_data("win, lose", chat_id)[0]
    wins, loses = stats[0], stats[1]
    games = wins + loses
    if games > 0:
        bot.send_message(chat_id,
                         f"📊| Твоя статистика:\n  Кол-во игр: {games}\n  🏆: {wins}\n  💢: {loses}\n  🏆%: {round(wins / games) * 100}%")
    else:
        bot.send_message(chat_id,
                         f"📊| Твоя статистика:\n\n  Кол-во игр: {games}\n\n  🏆: {wins}\n\n  💢: {loses}\n\n  🏆%: 0%")


@bot.message_handler(commands=['begin'])
def begin_game(message):
    chat_id = str(message.chat.id)
    player_id = str(message.from_user.id)
    if chat_id[0] != "-":
        bot.send_message(chat_id, "⚙️| Данная команда работает только в группе")
        return
    data = table_chat.open_json_file_and_write()
    if chat_id not in data["chat_id"]:
        bot.send_message(chat_id, "⚙️| Игру еще не создали.")
        return
    if player_id not in data["chat_id"][chat_id]["players"]:
        bot.send_message(chat_id, "⚙️| Вы не зашли в игру. /join")
        return
    if not data["chat_id"][chat_id]["game_in_progress"] and check_player_count(chat_id, data):
        for user_id in data["chat_id"][chat_id]["players"]:
            data["chat_id"][chat_id]["players"][user_id]["last_active"] = time()
        table_chat.save_json_file_and_write(data)
        start_new_game(chat_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('night_'))
def handle_night_action(call):
    handle_night_action_callback(call)


@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def handle_vote_action(call):
    handle_vote(call)


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    update_last_active(str(message.from_user.id), str(message.chat.id), message.message_id)


if __name__ == "__main__":
    bot.infinity_polling()
