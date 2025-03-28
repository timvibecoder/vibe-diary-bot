import os
import logging
from datetime import datetime, time, timedelta
import sqlite3
from dotenv import load_dotenv
from telegram import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Состояния разговора
WAITING_FOR_NOTE = 1
WAITING_FOR_TRANSFER_AMOUNT = 2
WAITING_FOR_TRANSFER_TARGET = 3

# Достижения
ACHIEVEMENTS = {
    'first_vibe': {
        'name': 'Первый вайб',
        'description': 'Получите свой первый вайб',
        'emoji': '🎯',
        'reward': 5
    },
    'vibe_master': {
        'name': 'Мастер вайба',
        'description': 'Достигните уровня "Суперзвезда"',
        'emoji': '🏆',
        'reward': 20
    },
    'social_butterfly': {
        'name': 'Социальная бабочка',
        'description': 'Передайте вайб 5 разным пользователям',
        'emoji': '🦋',
        'reward': 15
    },
    'daily_streak': {
        'name': 'Ежедневный стрик',
        'description': 'Получайте ежедневный бонус 5 дней подряд',
        'emoji': '🔥',
        'reward': 25
    },
    'note_taker': {
        'name': 'Заметочник',
        'description': 'Добавьте 10 заметок к изменениям вайба',
        'emoji': '📝',
        'reward': 10
    }
}

# Уровни вайба
VIBE_LEVELS = {
    0: {"name": "Начинающий", "emoji": "🌱", "required_vibe": 0},
    1: {"name": "Позитивный", "emoji": "⭐", "required_vibe": 10},
    2: {"name": "Энергичный", "emoji": "🌟", "required_vibe": 25},
    3: {"name": "Вайбовый", "emoji": "✨", "required_vibe": 50},
    4: {"name": "Суперзвезда", "emoji": "🌠", "required_vibe": 100},
    5: {"name": "Легенда", "emoji": "👑", "required_vibe": 200}
}

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('vibe_tracker.db')
        c = conn.cursor()
        
        # Создание таблицы для хранения вайба пользователей
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_vibes
            (user_id INTEGER,
             chat_id INTEGER,
             username TEXT,
             vibe_score INTEGER DEFAULT 0,
             last_update TIMESTAMP,
             last_daily_bonus TIMESTAMP,
             daily_streak INTEGER DEFAULT 0,
             PRIMARY KEY (user_id, chat_id))
        ''')
        
        # Создание таблицы для хранения истории изменений
        c.execute('''
            CREATE TABLE IF NOT EXISTS vibe_history
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER,
             chat_id INTEGER,
             change_amount INTEGER,
             note TEXT,
             timestamp TIMESTAMP,
             FOREIGN KEY (user_id, chat_id) REFERENCES user_vibes(user_id, chat_id))
        ''')
        
        # Новые таблицы
        c.execute('''
            CREATE TABLE IF NOT EXISTS achievements
            (user_id INTEGER,
             chat_id INTEGER,
             achievement_id TEXT,
             achieved_at TIMESTAMP,
             PRIMARY KEY (user_id, chat_id, achievement_id),
             FOREIGN KEY (user_id, chat_id) REFERENCES user_vibes(user_id, chat_id))
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS vibe_transfers
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             from_user_id INTEGER,
             to_user_id INTEGER,
             chat_id INTEGER,
             amount INTEGER,
             timestamp TIMESTAMP,
             FOREIGN KEY (from_user_id, chat_id) REFERENCES user_vibes(user_id, chat_id),
             FOREIGN KEY (to_user_id, chat_id) REFERENCES user_vibes(user_id, chat_id))
        ''')
        
        conn.commit()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()

def get_level_info(vibe_score):
    current_level = 0
    for level, info in sorted(VIBE_LEVELS.items(), reverse=True):
        if vibe_score >= info["required_vibe"]:
            current_level = level
            break
    
    current_info = VIBE_LEVELS[current_level]
    next_level = current_level + 1
    
    if next_level in VIBE_LEVELS:
        next_info = VIBE_LEVELS[next_level]
        progress = (vibe_score - current_info["required_vibe"]) / (next_info["required_vibe"] - current_info["required_vibe"]) * 100
        progress = min(100, max(0, progress))
        return current_info, next_info, progress
    
    return current_info, None, 100

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для отслеживания вайба.\n\n"
        "Команды:\n"
        "/plusvibe - добавить вайб (можно с заметкой)\n"
        "/minusvibe - уменьшить вайб (можно с заметкой)\n"
        "/myvibe - проверить свой текущий вайб\n"
        "/topvibe - показать топ пользователей по вайбу\n"
        "/history - показать историю изменений вайба\n"
        "/levels - информация об уровнях вайба\n"
        "/transfer - передать вайб другому пользователю\n"
        "/achievements - посмотреть свои достижения\n"
        "/daily - получить ежедневный бонус"
    )

# Добавление вайба
async def plus_vibe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    username = update.message.from_user.username or update.message.from_user.first_name
    
    # Проверяем, есть ли аргументы в команде
    args = context.args
    amount = 1
    if args:
        try:
            amount = int(args[0])
            if amount <= 0:
                await update.message.reply_text("Пожалуйста, укажите положительное число.")
                return
            if amount > 100:  # Ограничиваем максимальное значение
                await update.message.reply_text("Максимальное значение для одного изменения: 100")
                return
        except ValueError:
            await update.message.reply_text("Пожалуйста, укажите корректное число.")
            return
    
    # Сохраняем информацию для следующего шага
    context.user_data['vibe_change'] = {'amount': amount, 'user_id': user_id, 'chat_id': chat_id, 'username': username}
    
    keyboard = [
        [
            InlineKeyboardButton("Без заметки", callback_data='no_note'),
            InlineKeyboardButton("Добавить заметку", callback_data='add_note')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Хотите добавить заметку к изменению вайба (+{amount})?",
        reply_markup=reply_markup
    )

# Уменьшение вайба
async def minus_vibe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    username = update.message.from_user.username or update.message.from_user.first_name
    
    # Проверяем, есть ли аргументы в команде
    args = context.args
    amount = 1
    if args:
        try:
            amount = int(args[0])
            if amount <= 0:
                await update.message.reply_text("Пожалуйста, укажите положительное число.")
                return
            if amount > 100:  # Ограничиваем максимальное значение
                await update.message.reply_text("Максимальное значение для одного изменения: 100")
                return
        except ValueError:
            await update.message.reply_text("Пожалуйста, укажите корректное число.")
            return
    
    # Сохраняем информацию для следующего шага
    context.user_data['vibe_change'] = {'amount': -amount, 'user_id': user_id, 'chat_id': chat_id, 'username': username}
    
    keyboard = [
        [
            InlineKeyboardButton("Без заметки", callback_data='no_note'),
            InlineKeyboardButton("Добавить заметку", callback_data='add_note')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Хотите добавить заметку к изменению вайба (-{amount})?",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'no_note':
        await update_vibe(query, context, None)
    elif query.data == 'add_note':
        await query.edit_message_text("Пожалуйста, напишите заметку к изменению вайба:")
        return WAITING_FOR_NOTE

async def note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    await update_vibe(update, context, note)
    return ConversationHandler.END

async def update_vibe(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str = None):
    vibe_change = context.user_data.get('vibe_change')
    if not vibe_change:
        if isinstance(update, Update):
            await update.message.reply_text("Произошла ошибка. Попробуйте снова.")
        else:
            await update.edit_message_text("Произошла ошибка. Попробуйте снова.")
        return
    
    conn = sqlite3.connect('vibe_tracker.db')
    c = conn.cursor()
    
    try:
        # Получаем текущий вайб
        c.execute('SELECT vibe_score FROM user_vibes WHERE user_id = ? AND chat_id = ?',
                 (vibe_change['user_id'], vibe_change['chat_id']))
        result = c.fetchone()
        current_vibe = result[0] if result else 0
        
        # Проверяем, не превысит ли изменение лимиты
        new_vibe = current_vibe + vibe_change['amount']
        if new_vibe > 1000000:  # Максимальный вайб
            if isinstance(update, Update):
                await update.message.reply_text("Достигнут максимальный уровень вайба (1,000,000)")
            else:
                await update.edit_message_text("Достигнут максимальный уровень вайба (1,000,000)")
            return
        if new_vibe < -1000000:  # Минимальный вайб
            if isinstance(update, Update):
                await update.message.reply_text("Достигнут минимальный уровень вайба (-1,000,000)")
            else:
                await update.edit_message_text("Достигнут минимальный уровень вайба (-1,000,000)")
            return
        
        # Обновляем вайб
        c.execute('''
            INSERT INTO user_vibes (user_id, chat_id, username, vibe_score, last_update)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
            vibe_score = ?,
            last_update = ?
        ''', (vibe_change['user_id'], vibe_change['chat_id'], vibe_change['username'], 
              new_vibe, datetime.now(), new_vibe, datetime.now()))
        
        # Добавляем запись в историю
        c.execute('''
            INSERT INTO vibe_history (user_id, chat_id, change_amount, note, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (vibe_change['user_id'], vibe_change['chat_id'], vibe_change['amount'], note, datetime.now()))
        
        # Получаем обновленный счет
        c.execute('SELECT vibe_score FROM user_vibes WHERE user_id = ? AND chat_id = ?',
                  (vibe_change['user_id'], vibe_change['chat_id']))
        score = c.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        # Получаем информацию об уровне
        current_level, next_level, progress = get_level_info(score)
        
        message = f"{'✨ Вайб повышен' if vibe_change['amount'] > 0 else '😔 Вайб понижен'}!\n"
        message += f"Текущий вайб: {score}\n"
        message += f"Уровень: {current_level['emoji']} {current_level['name']}\n"
        
        if next_level:
            message += f"Прогресс до следующего уровня: {progress:.1f}%"
        
        if note:
            message += f"\nЗаметка: {note}"
        
        if isinstance(update, Update):
            await update.message.reply_text(message)
        else:  # CallbackQuery
            await update.edit_message_text(message)
        
    except Exception as e:
        conn.rollback()
        await update.message.reply_text("Произошла ошибка при изменении вайба. Попробуйте позже.")
        logging.error(f"Error in update_vibe: {e}")
    
    finally:
        conn.close()

# Проверка своего вайба
async def my_vibe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    conn = sqlite3.connect('vibe_tracker.db')
    c = conn.cursor()
    
    c.execute('SELECT vibe_score FROM user_vibes WHERE user_id = ? AND chat_id = ?',
              (user_id, chat_id))
    result = c.fetchone()
    
    if result:
        score = result[0]
        current_level, next_level, progress = get_level_info(score)
        
        message = f"🌟 Ваш текущий вайб: {score}\n"
        message += f"Уровень: {current_level['emoji']} {current_level['name']}\n"
        
        if next_level:
            message += f"До следующего уровня ({next_level['emoji']} {next_level['name']}): {progress:.1f}%"
        
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("У вас пока нет вайба. Используйте /plusvibe или /minusvibe!")
    
    conn.close()

# Топ пользователей по вайбу
async def top_vibe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    
    conn = sqlite3.connect('vibe_tracker.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT username, vibe_score 
        FROM user_vibes 
        WHERE chat_id = ? 
        ORDER BY vibe_score DESC 
        LIMIT 10
    ''', (chat_id,))
    
    results = c.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("Пока никто не набрал вайб в этом чате!")
        return
    
    message = "🏆 Топ пользователей по вайбу:\n\n"
    for i, (username, score) in enumerate(results, 1):
        level_info = get_level_info(score)[0]
        message += f"{i}. {level_info['emoji']} {username}: {score}\n"
    
    await update.message.reply_text(message)

# История изменений вайба
async def vibe_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    conn = sqlite3.connect('vibe_tracker.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT change_amount, note, timestamp
        FROM vibe_history
        WHERE user_id = ? AND chat_id = ?
        ORDER BY timestamp DESC
        LIMIT 10
    ''', (user_id, chat_id))
    
    results = c.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("У вас пока нет истории изменений вайба!")
        return
    
    message = "📝 Последние изменения вайба:\n\n"
    for change_amount, note, timestamp in results:
        dt = datetime.fromisoformat(timestamp)
        emoji = "✨" if change_amount > 0 else "😔"
        message += f"{dt.strftime('%d.%m %H:%M')} {emoji} {change_amount:+d}"
        if note:
            message += f" - {note}"
        message += "\n"
    
    await update.message.reply_text(message)

# Информация об уровнях
async def levels_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = "📊 Уровни вайба:\n\n"
    for level, info in sorted(VIBE_LEVELS.items()):
        message += f"{info['emoji']} {info['name']}: от {info['required_vibe']} вайба\n"
    
    await update.message.reply_text(message)

# Передача вайба
async def transfer_vibe_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Сколько вайба вы хотите передать? (введите число)"
    )
    return WAITING_FOR_TRANSFER_AMOUNT

async def transfer_vibe_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount <= 0:
            await update.message.reply_text("Пожалуйста, введите положительное число.")
            return WAITING_FOR_TRANSFER_AMOUNT
        
        # Проверяем, достаточно ли вайба у пользователя
        conn = sqlite3.connect('vibe_tracker.db')
        c = conn.cursor()
        c.execute('SELECT vibe_score FROM user_vibes WHERE user_id = ? AND chat_id = ?',
                  (update.message.from_user.id, update.message.chat_id))
        result = c.fetchone()
        conn.close()
        
        if not result or result[0] < amount:
            await update.message.reply_text("У вас недостаточно вайба для передачи!")
            return ConversationHandler.END
        
        context.user_data['transfer_amount'] = amount
        await update.message.reply_text(
            "Отлично! Теперь перешлите любое сообщение от пользователя, "
            "которому хотите передать вайб, или отправьте его @username"
        )
        return WAITING_FOR_TRANSFER_TARGET
        
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число.")
        return WAITING_FOR_TRANSFER_AMOUNT

async def transfer_vibe_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get('transfer_amount')
    if not amount:
        await update.message.reply_text("Произошла ошибка. Начните передачу заново с /transfer")
        return ConversationHandler.END
    
    target_user = None
    if update.message.forward_from:
        target_user = update.message.forward_from
    elif update.message.text and update.message.text.startswith('@'):
        username = update.message.text[1:]
        conn = sqlite3.connect('vibe_tracker.db')
        c = conn.cursor()
        c.execute('SELECT user_id FROM user_vibes WHERE username = ? AND chat_id = ?',
                  (username, update.message.chat_id))
        result = c.fetchone()
        conn.close()
        
        if result:
            target_user = await context.bot.get_chat_member(update.message.chat_id, result[0])
            target_user = target_user.user
    
    if not target_user:
        await update.message.reply_text(
            "Не удалось найти пользователя. Пожалуйста, перешлите сообщение от пользователя "
            "или укажите правильный @username"
        )
        return WAITING_FOR_TRANSFER_TARGET
    
    if target_user.id == update.message.from_user.id:
        await update.message.reply_text("Вы не можете передать вайб самому себе!")
        return ConversationHandler.END
    
    await transfer_vibe(update, context, target_user, amount)
    return ConversationHandler.END

async def transfer_vibe(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user, amount):
    conn = sqlite3.connect('vibe_tracker.db')
    c = conn.cursor()
    
    try:
        # Снимаем вайб у отправителя
        c.execute('''
            UPDATE user_vibes 
            SET vibe_score = vibe_score - ?
            WHERE user_id = ? AND chat_id = ?
        ''', (amount, update.message.from_user.id, update.message.chat_id))
        
        # Добавляем вайб получателю
        c.execute('''
            INSERT INTO user_vibes (user_id, chat_id, username, vibe_score, last_update)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
            vibe_score = vibe_score + ?,
            last_update = ?
        ''', (target_user.id, update.message.chat_id, target_user.username or target_user.first_name,
              amount, datetime.now(), amount, datetime.now()))
        
        # Записываем трансфер
        c.execute('''
            INSERT INTO vibe_transfers (from_user_id, to_user_id, chat_id, amount, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (update.message.from_user.id, target_user.id, update.message.chat_id, amount, datetime.now()))
        
        conn.commit()
        
        # Проверяем достижение social_butterfly
        c.execute('''
            SELECT COUNT(DISTINCT to_user_id) 
            FROM vibe_transfers 
            WHERE from_user_id = ? AND chat_id = ?
        ''', (update.message.from_user.id, update.message.chat_id))
        
        unique_transfers = c.fetchone()[0]
        if unique_transfers >= 5:
            await check_and_grant_achievement(update, context, 'social_butterfly')
        
        await update.message.reply_text(
            f"✨ Успешно передано {amount} вайба пользователю "
            f"{target_user.username or target_user.first_name}!"
        )
        
    except Exception as e:
        conn.rollback()
        await update.message.reply_text("Произошла ошибка при передаче вайба. Попробуйте позже.")
        logging.error(f"Error in transfer_vibe: {e}")
    
    finally:
        conn.close()

# Ежедневный бонус
async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
        username = update.message.from_user.username or update.message.from_user.first_name
        now = datetime.now()
        
        conn = sqlite3.connect('vibe_tracker.db')
        c = conn.cursor()
        
        # Проверяем или создаем запись пользователя
        c.execute('''
            INSERT OR IGNORE INTO user_vibes 
            (user_id, chat_id, username, vibe_score, last_update, last_daily_bonus, daily_streak)
            VALUES (?, ?, ?, 0, ?, NULL, 0)
        ''', (user_id, chat_id, username, now))
        conn.commit()
        
        # Получаем текущие данные пользователя
        c.execute('''
            SELECT vibe_score, last_daily_bonus, daily_streak
            FROM user_vibes
            WHERE user_id = ? AND chat_id = ?
        ''', (user_id, chat_id))
        
        vibe_score, last_bonus_str, streak = c.fetchone()
        
        # Проверяем время последнего бонуса
        if last_bonus_str:
            last_bonus = datetime.fromisoformat(last_bonus_str)
            time_since_last = now - last_bonus
            
            # Если прошло меньше 24 часов
            if time_since_last < timedelta(days=1):
                time_left = timedelta(days=1) - time_since_last
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                await update.message.reply_text(
                    f"⏳ Следующий бонус будет доступен через {hours} ч. {minutes} мин."
                )
                conn.close()
                return
            
            # Если прошло больше 48 часов, сбрасываем стрик
            if time_since_last > timedelta(days=2):
                streak = 0
        
        # Увеличиваем стрик и рассчитываем бонус
        streak += 1
        bonus_amount = 5 + min(streak - 1, 5)  # Базовый бонус 5 + до 5 за стрик
        new_vibe_score = vibe_score + bonus_amount
        
        # Обновляем данные пользователя одним запросом
        c.execute('''
            UPDATE user_vibes
            SET vibe_score = ?,
                last_daily_bonus = ?,
                daily_streak = ?,
                last_update = ?
            WHERE user_id = ? AND chat_id = ?
        ''', (new_vibe_score, now, streak, now, user_id, chat_id))
        
        # Записываем в историю
        c.execute('''
            INSERT INTO vibe_history (user_id, chat_id, change_amount, note, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, chat_id, bonus_amount, f"Ежедневный бонус (стрик: {streak})", now))
        
        conn.commit()
        
        # Проверяем достижение daily_streak
        if streak >= 5:
            await check_and_grant_achievement(update, context, 'daily_streak')
        
        message = f"🎁 Получен ежедневный бонус: +{bonus_amount} вайба!\n"
        message += f"🔥 Текущий стрик: {streak} дней\n"
        message += f"💫 Новый баланс: {new_vibe_score} вайба"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        logging.error(f"Error in daily_bonus: {str(e)}")
        logging.exception("Full error traceback:")
        await update.message.reply_text("Произошла ошибка при получении бонуса. Попробуйте позже.")
    
    finally:
        if 'conn' in locals():
            conn.close()

# Достижения
async def check_and_grant_achievement(update: Update, context: ContextTypes.DEFAULT_TYPE, achievement_id: str):
    if achievement_id not in ACHIEVEMENTS:
        return
    
    conn = sqlite3.connect('vibe_tracker.db')
    c = conn.cursor()
    
    try:
        # Проверяем, не получено ли уже достижение
        c.execute('''
            SELECT 1 FROM achievements
            WHERE user_id = ? AND chat_id = ? AND achievement_id = ?
        ''', (update.message.from_user.id, update.message.chat_id, achievement_id))
        
        if c.fetchone():
            return
        
        # Добавляем достижение
        c.execute('''
            INSERT INTO achievements (user_id, chat_id, achievement_id, achieved_at)
            VALUES (?, ?, ?, ?)
        ''', (update.message.from_user.id, update.message.chat_id, achievement_id, datetime.now()))
        
        # Начисляем награду
        achievement = ACHIEVEMENTS[achievement_id]
        c.execute('''
            UPDATE user_vibes
            SET vibe_score = vibe_score + ?
            WHERE user_id = ? AND chat_id = ?
        ''', (achievement['reward'], update.message.from_user.id, update.message.chat_id))
        
        conn.commit()
        
        # Уведомляем пользователя
        message = f"🎉 Получено достижение!\n\n"
        message += f"{achievement['emoji']} {achievement['name']}\n"
        message += f"📝 {achievement['description']}\n"
        message += f"🎁 Награда: +{achievement['reward']} вайба"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        conn.rollback()
        logging.error(f"Error in check_and_grant_achievement: {e}")
    
    finally:
        conn.close()

async def show_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    conn = sqlite3.connect('vibe_tracker.db')
    c = conn.cursor()
    
    try:
        c.execute('''
            SELECT achievement_id, achieved_at
            FROM achievements
            WHERE user_id = ? AND chat_id = ?
        ''', (user_id, chat_id))
        
        achieved = {row[0]: row[1] for row in c.fetchall()}
        
        message = "🏆 Ваши достижения:\n\n"
        
        for achievement_id, achievement in ACHIEVEMENTS.items():
            if achievement_id in achieved:
                dt = datetime.fromisoformat(achieved[achievement_id])
                message += f"{achievement['emoji']} {achievement['name']} - ✅ {dt.strftime('%d.%m.%Y')}\n"
                message += f"└ {achievement['description']}\n"
            else:
                message += f"❌ {achievement['name']}\n"
                message += f"└ {achievement['description']}\n"
            message += "\n"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        logging.error(f"Error in show_achievements: {e}")
        await update.message.reply_text("Произошла ошибка при получении достижений. Попробуйте позже.")
    
    finally:
        conn.close()

def main():
    # Инициализация базы данных
    init_db()
    
    # Создание и настройка бота
    application = Application.builder().token(TOKEN).build()
    
    # Создание обработчика разговора для заметок
    note_conv_handler = ConversationHandler(
        entry_points=[],  # Пустые entry_points, так как мы используем callback
        states={
            WAITING_FOR_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, note_handler)]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
    )
    
    # Создание обработчика разговора для передачи вайба
    transfer_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('transfer', transfer_vibe_start)],
        states={
            WAITING_FOR_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_vibe_amount)],
            WAITING_FOR_TRANSFER_TARGET: [MessageHandler(filters.TEXT | filters.FORWARDED, transfer_vibe_target)]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
    )
    
    # Добавление обработчиков команд в правильном порядке
    application.add_handler(CommandHandler("plusvibe", plus_vibe))
    application.add_handler(CommandHandler("minusvibe", minus_vibe))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(note_conv_handler)
    application.add_handler(transfer_conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myvibe", my_vibe))
    application.add_handler(CommandHandler("topvibe", top_vibe))
    application.add_handler(CommandHandler("history", vibe_history))
    application.add_handler(CommandHandler("levels", levels_info))
    application.add_handler(CommandHandler("daily", daily_bonus))
    application.add_handler(CommandHandler("achievements", show_achievements))
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main() 