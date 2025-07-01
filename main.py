import sqlite3
import matplotlib.pyplot as plt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import logging
import datetime
import io

# Логирование
logging.basicConfig(level=logging.INFO)

# Подключение к БД
conn = sqlite3.connect('mood_data.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS moods (
    user_id INTEGER,
    username TEXT,
    mood TEXT,
    date TEXT
)""")
conn.commit()

# Шкала настроения
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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(text, callback_data=value)] for value, text in mood_options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Привет! Оцени своё настроение по шкале:", reply_markup=reply_markup)

# Обработка выбора настроения
async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mood_value = query.data
    user = query.from_user
    username = user.username or user.first_name
    date = datetime.date.today().isoformat()
    mood_text = next(text for value, text in mood_options if value == mood_value)

    cursor.execute("INSERT INTO moods VALUES (?, ?, ?, ?)", (user.id, username, mood_text, date))
    conn.commit()

    await query.edit_message_text(f"📝 Настроение записано: {mood_text}")

# Команда /stats — общее настроение
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT mood FROM moods")
    moods = [row[0] for row in cursor.fetchall()]
    if not moods:
        await update.message.reply_text("😕 Пока нет данных о настроении.")
        return

    mood_counts = {text: moods.count(text) for _, text in mood_options if moods.count(text) > 0}
    labels = list(mood_counts.keys())
    values = list(mood_counts.values())

    plt.figure(figsize=(10, 5))
    bars = plt.barh(labels, values, color="skyblue")
    plt.xlabel("Количество")
    plt.title("📊 Статистика настроения чата")
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)
    await update.message.reply_photo(photo=buffer)

# Команда /my_mood_summary — личный итог за неделю
async def my_mood_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)

    cursor.execute("SELECT mood FROM moods WHERE user_id=? AND date>=?", (user.id, week_ago.isoformat()))
    mood_rows = cursor.fetchall()

    if not mood_rows:
        await update.message.reply_text("📭 У вас пока нет записей за последнюю неделю.")
        return

    # Определяем числовые значения
    mood_values = []
    for row in mood_rows:
        for value, text in mood_options:
            if text == row[0]:
                mood_values.append(int(value))

    avg_mood = round(sum(mood_values) / len(mood_values), 1)

    # Подбор ответа
    if avg_mood <= 3:
        text = (
            f"💔 За последнюю неделю ваше среднее настроение: *{avg_mood}*\n\n"
            "Берегите себя. Всё обязательно наладится 💙\n"
            "Рекомендую попробовать:\n"
            "`/breathe` — дыхательные упражнения\n"
            "`/motivate` — мотивация\n"
            "`/advice` — советы для улучшения состояния"
        )
    elif 4 <= avg_mood <= 5:
        text = (
            f"🙂 Ваше среднее настроение за неделю: *{avg_mood}*\n\n"
            "Вы держитесь молодцом! 💪\n"
            "Попробуйте отвлечься немного: `/joke` — случайная шутка 😄"
        )
    else:
        text = (
            f"🌟 Ваше среднее настроение за неделю: *{avg_mood}*\n\n"
            "Продолжайте в том же духе! Пусть всё остаётся так же хорошо ❤️"
        )

    await update.message.reply_text(text, parse_mode="Markdown")

# Запуск бота
TOKEN = "8038267384:AAGSbmkV7KG09UjyxXBiPkm0SIatxIIuzp0"

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("my_mood_summary", my_mood_summary))
    app.add_handler(CallbackQueryHandler(mood_callback))
    
    app.run_polling()
