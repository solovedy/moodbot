import os
import sqlite3
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, JobQueue
)
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Токен бота
TOKEN = os.getenv("BOT_TOKEN")

# Подключение к БД
conn = sqlite3.connect("mood_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS moods (
    user_id INTEGER,
    mood INTEGER,
    date TEXT
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS cities (
    user_id INTEGER PRIMARY KEY,
    city TEXT
)''')
conn.commit()

# Напоминание
async def send_mood_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    keyboard = [
        [
            InlineKeyboardButton("😞", callback_data="1"),
            InlineKeyboardButton("🙁", callback_data="2"),
            InlineKeyboardButton("😐", callback_data="3"),
            InlineKeyboardButton("🙂", callback_data="4"),
            InlineKeyboardButton("😄", callback_data="5"),
            InlineKeyboardButton("🤩", callback_data="6"),
            InlineKeyboardButton("🔥", callback_data="7")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text="Как ты себя чувствуешь сегодня?", reply_markup=reply_markup)

# Получить среднее настроение
def get_average_mood(user_id, days=None):
    if days:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor.execute("SELECT mood FROM moods WHERE user_id=? AND date >= ?", (user_id, start_date))
    else:
        cursor.execute("SELECT mood FROM moods WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        return None
    return sum(row[0] for row in rows) / len(rows)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для отслеживания настроения. Используй /mood, чтобы указать своё настроение.")

async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("😞", callback_data="1"),
            InlineKeyboardButton("🙁", callback_data="2"),
            InlineKeyboardButton("😐", callback_data="3"),
            InlineKeyboardButton("🙂", callback_data="4"),
            InlineKeyboardButton("😄", callback_data="5"),
            InlineKeyboardButton("🤩", callback_data="6"),
            InlineKeyboardButton("🔥", callback_data="7")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери своё настроение:", reply_markup=reply_markup)

async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    mood = int(query.data)
    user_id = query.from_user.id
    date = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO moods (user_id, mood, date) VALUES (?, ?, ?)", (user_id, mood, date))
    conn.commit()
    await query.answer("Настроение сохранено! 😊")

async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    avg = get_average_mood(update.effective_user.id, 7)
    if avg is None:
        await update.message.reply_text("Нет данных за неделю.")
    else:
        await update.message.reply_text(f"Среднее настроение за неделю: {avg:.1f}")

async def mood_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    avg = get_average_mood(update.effective_user.id, 30)
    if avg is None:
        await update.message.reply_text("Нет данных за месяц.")
    else:
        await update.message.reply_text(f"Среднее настроение за месяц: {avg:.1f}")

async def mood_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    avg = get_average_mood(update.effective_user.id)
    if avg is None:
        await update.message.reply_text("Нет данных.")
    else:
        await update.message.reply_text(f"Среднее настроение за всё время: {avg:.1f}")

async def setcity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        city = " ".join(context.args)
        cursor.execute("REPLACE INTO cities (user_id, city) VALUES (?, ?)", (update.effective_user.id, city))
        conn.commit()
        await update.message.reply_text(f"Город установлен: {city}")
    else:
        await update.message.reply_text("Пожалуйста, укажи город после команды. Пример: /setcity Алматы")

async def mycity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT city FROM cities WHERE user_id=?", (update.effective_user.id,))
    row = cursor.fetchone()
    if row:
        city = row[0]
        await update.message.reply_text(f"Твой выбранный город: {city}")
    else:
        await update.message.reply_text("Город не установлен. Используй /setcity <город>.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""Вот что я умею:
/start — начать
/mood — указать настроение
/mood_week — настроение за неделю
/mood_month — настроение за месяц
/mood_all — настроение за всё время
/setcity <город> — установить свой город
/mycity — показать твой город
/help — показать список команд
""")

# Веб-сервер для поддержания активности
app = Flask('')
@app.route('/')
def home():
    return "Бот активен"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Запуск бота
if __name__ == "__main__":
    keep_alive()
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mood", mood))
    application.add_handler(CallbackQueryHandler(mood_callback))
    application.add_handler(CommandHandler("mood_week", mood_week))
    application.add_handler(CommandHandler("mood_month", mood_month))
    application.add_handler(CommandHandler("mood_all", mood_all))
    application.add_handler(CommandHandler("setcity", setcity))
    application.add_handler(CommandHandler("mycity", mycity))
    application.add_handler(CommandHandler("help", help_command))

    # Напоминание каждый день
    async def schedule_reminders(app):
        for chat_id in set(row[0] for row in cursor.execute("SELECT DISTINCT user_id FROM moods")):
            application.job_queue.run_daily(
                send_mood_reminder,
                time=datetime.now().time(),  # любое подходящее время
                chat_id=chat_id
            )
    application.job_queue.run_once(lambda c: schedule_reminders(application), when=1)
    application.run_polling()
