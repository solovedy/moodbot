import sqlite3
import requests
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

# Telegram и OpenWeather ключи
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# Подключение к базе данных
conn = sqlite3.connect("moodbot.db", check_same_thread=False)
c = conn.cursor()

# Создание таблиц, если не существуют
c.execute('''CREATE TABLE IF NOT EXISTS moods (
    user_id INTEGER,
    mood INTEGER,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    city TEXT
)''')

conn.commit()

# 🌤 Получить погоду по городу
async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    c.execute("SELECT city FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if not row:
        await update.message.reply_text("Сначала укажи город командой /setcity [город]")
        return

    city = row[0]
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"

    try:
        response = requests.get(url).json()
        weather_description = response["weather"][0]["description"]
        temp = response["main"]["temp"]
        feels = response["main"]["feels_like"]
        humidity = response["main"]["humidity"]
        wind = response["wind"]["speed"]

        emoji = "🌤"
        if "дожд" in weather_description.lower(): emoji = "🌧"
        elif "ясно" in weather_description.lower(): emoji = "☀️"
        elif "облачно" in weather_description.lower(): emoji = "☁️"
        elif "снег" in weather_description.lower(): emoji = "❄️"

        # 🌈 Добавляем подпись, связанную с погодой
        mood_comment = ""
        if "rain" in weather_description.lower():
            mood_comment = "🌧️ Дождливо... Может казаться тоскливо, но плед и тёплый чай спасают атмосферу ☕"
        elif "cloud" in weather_description.lower():
            mood_comment = "☁️ Сегодня облачно — иногда и на душе может быть также. Подари себе немного тепла 💙"
        elif "clear" in weather_description.lower() or "sun" in weather_description.lower():
            mood_comment = "🌞 Ясно и солнечно! Отличный день для прогулки или любимого дела ✨"
        elif "snow" in weather_description.lower():
            mood_comment = "❄️ Снег за окном — как повод замедлиться и укутаться в уют 💭"

        await update.message.reply_text(
            f"{emoji} Погода в {city.title()}:\n"
            f"📍 {weather_description.capitalize()}\n"
            f"🌡 Температура: {temp}°C (Ощущается как {feels}°C)\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind} м/с\n\n"
            f"{mood_comment}"
        )
    except:
        await update.message.reply_text("Не удалось получить данные о погоде. Проверь название города.")

# Установка города
async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        city = " ".join(context.args)
        user_id = update.message.from_user.id
        c.execute("INSERT OR REPLACE INTO users (user_id, city) VALUES (?, ?)", (user_id, city))
        conn.commit()
        await update.message.reply_text(f"Город сохранён: {city}")
    else:
        await update.message.reply_text("Использование: /setcity [город]")

# Проверка текущего города
async def my_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    c.execute("SELECT city FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        await update.message.reply_text(f"Твой текущий город: {row[0]}")
    else:
        await update.message.reply_text("Ты ещё не установил город. Введи команду /setcity [город]")

# Обработка команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("1 😩"), KeyboardButton("2 😟"), KeyboardButton("3 😕")],
        [KeyboardButton("4 🙂"), KeyboardButton("5 😄"), KeyboardButton("6 🤩"), KeyboardButton("7 🥳")],
        [KeyboardButton("/weather")]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "Привет! Я бот для отслеживания твоего настроения.\n\n"
        "Выбери своё настроение ниже или напиши цифру от 1 до 7.\n"
        "А ещё я могу показывать погоду ☁️ — команда /weather\n\n"
        "Установить город: /setcity [название]\n"
        "Проверить город: /mycity",
        reply_markup=keyboard
    )

# Обработка сообщения с настроением
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    try:
        for i in range(1, 8):
            if text.strip().startswith(str(i)):
                mood_value = i
                break
        else:
            raise ValueError("Not a valid mood")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO moods (user_id, mood, timestamp) VALUES (?, ?, ?)", (user_id, mood_value, now))
        conn.commit()

        await update.message.reply_text("Настроение сохранено! 💖")

    except Exception as e:
        await update.message.reply_text("Пожалуйста, выбери настроение с помощью кнопок ниже или введи цифру от 1 до 7.")

# Запуск бота
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("setcity", set_city))
    app.add_handler(CommandHandler("mycity", my_city))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Бот запущен!")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e).startswith("This event loop is already running"):
            # Специально для Replit
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
            from flask import Flask
from threading import Thread

app_flask = Flask('')

@app_flask.route('/')
def home():
    return "I'm alive!"

def run():
    app_flask.run(host='0.0.0.0', port=8080)

Thread(target=run).start()
