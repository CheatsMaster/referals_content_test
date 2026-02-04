import asyncio
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from subscription_checker import SubscriptionChecker

router = Router()
logger = logging.getLogger(__name__)


class CreatePostStates(StatesGroup):
    waiting_title = State()  # НОВОЕ: ждем название поста
    waiting_content = State()
    waiting_channels = State()


@router.message(Command("create_post"))
async def create_post_start(message: Message, state: FSMContext):
    """Начало создания поста"""
    user = await db.get_user(message.from_user.id)
    
    if not user or user['role'] not in ['publisher', 'admin']:
        await message.answer("❌ У вас нет прав разместителя. Обратитесь к администратору.")
        return
    
    await message.answer(
        "📝 Создание нового поста:\n\n"
        "1️⃣ Сначала задайте название поста\n"
        "2️⃣ Затем отправьте контент\n"
        "3️⃣ Укажите каналы для подписки\n"
        "4️⃣ Получите уникальную ссылку\n\n"
        "❌ Отправьте /cancel для отмены"
    )
    await state.set_state(CreatePostStates.waiting_title)


@router.message(CreatePostStates.waiting_title)
async def process_post_title(message: Message, state: FSMContext):
    """Обработка названия поста"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание поста отменено")
        return
    
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("❌ Название должно быть не менее 3 символов")
        return
    
    await state.update_data(post_title=title)
    
    await message.answer(
        f"✅ Название сохранено: {title}\n\n"
        "📝 Теперь отправьте контент:\n"
        "• Текст сообщения\n"
        "• Фото с подписью\n"
        "• Видео с подписью\n\n"
        "❌ Отправьте /cancel для отмены"
    )
    await state.set_state(CreatePostStates.waiting_content)
    await state.update_data(content={"type": None, "text": "", "file_id": None})


@router.message(CreatePostStates.waiting_content)
async def process_content(message: Message, state: FSMContext):
    """Обработка контента"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание поста отменено")
        return
    
    data = await state.get_data()
    content = data.get("content", {})
    
    if message.text:
        content["type"] = "text"
        content["text"] = message.text
    elif message.photo:
        content["type"] = "photo"
        content["file_id"] = message.photo[-1].file_id
        content["text"] = message.caption or ""
    elif message.video:
        content["type"] = "video"
        content["file_id"] = message.video.file_id
        content["text"] = message.caption or ""
    else:
        await message.answer("❌ Поддерживается только текст, фото или видео")
        return
    
    await state.update_data(content=content)
    
    await message.answer(
        "✅ Контент сохранен!\n\n"
        "📢 Теперь отправьте каналы для подписки (по одному в строке):\n"
        "• @channel1\n"
        "• @channel2\n\n"
        "❌ Отправьте /skip если каналы не нужны\n"
        "📤 Отправьте /done когда закончите\n\n"
        "💡 Важно: Бот должен быть администратором в этих каналах!"
    )
    await state.set_state(CreatePostStates.waiting_channels)
    await state.update_data(channels=[])


@router.message(CreatePostStates.waiting_channels, F.text == "/skip")
async def skip_channels(message: Message, state: FSMContext):
    """Пропуск добавления каналов"""
    await finish_post_creation(message, state)


@router.message(CreatePostStates.waiting_channels, F.text == "/done")
async def done_channels(message: Message, state: FSMContext):
    """Завершение добавления каналов"""
    await finish_post_creation(message, state)


@router.message(CreatePostStates.waiting_channels)
async def process_channels(message: Message, state: FSMContext):
    """Обработка добавления каналов"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание поста отменено")
        return
    
    if not message.text.startswith("@"):
        await message.answer("❌ Канал должен начинаться с @ (например: @channel_name)")
        return
    
    channel = message.text.strip()
    
    # ПРОВЕРЯЕМ КАНАЛ
    checker = SubscriptionChecker(message.bot)
    
    # 1. Проверяем права администратора
    is_admin, admin_error = await checker.check_bot_admin_rights(channel)
    
    if not is_admin:
        await message.answer(
            f"❌ Проблема с каналом {channel}:\n\n"
            f"{admin_error}\n\n"
            f"Что нужно сделать:\n"
            f"1. Добавьте бота как администратора в {channel}\n"
            f"2. Дайте права на постинг сообщений\n"
            f"3. Проверьте командой /check_channel {channel}"
        )
        return
    
    data = await state.get_data()
    channels = data.get("channels", [])
    
    if channel in channels:
        await message.answer(f"ℹ️ Канал {channel} уже добавлен")
    else:
        channels.append(channel)
        await state.update_data(channels=channels)
        await message.answer(
            f"✅ Канал добавлен: {channel}\n"
            f"📊 Всего каналов: {len(channels)}\n\n"
            "Добавьте еще канал или отправьте /done"
        )


async def finish_post_creation(message: Message, state: FSMContext):
    """Завершение создания поста"""
    data = await state.get_data()
    post_title = data.get("post_title", "Без названия")
    content = data.get("content", {})
    channels = data.get("channels", [])
    
    if not content.get("type"):
        await message.answer("❌ Контент не был добавлен")
        await state.clear()
        return
    
    # Проверяем баланс пользователя
    user = await db.get_user(message.from_user.id)
    if user['credits'] < len(channels):
        await message.answer(
            f"❌ Недостаточно кредитов!\n"
            f"💰 Нужно: {len(channels)} кредитов\n"
            f"💎 У вас: {user['credits']} кредитов\n\n"
            f"Купите кредиты командой /subscribe"
        )
        await state.clear()
        return
    
    # Создаем пост с названием
    unique_code = await db.create_post_with_title(
        publisher_id=message.from_user.id,
        post_title=post_title,
        content_type=content["type"],
        content_text=content["text"],
        content_file_id=content["file_id"],
        channels=channels
    )
    
    # Списываем кредиты
    await db.add_credits(message.from_user.id, -len(channels))
    
    # Формируем ссылку
    bot_username = (await message.bot.get_me()).username
    post_url = f"https://t.me/{bot_username}?start={unique_code}"
    short_url = f"t.me/{bot_username}?start={unique_code}"
    
    await message.answer(
        f"🎉 Пост успешно создан!\n\n"
        f"📝 Название: {post_title}\n"
        f"🔗 Ссылка на пост:\n"
        f"👉 {post_url}\n\n"
        f"📎 Короткая ссылка:\n"
        f"👉 {short_url}\n\n"
        f"📊 Детали:\n"
        f"• Каналов: {len(channels)}\n"
        f"• Списано кредитов: {len(channels)}\n"
        f"• Осталось кредитов: {user['credits'] - len(channels)}"
    )
    
    # Показываем информацию о каналах
    if channels:
        channels_list = "\n".join([f"• {channel}" for channel in channels])
        await message.answer(
            f"📢 Каналы для подписки:\n\n"
            f"{channels_list}\n\n"
            f"✅ Бот проверен на права администратора во всех каналах"
        )
    
    await state.clear()


# ДОБАВЛЯЕМ КОМАНДУ ДЛЯ ПОКАЗА ПОСТОВ ПОЛЬЗОВАТЕЛЯ
@router.message(Command("my_posts"))
async def my_posts_command(message: Message):
    """Показать посты пользователя"""
    user = await db.get_user(message.from_user.id)
    
    if not user or user['role'] not in ['publisher', 'admin']:
        await message.answer("❌ У вас нет прав разместителя")
        return
    
    posts = await db.get_user_posts(message.from_user.id)
    
    if not posts:
        await message.answer("📭 У вас пока нет созданных постов")
        return
    
    await message.answer(f"📝 Ваши посты ({len(posts)}):")
    
    for post in posts[:10]:  # Ограничиваем 10 постами
        channels = json.loads(post['channels']) if post['channels'] else []
        status = "🟢 Активен" if post['is_active'] else "🔴 Неактивен"
        
        # Получаем название поста (если есть)
        post_title = post.get('post_title', f"Пост #{post['id']}")
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Обновить", callback_data=f"update_post_{post['id']}"),
                InlineKeyboardButton(text="📊 Статистика", callback_data=f"post_stats_{post['id']}")
            ],
            [
                InlineKeyboardButton(text="🔄 Отправить обновление", callback_data=f"send_update_{post['id']}"),
                InlineKeyboardButton(text="🚫/✅", callback_data=f"toggle_post_{post['id']}")
            ],
            [
                InlineKeyboardButton(text="👥 Подписчики", callback_data=f"post_subscribers_{post['id']}")
            ]
        ])
        
        message_text = (
            f"📝 <b>{post_title}</b>\n"
            f"🆔 ID: {post['id']}\n"
            f"🔗 Код: {post['unique_code']}\n"
            f"👀 Просмотров: {post['views']}\n"
            f"📊 Статус: {status}\n"
            f"📢 Каналов: {len(channels)}\n"
            f"📅 Дата: {post['created_at'][:16]}"
        )
        
        await message.answer(message_text, reply_markup=keyboard, parse_mode="HTML")
    
    if len(posts) > 10:
        await message.answer(f"📋 Показано 10 из {len(posts)} постов")


# ОБРАБОТЧИКИ ДЛЯ РЕДАКТИРОВАНИЯ ПОСТОВ
@router.callback_query(F.data.startswith("update_post_"))
async def update_post_start(callback: CallbackQuery, state: FSMContext):
    """Начало обновления поста"""
    try:
        post_id = int(callback.data.split("_")[2])
        
        # Проверяем права
        post = await db.get_post_by_id(post_id)
        if not post:
            await callback.answer("❌ Пост не найден")
            return
        
        if post['publisher_id'] != callback.from_user.id:
            user = await db.get_user(callback.from_user.id)
            if user['role'] != 'admin':
                await callback.answer("❌ У вас нет прав на редактирование этого поста")
                return
        
        await callback.message.answer(
            f"✏️ Редактирование поста\n\n"
            f"📝 Текущий контент:\n"
            f"{post['content_text'][:200] if post['content_text'] else 'Фото/видео'}\n\n"
            f"Отправьте новый контент:\n"
            f"• Текст\n"
            f"• Фото с подписью\n"
            f"• Видео с подписью\n\n"
            f"❌ Отправьте /cancel для отмены"
        )
        
        await state.update_data(post_id=post_id, editing_post=True)
        
        # Сохраняем callback для дальнейшего использования
        await state.update_data(callback_message_id=callback.message.message_id)
        await state.update_data(callback_chat_id=callback.message.chat.id)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в update_post_start: {e}")
        await callback.answer("❌ Ошибка")


@router.callback_query(F.data.startswith("send_update_"))
async def send_update_to_subscribers(callback: CallbackQuery):
    """Отправить обновление подписчикам"""
    try:
        post_id = int(callback.data.split("_")[2])
        
        # Проверяем права
        post = await db.get_post_by_id(post_id)
        if not post:
            await callback.answer("❌ Пост не найден")
            return
        
        if post['publisher_id'] != callback.from_user.id:
            user = await db.get_user(callback.from_user.id)
            if user['role'] != 'admin':
                await callback.answer("❌ У вас нет прав")
                return
        
        await callback.message.answer("⏳ Готовлю обновление для подписчиков...")
        
        # Получаем подписчиков
        subscribers = await db.get_post_subscribers(post_id)
        
        if not subscribers:
            await callback.message.answer("📭 Нет подписчиков для этого поста")
            await callback.answer()
            return
        
        # Создаем новую редакцию из текущего контента
        revision_id = await db.create_post_revision(
            post_id=post_id,
            content_type=post['content_type'],
            content_text=post['content_text'],
            content_file_id=post['content_file_id'],
            channels=json.loads(post['channels']) if post['channels'] else []
        )
        
        success_count = 0
        fail_count = 0
        
        # Получаем название поста
        post_title = post.get('post_title', f"Пост #{post_id}")
        
        # Отправляем обновление каждому подписчику
        for subscriber in subscribers:
            try:
                # Формируем сообщение об обновлении
                bot_username = (await callback.bot.get_me()).username
                post_url = f"https://t.me/{bot_username}?start={post['unique_code']}"
                
                update_text = (
                    f"📢 <b>ОБНОВЛЕНИЕ ПОСТА!</b>\n\n"
                    f"📝 <b>{post_title}</b>\n\n"
                    f"Автор обновил контент:\n"
                    f"👉 {post_url}\n\n"
                    f"💡 Перейдите по ссылке чтобы увидеть обновление"
                )
                
                await callback.bot.send_message(
                    chat_id=subscriber['user_id'],
                    text=update_text,
                    parse_mode="HTML"
                )
                success_count += 1
                
                # Небольшая задержка чтобы не превысить лимиты Telegram
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Ошибка отправки подписчику {subscriber['user_id']}: {e}")
                fail_count += 1
        
        # Отмечаем редакцию как отправленную
        await db.mark_revision_as_sent(revision_id)
        
        await callback.message.answer(
            f"✅ Обновление отправлено!\n\n"
            f"📝 Пост: {post_title}\n"
            f"👥 Получили: {success_count} подписчиков\n"
            f"❌ Не получили: {fail_count} подписчиков\n"
            f"📅 Ревизия #{revision_id} создана"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в send_update_to_subscribers: {e}")
        await callback.message.answer("❌ Ошибка при отправке обновления")
        await callback.answer()


@router.callback_query(F.data.startswith("post_subscribers_"))
async def show_post_subscribers(callback: CallbackQuery):
    """Показать подписчиков поста"""
    try:
        post_id = int(callback.data.split("_")[2])
        
        # Проверяем права
        post = await db.get_post_by_id(post_id)
        if not post:
            await callback.answer("❌ Пост не найден")
            return
        
        if post['publisher_id'] != callback.from_user.id:
            user = await db.get_user(callback.from_user.id)
            if user['role'] != 'admin':
                await callback.answer("❌ У вас нет прав")
                return
        
        subscribers = await db.get_post_subscribers(post_id)
        
        if not subscribers:
            await callback.answer("📭 Нет подписчиков")
            await callback.message.answer("У этого поста пока нет подписчиков")
            return
        
        subscribers_list = "\n".join([
            f"{i+1}. @{sub['username'] or 'без username'} - {sub['full_name']}"
            for i, sub in enumerate(subscribers[:20])
        ])
        
        post_title = post.get('post_title', f"Пост #{post_id}")
        response = (
            f"👥 Подписчики поста: {post_title}\n"
            f"📊 Всего: {len(subscribers)}\n\n"
            f"{subscribers_list}"
        )
        
        if len(subscribers) > 20:
            response += f"\n\n... и еще {len(subscribers) - 20}"
        
        await callback.message.answer(response)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в show_post_subscribers: {e}")
        await callback.answer("❌ Ошибка")


@router.callback_query(F.data.startswith("toggle_post_"))
async def toggle_post_status_callback(callback: CallbackQuery):
    """Переключение статуса поста"""
    try:
        post_id = int(callback.data.split("_")[2])
        
        # Проверяем права
        post = await db.get_post_by_id(post_id)
        if not post:
            await callback.answer("❌ Пост не найден")
            return
        
        if post['publisher_id'] != callback.from_user.id:
            user = await db.get_user(callback.from_user.id)
            if user['role'] != 'admin':
                await callback.answer("❌ У вас нет прав")
                return
        
        new_status = await db.toggle_post_status(post_id)
        status_text = "активирован" if new_status else "деактивирован"
        
        await callback.answer(f"✅ Пост {status_text}")
        
        # Обновляем сообщение
        await my_posts_command(callback.message)
        
    except Exception as e:
        logger.error(f"Ошибка в toggle_post_status_callback: {e}")
        await callback.answer("❌ Ошибка")


# ОБРАБОТЧИК ДЛЯ РЕДАКТИРОВАНИЯ КОНТЕНТА (если пользователь отправил новый контент)
@router.message()
async def handle_content_update(message: Message, state: FSMContext):
    """Обработка обновления контента поста"""
    data = await state.get_data()
    
    if data.get("editing_post"):
        post_id = data.get("post_id")
        
        if message.text == "/cancel":
            await state.clear()
            await message.answer("❌ Редактирование отменено")
            return
        
        # Получаем текущий пост
        post = await db.get_post_by_id(post_id)
        if not post:
            await state.clear()
            await message.answer("❌ Пост не найден")
            return
        
        # Определяем тип контента
        content_type = post['content_type']
        content_text = post['content_text']
        content_file_id = post['content_file_id']
        
        if message.text:
            content_type = "text"
            content_text = message.text
            content_file_id = None
        elif message.photo:
            content_type = "photo"
            content_file_id = message.photo[-1].file_id
            content_text = message.caption or ""
        elif message.video:
            content_type = "video"
            content_file_id = message.video.file_id
            content_text = message.caption or ""
        else:
            await message.answer("❌ Поддерживается только текст, фото или видео")
            return
        
        # Обновляем пост в БД
        await db.update_post_content(
            post_id=post_id,
            content_type=content_type,
            content_text=content_text,
            content_file_id=content_file_id,
            channels=json.loads(post['channels']) if post['channels'] else []
        )
        
        # Создаем запись о редакции
        revision_id = await db.create_post_revision(
            post_id=post_id,
            content_type=content_type,
            content_text=content_text,
            content_file_id=content_file_id,
            channels=json.loads(post['channels']) if post['channels'] else []
        )
        
        await message.answer(
            f"✅ Контент обновлен!\n"
            f"📝 Ревизия #{revision_id} создана\n\n"
            f"Хотите отправить обновление подписчикам?\n"
            f"Используйте кнопку '🔄 Отправить обновление' в списке постов"
        )
        
        await state.clear()