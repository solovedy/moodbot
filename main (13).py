import asyncio
import sqlite3
from datetime import datetime, timedelta  # ✅ исправлено
import matplotlib.pyplot as plt
import os
import requests
from io import BytesIO

from flask import Flask
import threading

from telegram import Update, ReplyKeyboardMarkup, InputFile  # ✅ добавлен InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# 📌 Настройка переменных
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEATHER_TOKEN = os.environ.get("WEATHER_API_KEY")

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
        "/mood_week — график за неделю\n"
        "/mood_month — график за месяц\n"
        "/mood_all — график за всё время\n"
        "/setcity [город] — установить город\n"
        "/mycity — показать текущий город\n"
        "/weather — узнать погоду\n"
        "/help — список команд"
    )

# 👋 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 😊 Я помогу тебе отслеживать настроение и погоду.\n\n"
        "Нажми /mood чтобы отметить, как ты себя чувствуешь 💬"
    )

# ⏰ Напоминание
pending_mood_users = {}

async def remind_if_no_mood(user_id, context):
    await asyncio.sleep(600)
    if pending_mood_users.get(user_id):
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="📩 Не забудь выбрать своё настроение — это займёт всего пару секунд!"
            )
        except Exception as e:
            print(f"Ошибка при отправке напоминания: {e}")
        finally:
            pending_mood_users.pop(user_id, None)

# 🌡 /mood
async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_mood"] = True
    user_id = update.effective_user.id
    pending_mood_users[user_id] = True
    await update.message.reply_text("Как ты себя чувствуешь сегодня?", reply_markup=mood_keyboard)
    asyncio.create_task(remind_if_no_mood(user_id, context))

# 💬 Обработка сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()
    user_id = update.effective_user.id

    if not context.user_data.get("waiting_for_mood"):
        return

    if message and message[0].isdigit():
        mood_value = int(message[0])
        if 1 <= mood_value <= 7:
            cursor.execute("INSERT INTO moods (user_id, mood, date) VALUES (?, ?, ?)", (
                user_id, mood_value, datetime.now().strftime("%Y-%m-%d")
            ))
            conn.commit()
            context.user_data["waiting_for_mood"] = False
            pending_mood_users.pop(user_id, None)

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
            await update.message.reply_text("Пожалуйста, выбери настроение от 1 до 7 😊")
    else:
        await update.message.reply_text("Пожалуйста, выбери настроение с помощью кнопок 😊")

# 📊 Построение и отправка графика настроения
async def send_mood_graph(update: Update, days: int = None):
    user_id = update.effective_user.id
    if days:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor.execute("SELECT date, mood FROM moods WHERE user_id = ? AND date >= ?", (user_id, start_date))
    else:
        cursor.execute("SELECT date, mood FROM moods WHERE user_id = ?", (user_id,))
    
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("Нет данных для построения графика 😕")
        return

    data = {}
    for date_str, mood in rows:
        data[date_str] = mood

    dates = sorted(data.keys())
    moods = [data[date] for date in dates]

    plt.figure(figsize=(10, 5))
    plt.plot(dates, moods, marker='o', linestyle='-', color='skyblue')
    plt.title("Настроение по дням")
    plt.xlabel("Дата")
    plt.ylabel("Настроение (1–7)")
    plt.xticks(rotation=45)
    plt.ylim(1, 7)
    plt.grid(True)
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await update.message.reply_photo(photo=InputFile(buf, filename="mood.png"))

# 📈 Команды
async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update, days=7)

async def mood_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update, days=30)

async def mood_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update, days=None)

# 🌐 Flask для Replit + UptimeRobot
app = Flask(__name__)

@app.route('/')
def home():
    return "Я жив! ✅"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# 🚀 Запуск
async def main():
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("mood", mood))
    bot_app.add_handler(CommandHandler("mood_week", mood_week))
    bot_app.add_handler(CommandHandler("mood_month", mood_month))
    bot_app.add_handler(CommandHandler("mood_all", mood_all))
    bot_app.add_handler(CommandHandler("setcity", set_city))
    bot_app.add_handler(CommandHandler("mycity", my_city))
    bot_app.add_handler(CommandHandler("weather", weather))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен! ✅")
    await bot_app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    threading.Thread(target=run_flask).start()

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e).startswith("This event loop is already running"):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
