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

# 🌡 /mood
async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Как ты себя чувствуешь сегодня?", reply_markup=mood_keyboard)

# 💬 обработка настроения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    user_id = update.effective_user.id

    # ⛔️ Проверка: если это группа и бот не был упомянут — выходим
    if update.message.chat.type != "private" and not message.lower().startswith(f"@{context.bot.username.lower()}"):
        return

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
# 📊 Общая функция построения графика (обновлённая)
async def send_mood_graph(update: Update, days: int = None):
    user_id = update.effective_user.id
    if days:
        since = datetime.now() - timedelta(days=days - 1)
        cursor.execute('''
            SELECT date, mood FROM moods
            WHERE user_id = ? AND date >= ?
            ORDER BY date
        ''', (user_id, since.strftime("%Y-%m-%d")))
    else:
        cursor.execute('''
            SELECT date, mood FROM moods
            WHERE user_id = ?
            ORDER BY date
        ''', (user_id,))

    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("Пока нет данных для отображения графика 📉")
        return

    # 🎯 Обработка данных
    dates = [datetime.strptime(row[0], "%Y-%m-%d").strftime("%d.%m") for row in rows]
    moods = [row[1] for row in rows]

    mood_labels = {
        1: "💀", 2: "🌧️", 3: "😕",
        4: "😐", 5: "🌿", 6: "🌞", 7: "🚀"
    }

    colors = {
        1: "#6b6b6b", 2: "#5c88c4", 3: "#9e9e9e",
        4: "#b0b0b0", 5: "#88c788", 6: "#f0c14b", 7: "#ff69b4"
    }

    # 🎨 График
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor('#f7f7fa')
    ax.set_facecolor('#ffffff')

    for i in range(len(moods)):
        ax.plot(dates[i], moods[i], marker='o', markersize=10, color=colors.get(moods[i], 'gray'))
        ax.text(dates[i], moods[i]+0.15, mood_labels[moods[i]], ha='center', fontsize=14)

    ax.set_ylim(0.5, 7.5)
    ax.set_yticks(range(1, 8))
    ax.set_yticklabels([mood_labels[i] for i in range(1, 8)], fontsize=13)
    ax.set_title("📈 Все отмеченные настроения", fontsize=16, color='purple', pad=15)
    ax.set_xlabel("Дата", fontsize=12)
    ax.set_ylabel("Настроение", fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.4)

    plt.xticks(rotation=45)
    plt.tight_layout()

    # 📊 Подпись среднего настроения
    avg = sum(moods) / len(moods)
    avg_mood = round(avg, 2)
    mood_emoji = mood_labels[round(avg)] if round(avg) in mood_labels else "❓"
    ax.text(0.5, -0.2, f"Среднее настроение: {avg_mood} {mood_emoji}", fontsize=12,
            color='gray', ha='center', transform=ax.transAxes)

    # 📤 Отправка
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    await update.message.reply_photo(photo=InputFile(buf, filename="mood.png"))
    plt.close()

# 📊 /mood_week
async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update, days=7)

# 📊 /mood_month
async def mood_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update, days=30)

# 📊 /mood_all
async def mood_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update)

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
    app.add_handler(CommandHandler("mood_month", mood_month))
    app.add_handler(CommandHandler("mood_all", mood_all))
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
