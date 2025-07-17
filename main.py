import logging
import sqlite3
import datetime
import matplotlib.pyplot as plt
import io
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

import os
TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = "ТВОЙ_API_КЛЮЧ_ПОГОДЫ"

# Настроения
mood_labels = {
    1: "😣 Ужасно",
    2: "😔 Плохо",
    3: "😕 Так себе",
    4: "😐 Нормально",
    5: "🙂 Хорошо",
    6: "😄 Отлично",
    7: "🤩 Вау!"
}

# Логирование
logging.basicConfig(level=logging.INFO)

# БД
conn = sqlite3.connect("mood_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS moods (
    user_id INTEGER,
    mood INTEGER,
    date TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    city TEXT
)
""")
conn.commit()


# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я помогу отслеживать твоё настроение. Используй /mood чтобы выбрать.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
Доступные команды:
/mood — Отметить настроение
/mood_week — Настроение за неделю 📅
/mood_month — Настроение за месяц 📈
/mood_all — Вся история настроения 📊
/setcity — Установить свой город 🏙
/mycity — Посмотреть текущий город 🗺
""")


async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(label, callback_data=str(i))]
        for i, label in mood_labels.items()
    ]
    await update.message.reply_text("Как ты себя чувствуешь?", reply_markup=InlineKeyboardMarkup(keyboard))


async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mood = int(query.data)
    user_id = query.from_user.id
    date = datetime.date.today().isoformat()

    cursor.execute("INSERT INTO moods (user_id, mood, date) VALUES (?, ?, ?)", (user_id, mood, date))
    conn.commit()

    text = f"Записал твоё настроение: {mood_labels[mood]}"

    # Подсказки
    if mood <= 3:
        text += "\nПопробуй /breathe, /motivate или /task"
    elif mood == 4:
        text += "\nМожет, анекдот? Попробуй /joke"
    elif mood >= 5:
        text += "\nОтлично! Продолжай в том же духе 💪"

    await query.edit_message_text(text)


# График
def generate_mood_graph(user_id, days=None):
    if days:
        since_date = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        cursor.execute("SELECT date, mood FROM moods WHERE user_id=? AND date>=?", (user_id, since_date))
    else:
        cursor.execute("SELECT date, mood FROM moods WHERE user_id=?", (user_id,))
    
    data = cursor.fetchall()
    if not data:
        return None

    dates, moods = zip(*data)
    dates = [datetime.datetime.strptime(d, "%Y-%m-%d") for d in dates]

    plt.figure(figsize=(7, 4))
    plt.plot(dates, moods, marker='o', linestyle='-', color='purple')
    plt.title("Настроение")
    plt.xlabel("Дата")
    plt.ylabel("Уровень")
    plt.yticks(range(1, 8), [mood_labels[i] for i in range(1, 8)])
    plt.grid(True)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf


async def send_graph(update: Update, context: ContextTypes.DEFAULT_TYPE, days, label):
    user_id = update.effective_user.id
    buf = generate_mood_graph(user_id, days)
    if not buf:
        await update.message.reply_text("Нет данных для отображения.")
        return
    await update.message.reply_photo(photo=InputFile(buf), caption=f"📊 Настроение за {label}")


async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_graph(update, context, 7, "неделю")


async def mood_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_graph(update, context, 31, "месяц")


async def mood_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_graph(update, context, None, "всё время")


# Город
async def setcity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши свой город вот так:\n/setcity Алматы")
        return
    city = " ".join(context.args)
    user_id = update.effective_user.id
    cursor.execute("REPLACE INTO users (user_id, city) VALUES (?, ?)", (user_id, city))
    conn.commit()
    await update.message.reply_text(f"Город сохранён: {city}")


async def mycity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT city FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row:
        await update.message.reply_text(f"Твой город: {row[0]}")
    else:
        await update.message.reply_text("Ты ещё не указал город. Напиши: /setcity <город>")


# Погода + напоминание
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    cursor.execute("SELECT user_id, city FROM users")
    for user_id, city in cursor.fetchall():
        try:
            # Погода
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&units=metric&lang=ru&appid={WEATHER_API_KEY}"
            res = requests.get(url).json()
            temp = res["main"]["temp"]
            desc = res["weather"][0]["description"]
            message = f"🕓 Пора отметить своё настроение! /mood\n\n🌤 Погода в {city}: {temp}°C, {desc}"
        except:
            message = "🕓 Пора отметить своё настроение! /mood"
        await bot.send_message(chat_id=user_id, text=message)


# Запуск
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mood", mood))
    app.add_handler(CallbackQueryHandler(mood_callback))
    app.add_handler(CommandHandler("mood_week", mood_week))
    app.add_handler(CommandHandler("mood_month", mood_month))
    app.add_handler(CommandHandler("mood_all", mood_all))
    app.add_handler(CommandHandler("setcity", setcity))
    app.add_handler(CommandHandler("mycity", mycity))

    # Напоминание ежедневно
    app.job_queue.run_daily(daily_reminder, time=datetime.time(hour=13, minute=0))

    app.run_polling()
