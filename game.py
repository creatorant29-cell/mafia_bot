import threading
from time import time, sleep
import random
from telebot import types, TeleBot
from cfg.config import (API_TOKEN, MIN_USER_IN_GAME,
                        MAX_USER_IN_GAME, LOSE_MAFIA,
                        INACTIVITY_TIMEOUT, MARKUP_TG)
from db.sqlite.repository import DataBase
from db.sqlite.schema import TABLE_NAME_USERS, USERS_TABLE_CREATE
from db.json.dynamic_database import Json

table_chat = Json()
table_users = DataBase(TABLE_NAME_USERS, USERS_TABLE_CREATE)

bot = TeleBot(API_TOKEN)


def get_admins(chat_id):
    try:
        user_status = bot.get_chat_administrators(chat_id)
        return [str(admins.user.id) for admins in user_status]
    except Exception:
        return []


def check_player_count(chat_id, data):
    count = len(data["chat_id"][chat_id]["players"])
    if count < MIN_USER_IN_GAME:
        bot.send_message(chat_id, f"⚙️| Для начала игры требуется минимум {MIN_USER_IN_GAME} людей.")
        return False
    elif count > MAX_USER_IN_GAME:
        bot.send_message(chat_id, f"⚙️| Максимальное количество людей - {MAX_USER_IN_GAME}.")
        return False
    return True


def start_new_game(chat_id):
    data = table_chat.open_json_file_and_write()
    data["chat_id"][chat_id]["game_in_progress"] = True
    table_chat.save_json_file_and_write(data)
    
    assign_roles(chat_id)
    
    data = table_chat.open_json_file_and_write()
    for player_id, role in data["chat_id"][chat_id]["players"].items():
        try:
            if role["roles"] == "Яндэре" and len(data["chat_id"][chat_id]["mafia"]) > 1:
                mafia_names = [data["chat_id"][chat_id]["players"][m]["name"] for m in data["chat_id"][chat_id]["mafia"]]
                bot.send_message(player_id, f'Твоя роль: {role["roles"]}\n\nСостав Яндэре:\n' + "\n".join(mafia_names))
            else:
                bot.send_message(player_id, f'Ваша 🎭: {role["roles"]}')
        except Exception:
            pass
            
    bot.send_message(chat_id, "🌃| Яндэре разозлилась! Яндэре вышла на охоту.")
    start_night_phase(chat_id)


def assign_roles(chat_id):
    data = table_chat.open_json_file_and_write()
    player_ids = list(data["chat_id"][chat_id]["players"].keys())
    random.shuffle(player_ids)
    num_players = len(player_ids)

    if num_players >= 5:
        data["chat_id"][chat_id]["players"][player_ids[0]]["roles"] = 'Яндэре'
        data["chat_id"][chat_id]["mafia"].append(player_ids[0])
        data["chat_id"][chat_id]["players"][player_ids[1]]["roles"] = 'Журналист'
        data["chat_id"][chat_id]["players"][player_ids[2]]["roles"] = 'Защитник'
        for i in range(3, num_players):
            data["chat_id"][chat_id]["players"][player_ids[i]]["roles"] = 'Соперница'
    if num_players >= 6:
        data["chat_id"][chat_id]["players"][player_ids[3]]["roles"] = 'Яндэре'
        data["chat_id"][chat_id]["mafia"].append(player_ids[3])
    if num_players >= 7:
        data["chat_id"][chat_id]["players"][player_ids[4]]["roles"] = 'Соперница'
    if num_players == 8:
        data["chat_id"][chat_id]["players"][player_ids[5]]["roles"] = 'Соперница'
    table_chat.save_json_file_and_write(data)


def start_night_phase(chat_id):
    data = table_chat.open_json_file_and_write()
    data["chat_id"][chat_id]["night_actions"] = {'Яндэре': None, 'Защитник': None, 'Журналист': None}
    table_chat.save_json_file_and_write(data)
    
    bot.send_message(chat_id, "🌃| Яндэре, Защитник и Журналист, проверьте свои личные сообщения для выполнения действий.", reply_markup=MARKUP_TG)
    
    for player_id in data["chat_id"][chat_id]["players"]:
        if player_id not in data["chat_id"][chat_id]["admins"]:
            try:
                bot.restrict_chat_member(chat_id, player_id, until_date=int(time()) + 3600)
            except Exception:
                pass

    for player_id, role in data["chat_id"][chat_id]["players"].items():
        try:
            if role["roles"] == 'Яндэре':
                markup = types.InlineKeyboardMarkup()
                for target_id, target_name in data["chat_id"][chat_id]["players"].items():
                    if target_id != player_id:
                        markup.add(types.InlineKeyboardButton(text=target_name['name'], callback_data=f'night_kill_{target_id}_{chat_id}'))
                bot.send_message(player_id, "⚙️| Выбери цель для 🔪🩸:", reply_markup=markup)
            elif role["roles"] == 'Защитник':
                markup = types.InlineKeyboardMarkup()
                for target_id, target_name in data["chat_id"][chat_id]["players"].items():
                    markup.add(types.InlineKeyboardButton(text=target_name['name'], callback_data=f'night_save_{target_id}_{chat_id}'))
                bot.send_message(player_id, "⚙️| Выбери к кому пойдешь в гости!🤗:", reply_markup=markup)
            elif role["roles"] == 'Журналист':
                markup = types.InlineKeyboardMarkup()
                for target_id, target_name in data["chat_id"][chat_id]["players"].items():
                    if target_id != player_id:
                        markup.add(types.InlineKeyboardButton(text=target_name['name'], callback_data=f'night_check_{target_id}_{chat_id}'))
                bot.send_message(player_id, "⚙️| Выбери цель для слежки 🔎:", reply_markup=markup)
        except Exception:
            pass


def handle_night_action_callback(call):
    data = table_chat.open_json_file_and_write()
    _, action, target_id, chat_id = call.data.split('_')
    player_id = str(call.message.chat.id)
    
    if chat_id not in data["chat_id"] or player_id not in data["chat_id"][chat_id]["players"]:
        return

    data["chat_id"][chat_id]["players"][player_id]['last_active'] = time()
    role = data["chat_id"][chat_id]["players"][player_id]["roles"]

    if role == 'Яндэре' and action == 'kill':
        data["chat_id"][chat_id]["night_actions"]['Яндэре'] = target_id
    elif role == 'Защитник' and action == 'save':
        data["chat_id"][chat_id]["night_actions"]['Защитник'] = target_id
    elif role == 'Журналист' and action == 'check':
        data["chat_id"][chat_id]["night_actions"]['Журналист'] = target_id
        
    bot.send_message(player_id, f"⚙️| Вы выбрали {data['chat_id'][chat_id]['players'][target_id]['name'] or 'Кого-то'}")
    table_chat.save_json_file_and_write(data)

    if all(action is not None for action in data["chat_id"][chat_id]["night_actions"].values()):
        end_night_phase(chat_id)


def end_night_phase(chat_id):
    data = table_chat.open_json_file_and_write()
    kill_target = data["chat_id"][chat_id]["night_actions"]['Яндэре']
    save_target = data["chat_id"][chat_id]["night_actions"]['Защитник']
    check_target = data["chat_id"][chat_id]["night_actions"]['Журналист']
    
    kill_result = 'Никто не был ☠️.'

    if kill_target and kill_target != save_target:
        kill_result = f'☠️| {data["chat_id"][chat_id]["players"][kill_target]["name"]} был убит.'
        if kill_target not in data["chat_id"][chat_id]["admins"]:
            try:
                bot.restrict_chat_member(chat_id, kill_target, until_date=int(time()) + 3600)
            except Exception:
                pass
            data["chat_id"][chat_id]["mute_users"].append(kill_target)
        table_users.update_data(kill_target, "lose", 1)
        del data["chat_id"][chat_id]["players"][kill_target]

    bot.send_message(chat_id, kill_result)
    
    if check_target:
        for player_id, role in data["chat_id"][chat_id]["players"].items():
            if role["roles"] == 'Журналист':
                check_result = f'🔎| {data["chat_id"][chat_id]["players"][check_target]["name"]} является {data["chat_id"][chat_id]["players"][check_target]["roles"]}.'
                try:
                    bot.send_message(player_id, check_result)
                except Exception:
                    pass

    for player_id in data["chat_id"][chat_id]["players"]:
        if player_id not in data["chat_id"][chat_id]["admins"]:
            try:
                bot.restrict_chat_member(chat_id, player_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
            except Exception:
                pass

    table_chat.save_json_file_and_write(data)
    if check_win_condition(chat_id):
        start_day_phase(chat_id)


def start_day_phase(chat_id):
    data = table_chat.open_json_file_and_write()
    bot.send_message(chat_id, "🏙️| День начался. У вас есть минута чтобы обсудить кто Яндэре.")
    sleep(60)
    
    data = table_chat.open_json_file_and_write()
    for player_id in data["chat_id"][chat_id]["players"]:
        markup = types.InlineKeyboardMarkup()
        for target_id, target_info in data["chat_id"][chat_id]["players"].items():
            if target_id != player_id:
                markup.add(types.InlineKeyboardButton(text=target_info['name'], callback_data=f'vote_{target_id}_{chat_id}'))
        try:
            bot.send_message(player_id, "📢| Голосуйте за подозреваемого:", reply_markup=markup)
        except Exception:
            pass
            
    bot.send_message(chat_id, "📢💬| Голосование в лс", reply_markup=MARKUP_TG)
    data["chat_id"][chat_id]["votes"] = {}
    table_chat.save_json_file_and_write(data)


def handle_vote(call):
    data = table_chat.open_json_file_and_write()
    voter_id = str(call.message.chat.id)
    _, target_id, chat_id = call.data.split('_')
    
    if chat_id not in data["chat_id"] or voter_id not in data["chat_id"][chat_id]["players"]:
        return

    data["chat_id"][chat_id]["players"][voter_id]['last_active'] = time()
    data["chat_id"][chat_id]["votes"][voter_id] = target_id
    bot.send_message(voter_id, f"📢| Ты проголосовал(а) за {data['chat_id'][chat_id]['players'][target_id]['name']}")
    table_chat.save_json_file_and_write(data)

    if len(data["chat_id"][chat_id]["votes"]) == len(data['chat_id'][chat_id]['players']):
end_day_phase(chat_id)def end_day_phase(chat_id):data = table_chat.open_json_file_and_write()vote_counts = {}for target_id in data["chat_id"][chat_id]["votes"].values():vote_counts[target_id] = vote_counts.get(target_id, 0) + 1if not vote_counts:returnmax_votes = max(vote_counts.values())to_eliminate = [target_id for target_id, count in vote_counts.items() if count == max_votes]eliminated_id = to_eliminate[0] if len(to_eliminate) == 1 else random.choice(to_eliminate)# Исправлено: Ссылка и отправка идет четко в общую группу chat_idbot.send_message(chat_id, f'🏃🚪| {data["chat_id"][chat_id]["players"][eliminated_id]["name"]} был изгнан. Он был {data["chat_id"][chat_id]["players"][eliminated_id]["roles"]}.')if eliminated_id not in data["chat_id"][chat_id]["admins"]:try:bot.restrict_chat_member(chat_id, eliminated_id, until_date=int(time()) + 3600)except Exception:passdata["chat_id"][chat_id]["mute_users"].append(eliminated_id)table_users.update_data(eliminated_id, "lose", 1)del data["chat_id"][chat_id]["players"][eliminated_id]table_chat.save_json_file_and_write(data)if check_win_condition(chat_id):start_night_phase(chat_id)def check_win_condition(chat_id):data = table_chat.open_json_file_and_write()if chat_id not in data["chat_id"]:return Falsemafia_count = sum(1 for role in data["chat_id"][chat_id]["players"].values() if role["roles"] == 'Яндэре')non_mafia_count = len(data["chat_id"][chat_id]["players"]) - mafia_countif mafia_count >= non_mafia_count and non_mafia_count >= 0:bot.send_message(chat_id, "🔪🩸| Яндэре победил(а)!")for player_id, role in data["chat_id"][chat_id]["players"].items():if role["roles"] == "Яндэре":table_users.update_data(player_id, "win", 1)end_game(chat_id)return Falseelif mafia_count == LOSE_MAFIA:bot.send_message(chat_id, "🙎‍♂️| Яндэре посадили в тюрьму. Победа Соперниц!")for player_id, role in data["chat_id"][chat_id]["players"].items():if role["roles"] != "Яндэре":table_users.update_data(player_id, "win", 1)end_game(chat_id)return Falsereturn Truedef monitor_inactivity():while True:try:data = table_chat.open_json_file_and_write()now = time()for chat_id in list(data["chat_id"].keys()):if data["chat_id"][chat_id]["game_in_progress"]:for player_id, player_info in list(data["chat_id"][chat_id]["players"].items()):last_active = player_info.get('last_active')if last_active and now - last_active > INACTIVITY_TIMEOUT:end_game_due_to_inactivity(player_id, chat_id)breakexcept Exception:passsleep(60)def end_game_due_to_inactivity(player_id, chat_id):data = table_chat.open_json_file_and_write()name = data["chat_id"][chat_id]["players"].get(player_id, {}).get('name', 'Игрок')bot.send_message(chat_id, f'⚙️| Игра завершена из-за неактивности игрока {name}.')end_game(chat_id)def end_game(chat_id):data = table_chat.open_json_file_and_write()if chat_id in data["chat_id"]:for user_id in data["chat_id"][chat_id]["mute_users"]:try:bot.restrict_chat_member(chat_id, user_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)except Exception:passdel data["chat_id"][chat_id]table_chat.save_json_file_and_write(data)def update_last_active(player_id, chat_id_user, message_id):data = table_chat.open_json_file_and_write()for chat_id in data["chat_id"]:if player_id in data["chat_id"][chat_id]["players"]:data["chat_id"][chat_id]["players"][player_id]['last_active'] = time()table_chat.save_json_file_and_write(data)returnif chat_id_user in data["chat_id"] and data["chat_id"][chat_id_user]["game_in_progress"]:try:bot.delete_message(chat_id_user, message_id)except Exception:passif player_id not in data["chat_id"][chat_id_user]["admins"]:try:bot.restrict_chat_member(chat_id_user, player_id, until_date=int(time()) + 3600)data["chat_id"][chat_id_user]["mute_users"].append(player_id)table_chat.save_json_file_and_write(data)except Exception:passinactivity_thread = threading.Thread(target=monitor_inactivity, daemon=True)inactivity_thread.start()
