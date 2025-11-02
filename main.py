import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
import requests
from io import BytesIO

# Matplotlib без GUI
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== Переменные окружения ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEATHER_TOKEN = os.environ.get("WEATHER_API_KEY")
URL = os.environ.get("APP_URL1")  # пример: https://your-repl-name.username.repl.co  (без слеша на конце)

if not BOT_TOKEN or not URL:
    print("❗️Убедись, что в Secrets заданы BOT_TOKEN и APP_URL1")

# ================== База данных ==================
conn = sqlite3.connect("mood.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS moods (
        user_id INTEGER,
        mood INTEGER,
        date TEXT
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS cities (
        user_id INTEGER PRIMARY KEY,
        city TEXT
    )
""")
conn.commit()

# ================== Клавиатура настроений ==================
mood_keyboard = ReplyKeyboardMarkup(
    [
        ["1 💀 Хочу исчезнуть", "2 🌧️ Всё валится из рук", "3 😕 День какой-то не такой"],
        ["4 😐 Просто день", "5 🌿 Внутренний дзен", "6 🌞 На подъёме!", "7 🚀 Я лечу от счастья!"],
    ],
    resize_keyboard=True
)

# ================== Погода ==================
def get_weather(city: str) -> str:
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_TOKEN}&units=metric&lang=ru"
    try:
        response = requests.get(url, timeout=10)
    except Exception:
        return "Не удалось получить погоду 😢"
    if response.status_code != 200:
        return "Не удалось получить погоду 😢"

    data = response.json()
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    description = data['weather'][0]['description'].capitalize()
    main = data['weather'][0]['main'].lower()
    emoji = "☀️" if ("clear" in main or "sun" in main) else "🌥️"
    return f"{emoji} В {city} сейчас {temp}°C, ощущается как {feels_like}°C. {description}."

# ================== Команды ==================
async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши так: /setcity [город], например: /setcity Алматы")
        return
    city = " ".join(context.args)
    user_id = update.effective_user.id
    cursor.execute("INSERT OR REPLACE INTO cities (user_id, city) VALUES (?, ?)", (user_id, city))
    conn.commit()
    await update.message.reply_text(f"Твой город сохранён: {city} ✅")

async def my_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT city FROM cities WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        await update.message.reply_text(f"Твой город: {row[0]} 🏙️")
    else:
        await update.message.reply_text("Ты ещё не указал город. Используй /setcity [город]")

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT city FROM cities WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        await update.message.reply_text("Сначала укажи свой город с помощью /setcity 🌍")
        return
    city = row[0]
    await update.message.reply_text(get_weather(city))

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 😊 Я помогу тебе отслеживать настроение и погоду.\n\n"
        "Нажми /mood чтобы отметить, как ты себя чувствуешь 💬"
    )

# ============== Напоминание ==============
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

# ============== /mood и обработка кнопок ==============
async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_mood"] = True
    user_id = update.effective_user.id
    pending_mood_users[user_id] = True
    await update.message.reply_text("Как ты себя чувствуешь сегодня?", reply_markup=mood_keyboard)
    asyncio.create_task(remind_if_no_mood(user_id, context))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (update.message.text or "").strip()
    user_id = update.effective_user.id

    if not context.user_data.get("waiting_for_mood"):
        return

    if message and message[0].isdigit():
        mood_value = int(message[0])
        if 1 <= mood_value <= 7:
            cursor.execute(
                "INSERT INTO moods (user_id, mood, date) VALUES (?, ?, ?)",
                (user_id, mood_value, datetime.now().strftime("%Y-%m-%d"))
            )
            conn.commit()
            context.user_data["waiting_for_mood"] = False
            pending_mood_users.pop(user_id, None)

            responses = {
                1: "😩 Держись! Попробуй /breathe или /advice.",
                2: "😣 Это пройдёт. Попробуй /motivate или /breathe!",
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

# ============== Графики ==============
async def send_mood_graph(update: Update, days: int | None = None):
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

    mood_by_date = {}
    for date_str, mood_val in rows:
        mood_by_date.setdefault(date_str, []).append(mood_val)

    dates = sorted(mood_by_date.keys())
    moods = [sum(mood_by_date[d]) / len(mood_by_date[d]) for d in dates]

    plt.style.use('ggplot')
    plt.figure(figsize=(12, 6))
    plt.plot(dates, moods, marker='o', color='#2F4F4F')

    average_mood = sum(moods) / len(moods)
    plt.axhline(average_mood, color='gray', linestyle='--')
    plt.text(dates[-1], average_mood + 0.2, f"Среднее: {average_mood:.2f}", fontsize=10)

    plt.title("📊 Твой график настроения")
    plt.xlabel("Дата")
    plt.ylabel("Уровень (1–7)")
    plt.ylim(0.5, 7.8)
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await update.message.reply_photo(photo=InputFile(buf, filename="mood_chart.png"))

async def mood_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update, days=7)

async def mood_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update, days=30)

async def mood_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_mood_graph(update)

# ============== Flask + Telegram Application ==============
app = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(CommandHandler("mood", mood))
telegram_app.add_handler(CommandHandler("mood_week", mood_week))
telegram_app.add_handler(CommandHandler("mood_month", mood_month))
telegram_app.add_handler(CommandHandler("mood_all", mood_all))
telegram_app.add_handler(CommandHandler("setcity", set_city))
telegram_app.add_handler(CommandHandler("mycity", my_city))
telegram_app.add_handler(CommandHandler("weather", weather))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    print("== Пришёл апдейт:", data)
    update = Update.de_json(data, telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "ok", 200

@app.route("/")
def home():
    return "Бот работает через вебхуки ✅"

# ============== Запуск ==============
if __name__ == "__main__":
    async def _startup():
        await telegram_app.initialize()
        await telegram_app.start()
        resp = await telegram_app.bot.set_webhook(f"{URL.rstrip('/')}/{BOT_TOKEN}")
        print("== setWebhook ответ:", resp)
        info = await telegram_app.bot.get_webhook_info()
        print("== getWebhookInfo:", info.to_dict())

    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_startup())

    app.run(host="0.0.0.0", port=8080)
