import sqlite3
import matplotlib.pyplot as plt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler
import logging
import datetime
import io
import os

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Соединение с базой данных
conn = sqlite3.connect('mood_data.db')
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS moods (
    user_id INTEGER,
    username TEXT,
    mood TEXT,
    date TEXT
)""")
conn.commit()

# Интересная шкала настроения
mood_options = [
    ("1", "Полный штиль — ни эмоций, ни энергии"),
    ("2", "Тучи сгущаются, но держусь"),
    ("3", "Погода пасмурная, но жить можно"),
    ("4", "Ветер перемен — уже легче"),
    ("5", "На горизонте солнце — есть надежда"),
    ("6", "Светло, тепло, и сердце спокойно"),
    ("7", "Вау! Летаю от счастья и вдохновения")
]

# Команда /start
async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton(text, callback_data=value)] for value, text in mood_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Оцени своё настроение по шкале:", reply_markup=reply_markup)

# Обработка выбора настроения
async def mood_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    mood_value = query.data
    user = query.from_user
    username = user.username or user.first_name
    date = datetime.date.today().isoformat()
    mood_text = next(text for value, text in mood_options if value == mood_value)

    cursor.execute("INSERT INTO moods VALUES (?, ?, ?, ?)", (user.id, username, mood_text, date))
    conn.commit()

    await query.edit_message_text(f"Настроение записано: {mood_text}")

# Команда /stats
async def stats(update: Update, context: CallbackContext):
    cursor.execute("SELECT mood FROM moods")
    moods = [row[0] for row in cursor.fetchall()]

    if not moods:
        await update.message.reply_text("Пока нет данных о настроении.")
        return

    mood_counts = {text: moods.count(text) for _, text in mood_options if moods.count(text) > 0}
    labels = list(mood_counts.keys())
    values = list(mood_counts.values())

    plt.figure(figsize=(10, 5))
    bars = plt.barh(labels, values, color="skyblue")
    plt.xlabel("Количество")
    plt.title("Статистика настроения в чате")
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)

    await update.message.reply_photo(photo=buffer)

# Запуск бота
TOKEN = os.getenv("8038267384:AAGSbmkV7KG09UjyxXBiPkm0SIatxIIuzp0")
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CallbackQueryHandler(mood_callback))
app.run_polling()
