import asyncio
import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import os
import requests
from io import BytesIO

from flask import Flask
from threading import Thread

from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# 📌 Настройка переменных
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEATHER_TOKEN = os.environ.get("WEATHER_TOKEN")

# 🛠️ База данных
conn = sqlite3.connect("mood.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS moods (
        user_id INTEGER,
        mood INTEGER,
        date TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS cities (
        user_id INTEGER PRIMARY KEY,
        city TEXT
    )
''')
conn.commit()

# 🧠 Подписи к настроениям
mood_keyboard = ReplyKeyboardMarkup(
    [[
        "1 💀 Хочу исчезнуть", "2 🌧️ Всё валится из рук", "3 😕 День какой-то не такой"
    ], [
        "4 😐 Просто день", "5 🌿 Внутренний дзен", "6 🌞 На подъёме!", "7 🚀 Я лечу от счастья!"
    ]],
    resize_keyboard=True
)

# 🌤 Получение погоды
def get_weather(city: str) -> str:
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_TOKEN}&units=metric&lang=ru"
    response = requests.get(url)
    if response.status_code != 200:
        return "Не удалось получить погоду 😢"

    data = response.json()
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    description = data['weather'][0]['description'].capitalize()
    emoji = "☀️" if "clear" in data['weather'][0]['main'].lower() else "🌥️"
    return f"{emoji} В {city} сейчас {temp}°C, ощущается как {feels_like}°C. {description}."

# 🌤 /weather
async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT city FROM cities WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        await update.message.reply_text("Сначала укажи свой город с помощью /setcity 🌍")
        return
    city = row[0]
    await update.message.reply_text(get_weather(city))

# 📍 /setcity
async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши так: /setcity [город], например: /setcity Алматы")
        return
    city = " ".join(context.args)
    user_id = update.effective_user.id
    cursor.execute("INSERT OR REPLACE INTO cities (user_id, city) VALUES (?, ?)", (user_id, city))
    conn.commit()
    await update.message.reply_text(f"Твой город сохранён: {city} ✅")

# 📍 /mycity
async def my_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT city FROM cities WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        await update.message.reply_text(f"Твой город: {row[0]} 🏙️")
    else:
        await update.message.reply_text("Ты ещё не указал город. Используй /setcity [город]")

# 🆘 /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Команды бота:\n"
        "/start — начать общение\n"
        "/mood — выбрать настроение\n"
        "/mood_week — график настроения за неделю\n"
        "/setcity [город] — установить город\n"
        "/mycity — показать текущий город\n"
        "/weather — узнать погоду в своём городе\n"
        "/help — список команд"
    )

# 👋 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 😊 Я помогу тебе отслеживать настроение и погоду.\n\n"
        "Нажми /mood чтобы отметить, как ты себя чувствуешь 💬"
    )

# 🌡 /mood
async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Как ты себя чувствуешь сегодня?", reply_markup=mood_keyboard)

# 💬 обработка настроения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    user_id = update.effective_user.id

    if message[0].isdigit():
        mood_value = int(message[0])
        cursor.execute("INSERT INTO moods (user_id, mood, date) VALUES (?, ?, ?)", (
            user_id, mood_value, datetime.now().strftime("%Y-%m-%d")
        ))
        conn.commit()

        responses = {
            1: "😩 Держись! Попробуй /breathe или /advice — они помогут немного облегчить день.",
            2: "😣 Это пройдёт. Попробуй /motivate или /breathe — тебе станет легче!",
            3: "😕 Надеюсь, день станет лучше. Загляни в /joke для улыбки.",
            4: "🙂 Неплохо! Продолжай в том же духе.",
            5: "😌 Спокойствие — это круто. Наслаждайся моментом!",
            6: "😀 Отлично! Заряжай позитивом других!",
            7: "🤩 Ура! Такое настроение вдохновляет! ⭐"
        }

        await update.message.reply_text(responses[mood_value])
    else:
        await update.message.reply_text("Пожалуйста, выбери настроение с помощью кнопок 😊")

# 📊 /mood_week
async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    one_week_ago = datetime.now() - timedelta(days=6)

    cursor.execute('''
        SELECT date, AVG(mood) FROM moods
        WHERE user_id = ? AND date >= ?
        GROUP BY date
    ''', (user_id, one_week_ago.strftime("%Y-%m-%d")))
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("У тебя пока нет данных за неделю.")
        return

    dates = [datetime.strptime(row[0], "%Y-%m-%d").strftime("%d.%m") for row in rows]
    moods = [row[1] for row in rows]

    plt.figure(figsize=(7, 4))
    plt.plot(dates, moods, marker='o', linestyle='-', color='mediumpurple')
    plt.title("Твоё настроение за неделю 💭")
    plt.ylim(0, 7.5)
    plt.grid(True)
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    await update.message.reply_photo(photo=InputFile(buf, filename="mood.png"))
    plt.close()

# 🌐 Flask-сервер для UptimeRobot
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "I'm alive! 🤖"

def run():
    app_flask.run(host='0.0.0.0', port=8080)

# 🚀 Запуск
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mood", mood))
    app.add_handler(CommandHandler("mood_week", mood_week))
    app.add_handler(CommandHandler("setcity", set_city))
    app.add_handler(CommandHandler("mycity", my_city))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен! ✅")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    Thread(target=run).start()

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e).startswith("This event loop is already running"):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
