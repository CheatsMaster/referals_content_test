import asyncio
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiosqlite

import database as db
from subscription_checker import SubscriptionChecker

from config import ADMIN_IDS

import os

router = Router()
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)


class AdminStates(StatesGroup):
    waiting_user_id = State()
    waiting_credits = State()
    waiting_publisher_id = State()


@router.message(Command("admin"))
async def admin_panel(message: Message):
    """Панель администратора"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав администратора")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 Добавить кредиты", callback_data="admin_add_credits")],
        [InlineKeyboardButton(text="👤 Назначить разместителя", callback_data="admin_make_publisher")],
        [InlineKeyboardButton(text="📝 Управление постами", callback_data="admin_manage_posts")],
        [InlineKeyboardButton(text="🔍 Проверять каналы", callback_data="admin_check_channels")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list_users")],
    ])
    
    await message.answer(
        "👑 Панель администратора\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Статистика бота"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    stats = await db.get_stats()
    
    # Получаем дополнительную статистику
    async with aiosqlite.connect("bot_database.db") as db_conn:
        async with db_conn.execute("SELECT COUNT() FROM users WHERE role = 'publisher'") as cursor:
            publishers = (await cursor.fetchone())[0]
        
        async with db_conn.execute("SELECT COUNT() FROM payments WHERE status = 'completed'") as cursor:
            payments = (await cursor.fetchone())[0]
        
        async with db_conn.execute("SELECT SUM(amount) FROM payments WHERE status = 'completed'") as cursor:
            total_income = (await cursor.fetchone())[0] or 0
    
    await callback.message.answer(
        f"📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📝 Всего постов: {stats['total_posts']}\n"
        f"👀 Всего просмотров: {stats['total_views']}\n\n"
        f"📢 Разместителей: {publishers}\n"
        f"💰 Оплаченных подписок: {payments}\n"
        f"💵 Общий доход: {total_income} руб\n\n"
        f"📅 Обновлено: {stats.get('timestamp', 'только что')}"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_credits")
async def admin_add_credits_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления кредитов"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    await callback.message.answer(
        "💰 Добавление кредитов\n\n"
        "Введите ID пользователя:"
    )
    await state.set_state(AdminStates.waiting_user_id)
    await callback.answer()


@router.message(AdminStates.waiting_user_id)
async def admin_add_credits_get_user(message: Message, state: FSMContext):
    """Получение ID пользователя для добавления кредитов"""
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        user_id = int(message.text)
        
        # Проверяем существует ли пользователь
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден")
            await state.clear()
            return
        
        await state.update_data(user_id=user_id)
        
        await message.answer(
            f"✅ Пользователь найден:\n\n"
            f"👤 Имя: {user['full_name']}\n"
            f"📱 Username: @{user['username']}\n"
            f"💰 Текущие кредиты: {user['credits']}\n\n"
            f"Введите количество кредитов для добавления:"
        )
        await state.set_state(AdminStates.waiting_credits)
    except ValueError:
        await message.answer("❌ Неверный ID. Введите число")


@router.message(AdminStates.waiting_credits)
async def admin_add_credits_finish(message: Message, state: FSMContext):
    """Завершение добавления кредитов"""
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        credits = int(message.text)
        data = await state.get_data()
        user_id = data["user_id"]
        
        if credits <= 0:
            await message.answer("❌ Количество кредитов должно быть больше 0")
            return
        
        await db.add_credits(user_id, credits)
        
        # Получаем обновленные данные пользователя
        user = await db.get_user(user_id)
        
        await message.answer(
            f"✅ Успешно!\n\n"
            f"👤 Пользователь: {user['full_name']}\n"
            f"🆔 ID: {user_id}\n"
            f"💰 Добавлено: {credits} кредитов\n"
            f"💎 Новый баланс: {user['credits']}"
        )
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверное количество. Введите число")


@router.callback_query(F.data == "admin_make_publisher")
async def admin_make_publisher_start(callback: CallbackQuery, state: FSMContext):
    """Начало назначения разместителя"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    await callback.message.answer(
        "👤 Назначение разместителя\n\n"
        "Введите ID пользователя для назначения:"
    )
    await state.set_state(AdminStates.waiting_publisher_id)
    await callback.answer()


@router.message(AdminStates.waiting_publisher_id)
async def admin_make_publisher_finish(message: Message, state: FSMContext):
    """Завершение назначения разместителя"""
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        user_id = int(message.text)
        
        # Проверяем существует ли пользователь
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден")
            await state.clear()
            return
        
        # Меняем роль на разместителя
        await db.update_user_role(user_id, "publisher")
        
        # Даем начальные кредиты (опционально)
        initial_credits = 10
        await db.add_credits(user_id, initial_credits)
        
        await message.answer(
            f"✅ Успешно!\n\n"
            f"👤 Пользователь: {user['full_name']}\n"
            f"🆔 ID: {user_id}\n"
            f"🎭 Новая роль: Разместитель\n"
            f"💎 Начислено кредитов: {initial_credits}\n\n"
            f"Теперь он может:\n"
            f"• Создавать посты командой /create_post\n"
            f"• Получать уникальные ссылки\n"
            f"• Использовать кредиты для постов"
        )
        
        # Отправляем уведомление пользователю
        try:
            await message.bot.send_message(
                user_id,
                f"🎉 Поздравляем!\n\n"
                f"Вам были выданы права 📝 Разместителя.\n"
                f"💎 Начислено: {initial_credits} кредитов\n\n"
                f"Теперь вы можете:\n"
                f"• Создавать посты командой /create_post\n"
                f"• Получать уникальные ссылки на контент\n"
                f"• Привлекать подписчиков в ваши каналы\n\n"
                f"💡 Начните с команды /create_post"
            )
        except:
            pass  # Не критично если не отправится
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверный ID. Введите число")


@router.callback_query(F.data == "admin_manage_posts")
async def admin_manage_posts(callback: CallbackQuery):
    """Управление постами"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список всех постов", callback_data="admin_all_posts")],
        [InlineKeyboardButton(text="🚫 Заблокированные посты", callback_data="admin_blocked_posts")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
    ])
    
    await callback.message.edit_text(
        "📝 Управление постами\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "admin_all_posts")
async def admin_all_posts(callback: CallbackQuery):
    """Список всех постов"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    # Получаем все посты
    async with aiosqlite.connect("bot_database.db") as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute(
            """SELECT p., u.username, u.user_id as publisher_user_id 
               FROM posts p 
               LEFT JOIN users u ON p.publisher_id = u.user_id 
               ORDER BY p.created_at DESC LIMIT 20"""
        ) as cursor:
            posts = await cursor.fetchall()
    
    if not posts:
        await callback.message.answer("📭 Постов пока нет")
        await callback.answer()
        return
    
    for post in posts:
        status = "🟢 Активен" if post['is_active'] else "🔴 Заблокирован"
        channels = json.loads(post['channels']) if post['channels'] else []
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Блокировать" if post['is_active'] else "✅ Разблокировать",
                    callback_data=f"toggle_post_{post['id']}"
                )
            ],
            [
                InlineKeyboardButton(text="👤 Автор", callback_data=f"view_user_{post['publisher_user_id']}"),
                InlineKeyboardButton(text="📊 Статистика", callback_data=f"post_stats_{post['id']}")
            ]
        ])
        
        message_text = (
            f"📝 Пост #{post['id']}\n\n"
            f"👤 Автор: @{post['username'] or 'неизвестен'}\n"
            f"🔗 Код: {post['unique_code']}\n"
            f"👀 Просмотров: {post['views']}\n"
            f"📊 Статус: {status}\n"
            f"📅 Дата: {post['created_at']}\n"
            f"📢 Каналов: {len(channels)}\n"
        )
        
        if channels:
            message_text += f"📋 Список: {', '.join(channels[:3])}"
            if len(channels) > 3:
                message_text += f" ... (+{len(channels)-3})"
        
        await callback.message.answer(message_text, reply_markup=keyboard)
    
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_post_"))
async def toggle_post_status(callback: CallbackQuery):
    """Блокировка/разблокировка поста"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    post_id = int(callback.data.split("_")[2])
    
    new_status = await db.toggle_post_status(post_id)
    status_text = "заблокирован" if not new_status else "разблокирован"
    
    await callback.answer(f"✅ Пост {status_text}")
    
    # Обновляем сообщение
    await admin_all_posts(callback)


@router.callback_query(F.data == "admin_check_channels")
async def admin_check_channels(callback: CallbackQuery):
    """Проверка всех каналов"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    # Получаем все уникальные каналы из всех постов
    async with aiosqlite.connect("bot_database.db") as db_conn:
        async with db_conn.execute("SELECT channels FROM posts WHERE channels IS NOT NULL AND channels != ''") as cursor:
            posts = await cursor.fetchall()
    
    all_channels = set()
    for post in posts:
        if post[0]:
            try:
                channels = json.loads(post[0])
                all_channels.update(channels)
            except:
                pass
    
    if not all_channels:
        await callback.message.answer("📭 В постах нет каналов для проверки")
        await callback.answer()
        return
    
    checker = SubscriptionChecker(callback.message.bot)
    
    await callback.message.answer(f"🔍 Проверяем {len(all_channels)} каналов...")
    
    valid_channels = []
    invalid_channels = []
    
    # Проверяем каналы по очереди
    for idx, channel in enumerate(all_channels):
        is_valid, error_msg = await checker.check_bot_admin_rights(channel)
        
        if is_valid:
            valid_channels.append(channel)
        else:
            invalid_channels.append((channel, error_msg))
        
        # Отправляем промежуточный отчет каждые 5 каналов
        if (idx + 1) % 5 == 0:
            await callback.message.answer(f"🔍 Проверено {idx + 1}/{len(all_channels)} каналов...")
    
    # Формируем финальный отчет
    report = f"📊 Отчет по проверке каналов\n\n"
    report += f"✅ Рабочих каналов: {len(valid_channels)}\n"
    report += f"❌ Проблемных каналов: {len(invalid_channels)}\n\n"
    
    if valid_channels:
        report += "✅ Рабочие каналы:\n"
        for channel in valid_channels[:10]:
            report += f"• {channel}\n"
        if len(valid_channels) > 10:
            report += f"... и еще {len(valid_channels) - 10}\n"
        report += "\n"
    
    if invalid_channels:
        report += "❌ Проблемные каналы:\n"
        for channel, error in invalid_channels[:10]:
            # Укорачиваем длинные ошибки
            if len(error) > 50:
                error = error[:50] + "..."
            report += f"• {channel} - {error}\n"
        if len(invalid_channels) > 10:
            report += f"... и еще {len(invalid_channels) - 10}\n"
    
    await callback.message.answer(report)
    await callback.answer()


@router.callback_query(F.data == "admin_list_users")
async def admin_list_users(callback: CallbackQuery):
    """Список пользователей"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    # Получаем всех пользователей
    async with aiosqlite.connect("bot_database.db") as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute(
            """SELECT  FROM users ORDER BY created_at DESC LIMIT 50"""
        ) as cursor:
            users = await cursor.fetchall()
    
    if not users:
        await callback.message.answer("📭 Пользователей пока нет")
        await callback.answer()
        return
    
    # Группируем по ролям
    admins = [u for u in users if u['role'] == 'admin']
    publishers = [u for u in users if u['role'] == 'publisher']
    regular_users = [u for u in users if u['role'] == 'user']
    
    response = f"👥 Всего пользователей: {len(users)}\n\n"
    
    if admins:
        response += "👑 Администраторы:\n"
        for admin in admins[:5]:
            response += f"• @{admin['username'] or 'без username'} (ID: {admin['user_id']}) - {admin['credits']} кредитов\n"
        if len(admins) > 5:
            response += f"... и еще {len(admins) - 5}\n"
        response += "\n"
    
    if publishers:
        response += "📝 Разместители:\n"
        for publisher in publishers[:10]:
            response += f"• @{publisher['username'] or 'без username'} (ID: {publisher['user_id']}) - {publisher['credits']} кредитов\n"
        if len(publishers) > 10:
            response += f"... и еще {len(publishers) - 10}\n"
        response += "\n"
    
    response += f"👤 Обычных пользователей: {len(regular_users)}"
    
    await callback.message.answer(response)
    await callback.answer()


@router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    """Возврат в админ панель"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    
    await admin_panel(callback.message)
    await callback.answer()


# Команды для быстрого управления


@router.message(Command("make_publisher"))
async def make_publisher_command(message: Message):
    """Быстрая команда для назначения разместителя"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("Использование: /make_publisher ID_пользователя")
        return
    
    try:
        user_id = int(args[1])
        user = await db.get_user(user_id)
        
        if not user:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден")
            return
        
        await db.update_user_role(user_id, "publisher")
        
        await message.answer(
            f"✅ Пользователь @{user['username']} (ID: {user_id})\n"
            f"теперь назначен 📝 Разместителем!"
        )
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")


@router.message(Command("add_credits"))
async def add_credits_command(message: Message):
    """Быстрая команда для добавления кредитов"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split()
    
    if len(args) < 3:
        await message.answer("Использование: /add_credits ID_пользователя КОЛИЧЕСТВО")
        return
    
    try:
        user_id = int(args[1])
        credits = int(args[2])
        
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден")
            return
        
        await db.add_credits(user_id, credits)
        
        # Получаем обновленные данные
        updated_user = await db.get_user(user_id)
        
        await message.answer(
            f"✅ Успешно добавлено {credits} кредитов\n\n"
            f"👤 Пользователю: @{user['username']}\n"
            f"💎 Новый баланс: {updated_user['credits']}"
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /add_credits ID КОЛИЧЕСТВО")


@router.message(Command("block_post"))
async def block_post_command(message: Message):
    """Быстрая команда для блокировки поста"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("Использование: /block_post ID_поста")
        return
    
    try:
        post_id = int(args[1])
        
        # Получаем текущий статус
        async with aiosqlite.connect("bot_database.db") as db_conn:
            async with db_conn.execute("SELECT is_active FROM posts WHERE id = ?", (post_id,)) as cursor:
                result = await cursor.fetchone()
                
                if not result:
                    await message.answer(f"❌ Пост с ID {post_id} не найден")
                    return
                
                current_status = result[0]
                new_status = not current_status
                
                await db_conn.execute(
                    "UPDATE posts SET is_active = ? WHERE id = ?",
                    (new_status, post_id)
                )
                await db_conn.commit()
        
        action = "разблокирован" if new_status else "заблокирован"
        await message.answer(f"✅ Пост #{post_id} {action}")
    except ValueError:
        await message.answer("❌ Неверный ID поста")


@router.message(Command("find_user"))
async def find_user_command(message: Message):
    """Поиск пользователя по ID или username"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("Использование: /find_user ID_или_username")
        return
    
    search_term = args[1]
    
    async with aiosqlite.connect("bot_database.db") as db_conn:
        db_conn.row_factory = aiosqlite.Row
        
        # Пробуем поиск по ID
        try:
            user_id = int(search_term)
            async with db_conn.execute("SELECT  FROM users WHERE user_id = ?", (user_id,)) as cursor:
                user = await cursor.fetchone()
        except ValueError:
            user = None
        
        # Если не нашли по ID, ищем по username
        if not user:
            async with db_conn.execute(
                "SELECT  FROM users WHERE username LIKE ?", 
                (f"%{search_term}%",)
            ) as cursor:
                user = await cursor.fetchone()
        
        if not user:
            await message.answer(f"❌ Пользователь '{search_term}' не найден")
            return
        
        role_text = {
            "user": "👤 Пользователь",
            "publisher": "📝 Разместитель", 
            "admin": "👑 Администратор"
        }
        
        # Получаем статистику пользователя
        async with db_conn.execute(
            "SELECT COUNT() FROM posts WHERE publisher_id = ?", 
            (user['user_id'],)
        ) as cursor:
            posts_count = (await cursor.fetchone())[0]
        
        async with db_conn.execute(
            "SELECT SUM(views) FROM posts WHERE publisher_id = ?", 
            (user['user_id'],)
        ) as cursor:
            total_views = (await cursor.fetchone())[0] or 0
        
        response = (
            f"🔍 Информация о пользователе:\n\n"
            f"🆔 ID: {user['user_id']}\n"
            f"👤 Имя: {user['full_name']}\n"
            f"📱 Username: @{user['username']}\n"
            f"🎭 Роль: {role_text.get(user['role'], '👤 Пользователь')}\n"
            f"💰 Кредиты: {user['credits']}\n"
            f"📝 Постов создано: {posts_count}\n"
            f"👀 Всего просмотров: {total_views}\n"
            f"📅 Регистрация: {user['created_at']}\n\n"
            f"💡 Команды управления:\n"
            f"/add_credits {user['user_id']} КОЛИЧЕСТВО\n"
            f"/make_publisher {user['user_id']}"
        )
        
        await message.answer(response)
