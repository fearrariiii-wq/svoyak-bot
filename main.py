import os
import random
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не найден!")
    exit(1)

# Хранилище комнат
rooms = {}
user_rooms = {}  # {user_id: room_id}

class GameRoom:
    def __init__(self, room_id, host_id, host_name):
        self.room_id = room_id
        self.host_id = host_id
        self.host_name = host_name
        self.players = {}  # {user_id: {"name": str, "score": int}}
        self.spectators = {}  # {user_id: name}
        self.num_themes = 0
        self.questions = {}  # {theme: {10: False, ...}}
        self.game_started = False
        self.current_theme = 1
        self.current_question = 0
        self.paused = False
        self.blocked_players = {}  # {(theme, points): [user_id1, user_id2, ...]}
        self.answered_players = {}  # {(theme, points): [user_id1, user_id2, ...]}

async def create_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание новой комнаты"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Пользователь"
    
    # Проверяем, не в комнате ли уже
    if user_id in user_rooms:
        await update.message.reply_text("❌ Ты уже в комнате! Сначала используй /exit")
        return
    
    # Генерируем уникальный номер комнаты
    room_id = random.randint(10000, 99999)
    while room_id in rooms:
        room_id = random.randint(10000, 99999)
    
    # Создаем комнату
    room = GameRoom(room_id, user_id, user_name)
    rooms[room_id] = room
    user_rooms[user_id] = room_id
    
    await update.message.reply_text(
        f"✅ *Комната создана!*\n\n"
        f"🏠 *Номер комнаты:* `{room_id}`\n"
        f"👤 *Хост:* {user_name}\n\n"
        f"📌 *Игроки могут присоединиться используя:*\n"
        f"`/room {room_id}` - как игрок\n"
        f"`/spectator {room_id}` - как зритель\n\n"
        f"Когда все будут готовы, нажми `/game 4` (где 4 - количество тем)",
        parse_mode='Markdown'
    )

async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Присоединиться как игрок"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Игрок"
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Укажи номер комнаты*\n\n"
            "Используй: `/room 12345`",
            parse_mode='Markdown'
        )
        return
    
    try:
        room_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Номер комнаты должен быть числом!")
        return
    
    if user_id in user_rooms:
        await update.message.reply_text("❌ Ты уже в комнате! Сначала используй /exit")
        return
    
    if room_id not in rooms:
        await update.message.reply_text("❌ Комната не найдена!")
        return
    
    room = rooms[room_id]
    
    if room.game_started:
        await update.message.reply_text("❌ Игра уже началась!")
        return
    
    # Добавляем игрока
    room.players[user_id] = {"name": user_name, "score": 0}
    user_rooms[user_id] = room_id
    
    # Уведомляем хоста
    await context.bot.send_message(
        room.host_id,
        f"👤 *Новый игрок:* {user_name}\n"
        f"👥 *Всего игроков:* {len(room.players)}",
        parse_mode='Markdown'
    )
    
    # Показываем комнату игроку
    await show_room_info(context.bot, room, user_id)

async def join_spectator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Присоединиться как зритель"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Зритель"
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Укажи номер комнаты*\n\n"
            "Используй: `/spectator 12345`",
            parse_mode='Markdown'
        )
        return
    
    try:
        room_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Номер комнаты должен быть числом!")
        return
    
    if user_id in user_rooms:
        await update.message.reply_text("❌ Ты уже в комнате! Сначала используй /exit")
        return
    
    if room_id not in rooms:
        await update.message.reply_text("❌ Комната не найдена!")
        return
    
    room = rooms[room_id]
    
    if room.game_started:
        await update.message.reply_text("❌ Игра уже началась!")
        return
    
    # Добавляем зрителя
    room.spectators[user_id] = user_name
    user_rooms[user_id] = room_id
    
    # Уведомляем хоста
    await context.bot.send_message(
        room.host_id,
        f"👁️ *Новый зритель:* {user_name}\n"
        f"📺 *Всего зрителей:* {len(room.spectators)}",
        parse_mode='Markdown'
    )
    
    # Показываем комнату зрителю
    await show_room_info(context.bot, room, user_id, is_spectator=True)

async def show_room_info(bot, room: GameRoom, user_id: int, is_spectator=False):
    """Показать информацию о комнате"""
    role = "зритель 👁️" if is_spectator else "игрок 🎮"
    
    info_text = f"🏠 *Ты в комнате* `{room.room_id}` ({role})\n\n"
    info_text += f"👤 *Хост:* {room.host_name}\n\n"
    info_text += f"👥 *Игроки ({len(room.players)}):*\n"
    
    if room.players:
        for pid, pdata in room.players.items():
            info_text += f"  • {pdata['name']}\n"
    else:
        info_text += "  *(нет)*\n"
    
    info_text += f"\n📺 *Зрители ({len(room.spectators)}):*\n"
    if room.spectators:
        for _, sname in room.spectators.items():
            info_text += f"  • {sname}\n"
    else:
        info_text += "  *(нет)*\n"
    
    info_text += f"\n💡 *Используй /exit чтобы выйти*"
    
    await bot.send_message(user_id, info_text, parse_mode='Markdown')

async def exit_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из комнаты"""
    user_id = update.effective_user.id
    
    if user_id not in user_rooms:
        await update.message.reply_text("❌ Ты не в комнате!")
        return
    
    room_id = user_rooms[user_id]
    room = rooms[room_id]
    
    if room.game_started:
        await update.message.reply_text("❌ Игра уже началась! Ты не можешь выйти")
        return
    
    # Удаляем из игроков или зрителей
    user_name = None
    if user_id in room.players:
        user_name = room.players[user_id]["name"]
        del room.players[user_id]
    elif user_id in room.spectators:
        user_name = room.spectators[user_id]
        del room.spectators[user_id]
    
    # Удаляем из глобального хранилища
    del user_rooms[user_id]
    
    # Если комната пустая, удаляем её
    if len(room.players) == 0 and len(room.spectators) == 0:
        del rooms[room_id]
        await update.message.reply_text(f"✅ Ты вышел из комнаты. Комната удалена.")
    else:
        # Уведомляем хоста
        await context.bot.send_message(
            room.host_id,
            f"👤 *Участник вышел:* {user_name}\n"
            f"👥 *Осталось игроков:* {len(room.players)}",
            parse_mode='Markdown'
        )
        await update.message.reply_text("✅ Ты вышел из комнаты")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск игры"""
    user_id = update.effective_user.id
    
    if user_id not in user_rooms:
        await update.message.reply_text("❌ Ты не в комнате!")
        return
    
    room_id = user_rooms[user_id]
    room = rooms[room_id]
    
    if room.host_id != user_id:
        await update.message.reply_text("❌ Только хост может начать игру!")
        return
    
    if len(room.players) == 0:
        await update.message.reply_text("❌ Нужен минимум 1 игрок!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Укажи количество тем*\n\n"
            "Используй: `/game 4` (где 4 - количество тем)",
            parse_mode='Markdown'
        )
        return
    
    try:
        num_themes = int(context.args[0])
        if num_themes < 1 or num_themes > 10:
            await update.message.reply_text("❌ Количество тем должно быть от 1 до 10")
            return
    except ValueError:
        await update.message.reply_text("❌ Количество тем должно быть числом!")
        return
    
    room.num_themes = num_themes
    room.game_started = True
    room.current_theme = 1
    
    # Инициализируем вопросы
    for theme in range(1, num_themes + 1):
        room.questions[theme] = {10: False, 20: False, 30: False, 40: False, 50: False}
    
    # Показываем таблицу перед игрой
    await show_game_table(context, room)

async def show_game_table(context: ContextTypes.DEFAULT_TYPE, room: GameRoom):
    """Показать таблицу перед началом игры"""
    
    # Таблица игроков
    players_text = "🏆 *ТАБЛИЦА ИГРОКОВ*\n\n"
    players_text += "🎮 *Игроки:*\n"
    for i, (pid, pdata) in enumerate(room.players.items(), 1):
        players_text += f"{i}. {pdata['name']} - 0 очков\n"
    
    players_text += f"\n👁️ *Зрители ({len(room.spectators)}):*\n"
    if room.spectators:
        for _, sname in room.spectators.items():
            players_text += f"• {sname}\n"
    else:
        players_text += "*(нет)*\n"
    
    # Таблица тем
    themes_text = f"\n🎮 *СВОЯ ИГРА - {room.num_themes} ТЕМ*\n\n"
    
    for theme_num in range(1, room.num_themes + 1):
        themes_text += f"*Тема {theme_num}:*\n"
        for points in [10, 20, 30, 40, 50]:
            themes_text += f"  ❓ {points}  "
        themes_text += "\n\n"
    
    # Отправляем всем
    full_message = players_text + themes_text + "✅ *Игра начинается!*"
    
    for player_id in room.players:
        await context.bot.send_message(player_id, full_message, parse_mode='Markdown')
    
    for spectator_id in room.spectators:
        await context.bot.send_message(spectator_id, full_message, parse_mode='Markdown')
    
    # Отправляем доску хосту
    await send_board(context, room)

async def send_board(context: ContextTypes.DEFAULT_TYPE, room: GameRoom):
    """Отправить доску вопросов хосту"""
    board_text = f"🎮 *ДОСКА ВОПРОСОВ - ТЕМА {room.current_theme}/{room.num_themes}*\n\n"
    
    # Кнопки для выбора вопроса
    keyboard = []
    for points in [10, 20, 30, 40, 50]:
        if not room.questions[room.current_theme][points]:
            keyboard.append([InlineKeyboardButton(
                f"❓ Вопрос за {points}",
                callback_data=f"q_{room.room_id}_{room.current_theme}_{points}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                f"✅ Вопрос {points}",
                callback_data="skip"
            )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        room.host_id,
        board_text + "*Выбери вопрос:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def question_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вопрос выбран"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "skip":
        return
    
    data_parts = query.data.split('_')
    room_id = int(data_parts[1])
    theme = int(data_parts[2])
    points = int(data_parts[3])
    
    if room_id not in rooms:
        await query.edit_message_text("❌ Комната не найдена!")
        return
    
    room = rooms[room_id]
    
    # Отмечаем вопрос
    room.questions[theme][points] = True
    room.current_question = points
    
    # Инициализируем списки для этого вопроса
    question_key = (theme, points)
    if question_key not in room.blocked_players:
        room.blocked_players[question_key] = []
        room.answered_players[question_key] = []
    
    # Кнопка "Время"
    keyboard = [[InlineKeyboardButton("⏱️ Время", callback_data=f"time_{room_id}_{theme}_{points}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg_text = (
        f"🎯 *ТЕМА {theme} - ВОПРОС ЗА {points}*\n\n"
        f"📖 Прочитай вопрос вслух\n\n"
        f"Нажми 'Время' когда будешь готов!"
    )
    
    await query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='Markdown')

async def time_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Таймер"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    room_id = int(data_parts[1])
    theme = int(data_parts[2])
    points = int(data_parts[3])
    
    if room_id not in rooms:
        await query.edit_message_text("❌ Комната не найдена!")
        return
    
    room = rooms[room_id]
    question_key = (theme, points)
    
    # Кнопка ответа для игроков
    keyboard = [[InlineKeyboardButton("➕ Ответить", callback_data=f"answer_{room_id}_{theme}_{points}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for player_id in room.players:
        await context.bot.send_message(
            player_id,
            "⏱️ *ВРЕМЯ!*\n\n"
            "⏳ У тебя есть 10 секунд чтобы ответить!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Отсчет для хоста
    for i in range(10, 0, -1):
        if room.paused:
            await context.bot.send_message(room.host_id, "⏸️ Игра на паузе")
            return
        
        if i % 2 == 0 or i <= 3:
            await context.bot.send_message(room.host_id, f"⏳ {i} сек...")
        await asyncio.sleep(1)
    
    await context.bot.send_message(room.host_id, "⏰ *ВРЕМЯ ВЫШЛО!*", parse_mode='Markdown')
    
    # Ждем перед переходом к следующему вопросу
    await asyncio.sleep(3)
    
    # Проверяем остались ли вопросы
    all_answered = all(room.questions[theme].values())
    
    if all_answered and theme < room.num_themes:
        # Переход на следующую тему
        await show_theme_transition(context, room)
    elif all_answered and theme >= room.num_themes:
        # Конец игры
        await show_final_score(context, room)
    else:
        # Следующий вопрос в теме
        room.current_theme = theme
        await send_board(context, room)

async def answer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Игрок ответил"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data_parts = query.data.split('_')
    room_id = int(data_parts[1])
    theme = int(data_parts[2])
    points = int(data_parts[3])
    
    if room_id not in rooms:
        await query.edit_message_text("❌ Комната не найдена!")
        return
    
    room = rooms[room_id]
    question_key = (theme, points)
    
    if user_id not in room.players:
        await query.edit_message_text("❌ Ты не игрок!")
        return
    
    # Проверяем, заблокирован ли игрок на этом вопросе
    if user_id in room.blocked_players.get(question_key, []):
        await query.edit_message_text("❌ *Ты уже ответил неправильно!*\nТы больше не можешь отвечать на этот вопрос.", parse_mode='Markdown')
        return
    
    # Проверяем, уже ли ответил
    if user_id in room.answered_players.get(question_key, []):
        await query.edit_message_text("⏳ *Ты уже ответил!*\nЖди оценки хоста...", parse_mode='Markdown')
        return
    
    user_name = room.players[user_id]["name"]
    room.answered_players[question_key].append(user_id)
    
    # Кнопки оценки для хоста
    keyboard = [
        [
            InlineKeyboardButton("✅ Верно", callback_data=f"correct_{room_id}_{theme}_{points}_{user_id}"),
            InlineKeyboardButton("❌ Неверно", callback_data=f"wrong_{room_id}_{theme}_{points}_{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        room.host_id,
        f"🎤 *{user_name} ОТВЕТИЛ!*\n\n"
        f"Оцени ответ:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    await query.edit_message_text("✋ *Ты ответил!*\nЖди оценки хоста...", parse_mode='Markdown')

async def correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ верный"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    room_id = int(data_parts[1])
    theme = int(data_parts[2])
    points = int(data_parts[3])
    user_id = int(data_parts[4])
    
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    room.players[user_id]["score"] += points
    
    await show_scores(context, room)
    await query.edit_message_text("✅ *Ответ засчитан!*", parse_mode='Markdown')

async def wrong_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ неверный"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    room_id = int(data_parts[1])
    theme = int(data_parts[2])
    points = int(data_parts[3])
    user_id = int(data_parts[4])
    
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    question_key = (theme, points)
    
    # Блокируем игрока на этом вопросе
    if user_id not in room.blocked_players[question_key]:
        room.blocked_players[question_key].append(user_id)
    
    room.players[user_id]["score"] -= points
    
    await show_scores(context, room)
    await query.edit_message_text("❌ *Ответ не засчитан!*\n\nИгрок заблокирован на этом вопросе.", parse_mode='Markdown')
    
    # Отправляем уведомление заблокированному игроку
    player_name = room.players[user_id]["name"]
    await context.bot.send_message(
        user_id,
        f"❌ *Твой ответ был неправильным!*\n\n"
        f"Ты больше не можешь отвечать на этот вопрос.",
        parse_mode='Markdown'
    )

async def show_scores(context: ContextTypes.DEFAULT_TYPE, room: GameRoom):
    """Показать текущие очки"""
    score_text = "📊 *ТЕКУЩИЙ СЧЕТ*\n\n"
    
    sorted_players = sorted(room.players.items(), key=lambda x: x[1]["score"], reverse=True)
    for i, (_, pdata) in enumerate(sorted_players, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        score_text += f"{emoji} {pdata['name']}: **{pdata['score']}** очков\n"
    
    for player_id in room.players:
        await context.bot.send_message(player_id, score_text, parse_mode='Markdown')
    
    for spectator_id in room.spectators:
        await context.bot.send_message(spectator_id, score_text, parse_mode='Markdown')
    
    await context.bot.send_message(room.host_id, score_text, parse_mode='Markdown')

async def show_theme_transition(context: ContextTypes.DEFAULT_TYPE, room: GameRoom):
    """Переход между темами"""
    theme_text = f"🎉 *КОНЕЦ ТЕМЫ {room.current_theme}*\n\n"
    
    sorted_players = sorted(room.players.items(), key=lambda x: x[1]["score"], reverse=True)
    theme_text += "*ТАБЛИЦА ЛИДЕРОВ:*\n"
    for i, (_, pdata) in enumerate(sorted_players, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        theme_text += f"{emoji} {pdata['name']}: **{pdata['score']}** очков\n"
    
    theme_text += f"\n⏳ Начинаем тему {room.current_theme + 1}..."
    
    for player_id in room.players:
        await context.bot.send_message(player_id, theme_text, parse_mode='Markdown')
    
    for spectator_id in room.spectators:
        await context.bot.send_message(spectator_id, theme_text, parse_mode='Markdown')
    
    await context.bot.send_message(room.host_id, theme_text, parse_mode='Markdown')
    
    await asyncio.sleep(3)
    
    room.current_theme += 1
    await send_board(context, room)

async def show_final_score(context: ContextTypes.DEFAULT_TYPE, room: GameRoom):
    """Финальный счет"""
    final_text = "🏆 *ФИНАЛЬНЫЙ СЧЕТ*\n\n"
    
    sorted_players = sorted(room.players.items(), key=lambda x: x[1]["score"], reverse=True)
    for i, (_, pdata) in enumerate(sorted_players, 1):
        if i == 1:
            final_text += f"🥇 *ПОБЕДИТЕЛЬ:* {pdata['name']} - **{pdata['score']}** очков\n"
        elif i == 2:
            final_text += f"🥈 {pdata['name']} - **{pdata['score']}** очков\n"
        elif i == 3:
            final_text += f"🥉 {pdata['name']} - **{pdata['score']}** очков\n"
        else:
            final_text += f"{i}. {pdata['name']} - **{pdata['score']}** очков\n"
    
    final_text += "\n✅ *Игра завершена!*"
    
    for player_id in room.players:
        await context.bot.send_message(player_id, final_text, parse_mode='Markdown')
    
    for spectator_id in room.spectators:
        await context.bot.send_message(spectator_id, final_text, parse_mode='Markdown')
    
    await context.bot.send_message(room.host_id, final_text, parse_mode='Markdown')
    
    # Очищаем комнату
    del rooms[room.room_id]
    for pid in list(room.players.keys()):
        if pid in user_rooms:
            del user_rooms[pid]
    for sid in list(room.spectators.keys()):
        if sid in user_rooms:
            del user_rooms[sid]

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершить игру"""
    user_id = update.effective_user.id
    
    if user_id not in user_rooms:
        await update.message.reply_text("❌ Ты не в комнате!")
        return
    
    room_id = user_rooms[user_id]
    room = rooms[room_id]
    
    if room.host_id != user_id:
        await update.message.reply_text("❌ Только хост может завершить игру!")
        return
    
    if not room.game_started:
        await update.message.reply_text("❌ Игра не началась!")
        return
    
    await show_final_score(context, room)

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пауза"""
    user_id = update.effective_user.id
    
    if user_id not in user_rooms:
        await update.message.reply_text("❌ Ты не в комнате!")
        return
    
    room_id = user_rooms[user_id]
    room = rooms[room_id]
    
    if room.host_id != user_id:
        await update.message.reply_text("❌ Только хост может остановить игру!")
        return
    
    if not room.game_started:
        await update.message.reply_text("❌ Игра не началась!")
        return
    
    room.paused = True
    await update.message.reply_text("⏸️ *Игра на паузе!*", parse_mode='Markdown')
    
    for player_id in room.players:
        await context.bot.send_message(player_id, "⏸️ Хост поставил игру на паузу", parse_mode='Markdown')

async def go_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возобновить"""
    user_id = update.effective_user.id
    
    if user_id not in user_rooms:
        await update.message.reply_text("❌ Ты не в комнате!")
        return
    
    room_id = user_rooms[user_id]
    room = rooms[room_id]
    
    if room.host_id != user_id:
        await update.message.reply_text("❌ Только хост может возобновить игру!")
        return
    
    if not room.game_started:
        await update.message.reply_text("❌ Игра не началась!")
        return
    
    room.paused = False
    await update.message.reply_text("▶️ *Игра возобновлена!*", parse_mode='Markdown')
    
    for player_id in room.players:
        await context.bot.send_message(player_id, "▶️ Хост возобновил игру", parse_mode='Markdown')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "👋 *Добро пожаловать в бот 'СВОЯ ИГРА'!*\n\n"
        "🎮 *КОМАНДЫ:*\n"
        "/create - Создать новую игровую комнату\n"
        "/room НОМЕР - Присоединиться как игрок\n"
        "/spectator НОМЕР - Присоединиться как зритель\n"
        "/game N - Начать игру (N = количество тем)\n"
        "/exit - Выйти из комнаты\n"
        "/stop - Пауза игры\n"
        "/go - Возобновить игру\n"
        "/end - Завершить игру\n\n"
        "🎯 *Пример:*\n"
        "`/create` - ты хост\n"
        "`/room 12345` - игрок присоединяется\n"
        "`/game 4` - начинаем игру с 4 темами\n\n"
        "Готов играть? 🎮",
        parse_mode='Markdown'
    )

async def setup_commands(bot):
    """Установка меню команд"""
    try:
        commands = [
            BotCommand("start", "Главное меню"),
            BotCommand("create", "Создать комнату"),
            BotCommand("room", "Присоединиться как игрок"),
            BotCommand("spectator", "Присоединиться как зритель"),
            BotCommand("game", "Начать игру"),
            BotCommand("exit", "Выйти из комнаты"),
            BotCommand("stop", "Пауза"),
            BotCommand("go", "Возобновить"),
            BotCommand("end", "Завершить"),
        ]
        await bot.set_my_commands(commands)
        print("✅ Меню команд установлено")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

async def post_init(application: Application):
    """Инициализация"""
    await setup_commands(application.bot)

def main():
    """Запуск бота"""
    print("🤖 Запуск бота 'СВОЯ ИГРА'...")
    
    application = Application.builder().token(TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("create", create_room))
    application.add_handler(CommandHandler("room", join_room))
    application.add_handler(CommandHandler("spectator", join_spectator))
    application.add_handler(CommandHandler("game", start_game))
    application.add_handler(CommandHandler("exit", exit_room))
    application.add_handler(CommandHandler("stop", stop_game))
    application.add_handler(CommandHandler("go", go_game))
    application.add_handler(CommandHandler("end", end_game))
    
    # Кнопки
    application.add_handler(CallbackQueryHandler(question_selected, pattern=r"^q_"))
    application.add_handler(CallbackQueryHandler(time_button, pattern=r"^time_"))
    application.add_handler(CallbackQueryHandler(answer_button, pattern=r"^answer_"))
    application.add_handler(CallbackQueryHandler(correct_answer, pattern=r"^correct_"))
    application.add_handler(CallbackQueryHandler(wrong_answer, pattern=r"^wrong_"))
    
    application.post_init = post_init
    
    print("✅ Бот готов! Запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
