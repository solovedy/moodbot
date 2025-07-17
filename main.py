import os
import sqlite3
import datetime
import requests
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

# Настроение
mood_levels = {
    1: "😞 Очень плохо",
    2: "😕 Плохо",
    3: "😐 Так себе",
    4: "🙂 Нормально",
    5: "😊 Хорошо",
    6: "😄 Отлично",
    7: "🤩 Великолепно"
}

# Подключение к базе
conn = sqlite3.connect("mood_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS mood (
    user_id INTEGER,
    mood INTEGER,
    date TEXT
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    city TEXT
)''')
conn.commit()

# Погода
def get_weather(city):
    try:
        key = os.getenv("WEATHER_API_KEY")
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric&lang=ru"
        data = requests.get(url).json()
        temp = data["main"]["temp"]
        condition = data["weather"][0]["description"].capitalize()
        return f"🌤 Погода в {city}: {temp}°C, {condition}."
    except:
        return "Не удалось получить погоду 🌧"

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для отслеживания настроения.\nКоманда /mood чтобы отправить настроение!")

# Команда /mood
async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(text, callback_data=str(level))] for level, text in mood_levels.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Как у тебя настроение сегодня?", reply_markup=reply_markup)

# Обработка выбора настроения
async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    mood = int(query.data)
    user_id = query.from_user.id
    today = datetime.date.today().isoformat()

    cursor.execute("INSERT INTO mood (user_id, mood, date) VALUES (?, ?, ?)", (user_id, mood, today))
    conn.commit()

    await query.answer("Настроение сохранено!")
    
    # Рекомендации
    if mood <= 3:
        text = "💙 Похоже, не лучший день. Попробуй /breathe, /motivate или /task"
    elif mood <= 5:
        text = "💛 Спасибо за отклик! Можешь глянуть /joke для улыбки."
    else:
        text = "💚 Круто! Пусть день будет ярким ✨"

    await query.edit_message_text(f"Твоё настроение: {mood_levels[mood]}\n{text}")

# Команды статистики
def get_stats(user_id, days=None):
    if days:
        start_date = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        cursor.execute("SELECT mood FROM mood WHERE user_id = ? AND date >= ?", (user_id, start_date))
    else:
        cursor.execute("SELECT mood FROM mood WHERE user_id = ?", (user_id,))
    moods = cursor.fetchall()
    return [m[0] for m in moods]

async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    moods = get_stats(update.message.from_user.id, 7)
    await send_mood_summary(update, moods, "за неделю")

async def mood_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    moods = get_stats(update.message.from_user.id, 30)
    await send_mood_summary(update, moods, "за месяц")

async def mood_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    moods = get_stats(update.message.from_user.id)
    await send_mood_summary(update, moods, "за всё время")

async def send_mood_summary(update, moods, period):
    if not moods:
        await update.message.reply_text(f"Нет данных {period} 😕")
        return
    avg = sum(moods) / len(moods)
    mood_label = mood_levels[round(avg)]
    await update.message.reply_text(f"📊 Твоё среднее настроение {period}: {mood_label} ({avg:.2f})")

# Город
async def setcity(update: Update, context: CallbackContext):
    if context.args:
        city = " ".join(context.args)
        user_id = update.message.from_user.id
        cursor.execute("REPLACE INTO users (user_id, city) VALUES (?, ?)", (user_id, city))
        conn.commit()
        await update.message.reply_text(f"🏙 Город установлен: {city}")
    else:
        await update.message.reply_text("Введите город после команды, например: /setcity Almaty")

async def mycity(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    cursor.execute("SELECT city FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result and result[0]:
        await update.message.reply_text(f"Твой текущий город: {result[0]}")
    else:
        await update.message.reply_text("Город не установлен. Используй /setcity")

# Ежедневная погода и напоминание
async def daily_reminder(app):
    while True:
        now = datetime.datetime.now()
        if now.hour == 16 and now.minute == 0:
            cursor.execute("SELECT user_id, city FROM users")
            for user_id, city in cursor.fetchall():
                weather = get_weather(city) if city else "🏙 Город не указан. Установи командой /setcity"
                try:
                    await app.bot.send_message(chat_id=user_id, text=f"🌞 Не забудь поделиться настроением!\n{weather}")
                except:
                    continue
            await asyncio.sleep(60)
        await asyncio.sleep(30)

# /help
async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text("""📋 Доступные команды:
/start — начать
/mood — отметить настроение
/mood_week — настроение за неделю
/mood_month — настроение за месяц
/mood_all — настроение за всё время
/setcity [город] — установить город
/mycity — показать текущий город""")

# Flask для UptimeRobot
flask_app = Flask('')
@flask_app.route('/')
def home():
    return "Bot is alive"

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# Запуск
if __name__ == "__main__":
    import asyncio
    from telegram.ext import ApplicationBuilder

    keep_alive()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mood", mood))
    app.add_handler(CommandHandler("mood_week", mood_week))
    app.add_handler(CommandHandler("mood_month", mood_month))
    app.add_handler(CommandHandler("mood_all", mood_all))
    app.add_handler(CommandHandler("setcity", setcity))
    app.add_handler(CommandHandler("mycity", mycity))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(mood_callback))

    loop = asyncio.get_event_loop()
    loop.create_task(daily_reminder(app))

    app.run_polling()
