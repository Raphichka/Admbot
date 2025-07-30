import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from aiogram.client.default import DefaultBotProperties
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio

# Настройки
logging.basicConfig(level=logging.INFO)
TOKEN = "8301190456:AAHekIPMG8mNW2GIlWlU4u1OAUue3SAvV4E"  # Замените на реальный токен
LOG_CHAT_ID = None  # Можно указать ID чата для логов (-10012345678)
ADMINS = [1247582425]  # Добавьте сюда ID админов [123456789, 987654321]

# Инициализация бота
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Базы данных
user_warns = defaultdict(int)
user_mutes = defaultdict(int)
user_msg_count = defaultdict(int)
banned_users = set()

# Фильтры
BANNED_WORDS = ["мат1", "мат2", "спам", "оскорбление"]
SPAM_LIMIT = 8  # Макс. сообщений в минуту

# --- Система анти-флуда ---
async def reset_message_counters():
    """Очищает счётчик сообщений каждую минуту"""
    while True:
        await asyncio.sleep(60)
        user_msg_count.clear()
        logging.info("Счётчики сообщений сброшены")

def count_user_messages(user_id: int) -> int:
    """Увеличивает счётчик сообщений и возвращает текущее значение"""
    user_msg_count[user_id] += 1
    return user_msg_count[user_id]

# --- Вспомогательные функции ---
async def log_action(text: str):
    """Отправляет сообщение в лог-чат"""
    if LOG_CHAT_ID:
        await bot.send_message(LOG_CHAT_ID, text)

async def add_warn(user: types.User, chat_id: int, reason: str):
    """Добавляет предупреждение и применяет наказания"""
    user_warns[user.id] += 1
    warns = user_warns[user.id]

    # Логирование
    log_msg = f"⚠️ {user.mention_html()} | {reason}\nПредупреждение {warns}/3"
    await log_action(log_msg)

    # Уведомление в чат
    await bot.send_message(
        chat_id=chat_id,
        text=f"{user.mention_html()}, нарушение: {reason} ({warns}/3)"
    )

    # Мут на 3 часа при 3 варнах
    if warns >= 3:
        until_date = datetime.now() + timedelta(hours=3)
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        user_warns[user.id] = 0
        user_mutes[user.id] += 1
        await log_action(f"🚫 {user.mention_html()} | Мут 3 ч. Нарушение: {reason}")

        # Бан при 3 мутах
        if user_mutes[user.id] >= 3:
            await bot.ban_chat_member(chat_id, user.id)
            banned_users.add(user.id)
            await log_action(f"⛔ {user.mention_html()} | БАН. 3+ мутов")

# --- Команды для админов ---
@dp.message(Command("unmute"))
async def unmute_user(message: Message):
    if message.from_user.id not in ADMINS:
        return await message.reply("❌ Только для админов!")

    if not message.reply_to_message:
        return await message.reply("ℹ️ Ответьте на сообщение пользователя")

    user = message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=True)
        )
        await message.reply(f"✅ {user.mention_html()} размучен")
        await log_action(f"🔈 Админ {message.from_user.mention_html()} размутил {user.mention_html()}")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

@dp.message(Command("unban"))
async def unban_user(message: Message):
    if message.from_user.id not in ADMINS:
        return await message.reply("❌ Только для админов!")

    if not message.reply_to_message:
        return await message.reply("ℹ️ Ответьте на сообщение пользователя")

    user = message.reply_to_message.from_user
    try:
        await bot.unban_chat_member(
            chat_id=message.chat.id,
            user_id=user.id
        )
        banned_users.discard(user.id)
        await message.reply(f"✅ {user.mention_html()} разбанен")
        await log_action(f"🔓 Админ {message.from_user.mention_html()} разбанил {user.mention_html()}")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

# --- Автомодерация ---
@dp.message()
async def auto_moderate(message: Message):
    if not message.from_user or message.from_user.id in ADMINS:
        return

    user = message.from_user
    chat_id = message.chat.id

    # 1. Проверка на запрещённые слова
    if message.text and any(word in message.text.lower() for word in BANNED_WORDS):
        await message.delete()
        await add_warn(user, chat_id, "Запрещённое слово")

    # 2. Анти-спам (флуд)
    elif count_user_messages(user.id) > SPAM_LIMIT:
        await add_warn(user, chat_id, "Флуд")

    # 3. Капс (>60% символов)
    elif (message.text
          and len(message.text) >= 10
          and sum(1 for c in message.text if c.isupper()) / len(message.text) > 0.6):
        await add_warn(user, chat_id, "Капс")

# Запуск бота
async def main():
    # Запускаем фоновую задачу для сброса счётчиков
    asyncio.create_task(reset_message_counters())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())