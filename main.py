import logging
import sqlite3
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from datetime import datetime
import matplotlib.pyplot as plt
import os

# 🔐 Секреты
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

# 📦 Логгирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 📂 Подключение к базе
conn = sqlite3.connect("mood_data.db")
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS moods (
    user_id INTEGER,
    mood INTEGER,
    timestamp TEXT
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    city TEXT
)
''')

conn.commit()

# 🌈 Описание настроений
mood_scale = {
    1: "😞 Очень плохо",
    2: "😟 Плохо",
    3: "😐 Так себе",
    4: "🙂 Нормально",
    5: "😊 Хорошо",
    6: "😄 Отлично",
    7: "🤩 Супер!"
}

# 🖼️ Кнопки для выбора настроения
keyboard = ReplyKeyboardMarkup(
    [[f"{i}. {mood_scale[i]}"] for i in range(1, 8)],
    one_time_keyboard=True,
    resize_keyboard=True
)

# 🚀 Команды

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для отслеживания настроения 🌈\n"
        "Используй /mood чтобы выбрать настроение на сегодня."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 Доступные команды:\n"
        "/mood — отметить настроение\n"
        "/mood_week — график за неделю\n"
        "/mood_month — график за месяц\n"
        "/mood_all — график за всё время\n"
        "/setcity — указать свой город 🌍\n"
        "/mycity — показать текущий город\n"
        "/weather — погода в твоём городе ☀️"
    )

async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Как ты себя сегодня чувствуешь?", reply_markup=keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    try:
        for i in range(1, 8):
            if text.strip().startswith(str(i)):
                mood_value = i
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("INSERT INTO moods (user_id, mood, timestamp) VALUES (?, ?, ?)", (user_id, mood_value, now))
                conn.commit()

                # 🎯 Подсказки
                tip = ""
                if mood_value <= 2:
                    tip = "💡 Попробуй команду /breathe для дыхательных техник или /motivate для мотивации!"
                elif mood_value <= 4:
                    tip = "😊 Хочешь улыбнуться? Введи /joke!"
                else:
                    tip = "🌟 Отлично, продолжай в том же духе!"

                await update.message.reply_text(f"Настроение сохранено: {mood_scale[mood_value]}\n{tip}")
                break
        else:
            await update.message.reply_text("Пожалуйста, выбери настроение кнопками ниже.")
    except:
        await update.message.reply_text("Пожалуйста, выбери настроение кнопками ниже.")

# 📊 Графики
def generate_chart(user_id, period):
    c.execute(f"SELECT timestamp, mood FROM moods WHERE user_id = ? ORDER BY timestamp", (user_id,))
    rows = c.fetchall()

    if period == "week":
        title = "Настроение за неделю"
        rows = rows[-7:]
    elif period == "month":
        title = "Настроение за месяц"
        rows = rows[-30:]
    else:
        title = "Настроение за всё время"

    if not rows:
        return None

    dates = [row[0][:10] for row in rows]
    moods = [row[1] for row in rows]

    plt.figure(figsize=(8, 4))
    plt.plot(dates, moods, marker='o', color='purple')
    plt.ylim(1, 7)
    plt.xticks(rotation=45)
    plt.title(title)
    plt.xlabel("Дата")
    plt.ylabel("Настроение")
    plt.grid(True)
    plt.tight_layout()
    filename = f"mood_chart_{user_id}.png"
    plt.savefig(filename)
    plt.close()
    return filename

async def mood_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str):
    user_id = update.message.from_user.id
    chart = generate_chart(user_id, period)
    if chart:
        await update.message.reply_photo(photo=open(chart, 'rb'))
        os.remove(chart)
    else:
        await update.message.reply_text("Нет данных для отображения графика.")

async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mood_chart(update, context, "week")

async def mood_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mood_chart(update, context, "month")

async def mood_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mood_chart(update, context, "all")

# 🌍 Погода

async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        city = " ".join(context.args)
        user_id = update.message.from_user.id
        c.execute("INSERT OR REPLACE INTO users (user_id, city) VALUES (?, ?)", (user_id, city))
        conn.commit()
        await update.message.reply_text(f"Город сохранён: {city}")
    else:
        await update.message.reply_text("Использование: /setcity [название города]")

async def my_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    c.execute("SELECT city FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        await update.message.reply_text(f"Твой текущий город: {row[0]}")
    else:
        await update.message.reply_text("Ты ещё не установил город. Введи команду /setcity [город]")

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
        weather_text = weather_description.capitalize()

        mood_comment = ""
        if "rain" in weather_description.lower():
            mood_comment = "🌧️ Дождливо... Может казаться тоскливо, но плед и тёплый чай спасают атмосферу ☕"
        elif "cloud" in weather_description.lower():
            mood_comment = "☁️ Сегодня облачно — иногда и на душе может быть также. Подари себе немного тепла 💙"
        elif "clear" in weather_description.lower() or "sun" in weather_description.lower():
            mood_comment = "🌞 Ясно и солнечно! Отличный день для прогулки или любимого дела ✨"
        elif "snow" in weather_description.lower():
            mood_comment = "❄️ Снег за окном — как повод замедлиться и укутаться в уют 💭"

        temp = response["main"]["temp"]
        feels = response["main"]["feels_like"]
        humidity = response["main"]["humidity"]
        wind = response["wind"]["speed"]

        emoji = "🌤"
        if "дожд" in weather_text.lower(): emoji = "🌧"
        elif "ясно" in weather_text.lower(): emoji = "☀️"
        elif "облачно" in weather_text.lower(): emoji = "☁️"
        elif "снег" in weather_text.lower(): emoji = "❄️"

        await update.message.reply_text(
            f"{emoji} Погода в {city}:\n"
            f"📍 {weather_text}\n"
            f"🌡 Температура: {temp}°C (Ощущается как {feels}°C)\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind} м/с\n\n"
            f"{mood_comment}"
        )
    except:
        await update.message.reply_text("Не удалось получить данные о погоде. Проверь название города.")

# 🔁 Запуск
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

app.run_polling()
