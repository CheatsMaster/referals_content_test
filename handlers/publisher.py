from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json

import database as db
from subscription_checker import SubscriptionChecker

router = Router()


class CreatePostStates(StatesGroup):
    waiting_name = State()
    waiting_content = State()
    waiting_channels = State()

class UpdatePostStates(StatesGroup):
    waiting_content = State()


@router.message(Command("create_post"))
async def create_post_start(message: Message, state: FSMContext):
    """Начало создания поста"""
    user = await db.get_user(message.from_user.id)
    
    if not user or user['role'] not in ['publisher', 'admin']:
        await message.answer("❌ У вас нет прав разместителя. Обратитесь к администратору.")
        return
    
    await message.answer(
        "📝 Создание нового поста:\n\n"
        "1️⃣ Придумайте название посту\n"
        "2️⃣ Отправьте контент:\n"
        "• Текст сообщения\n"
        "• Фото с подписью\n"
        "• Видео с подписью\n\n"
        "3️⃣ Затем отправьте каналы для подписки\n"
        "Получите уникальную ссылку\n\n"
        "❌ Отправьте /cancel для отмены"
    )
    await state.set_state(CreatePostStates.waiting_name)
    await state.update_data(content={"type": None, "text": "", "file_id": None})


@router.message(CreatePostStates.waiting_content, F.text == "/cancel")
async def cancel_create_post(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Создание поста отменено")

@router.message(CreatePostStates.waiting_name)
async def process_post_name(message: Message, state: FSMContext):
    """Обработка названия поста"""
    post_name = message.text.strip()
    
    if len(post_name) < 2:
        await message.answer("❌ Название должно быть не менее 2 символов")
        return
    
    if len(post_name) > 100:
        await message.answer("❌ Название должно быть не более 100 символов")
        return
    
    await state.update_data(post_name=post_name)
    
    await message.answer(
        f"✅ Название сохранено: '{post_name}'\n\n"
        f"2️⃣ Отправьте контент:\n"
        f"• Текст сообщения\n"
        f"• Фото с подписью\n"
        f"• Видео с подписью\n\n"
        f"3️⃣ Затем отправьте каналы для подписки\n"
        f"Получите уникальную ссылку\n\n"
        f"❌ Отправьте /cancel для отмены"
    )
    await state.set_state(CreatePostStates.waiting_content)

@router.message(CreatePostStates.waiting_content)
async def process_content(message: Message, state: FSMContext):
    """Обработка контента"""
    data = await state.get_data()
    content = data["content"]
    
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
    if not message.text.startswith("@"):
        await message.answer("❌ Канал должен начинаться с @ (например: @channel_name)")
        return
    
    channel = message.text.strip()
    
    # ПРОВЕРЯЕМ КАНАЛ НАЛИЧИЕМ ПРАВ БОТА И ВОЗМОЖНОСТЬ ПРОВЕРКИ ПОДПИСОК
    checker = SubscriptionChecker(message.bot)
    
    # 1. Проверяем права администратора
    is_admin, admin_error = await checker.check_bot_admin_rights(channel)
    
    if not is_admin:
        await message.answer(
            f"❌ Проблема с каналом {channel}:\n\n"
            f"{admin_error}\n\n"
            f"Что сделать:\n"
            f"1. Добавьте бота как администратора в {channel}\n"
            f"2. Дайте права на постинг сообщений\n"
            f"3. Проверьте командой /check_channel {channel}"
        )
        return
    
    # 2. ТЕСТИРУЕМ проверку подписки на себе
    await message.answer(f"🔍 Тестируем проверку подписок в {channel}...")
    
    # ИСПРАВЛЕНИЕ: передаем правильный user_id
    test_result, test_error = await checker.check_user_subscription(
        message.from_user.id,  # Правильный ID пользователя
        channel
    )
    
    if "не имеет прав для проверки подписок" in test_error:
        await message.answer(
            f"⚠️ Внимание!\n\n"
            f"Бот не может проверять подписки в {channel}\n\n"
            f"Решение:\n"
            f"1. Зайдите в настройки канала {channel}\n"
            f"2. Права администратора → Ваш бот\n"
            f"3. Включите 'Может видеть участников'\n"
            f"4. Попробуйте снова"
        )
        return
    
    data = await state.get_data()
    channels = data["channels"]
    
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
    post_name = data["post_name"]
    content = data["content"]
    channels = data.get("channels", [])
    
    if not content["type"]:
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
    
    # Создаем пост
    unique_code = await db.create_post(
        publisher_id=message.from_user.id,
        post_name=post_name,
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
        f"🎉 Пост '{post_name}' успешно создан!\n\n"
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

@router.message(Command("my_posts"))
async def my_posts_command(message: Message):
    """Показать все посты разместителя"""
    user = await db.get_user(message.from_user.id)
    
    if not user or user['role'] not in ['publisher', 'admin']:
        await message.answer("❌ У вас нет прав разместителя")
        return
    
    posts = await db.get_user_posts_with_stats(message.from_user.id)
    
    if not posts:
        await message.answer(
            "📭 У вас пока нет созданных постов.\n\n"
            "Создайте первый пост командой:\n"
            "👉 /create_post"
        )
        return
    
    await message.answer(f"📚 Ваши посты ({len(posts)}):")
    
    for post in posts:
        channels = json.loads(post['channels']) if post['channels'] else []
        status = "🟢 Активен" if post['is_active'] else "🔴 Неактивен"
        
        # Создаем клавиатуру для поста
        builder = InlineKeyboardBuilder()
        
        # Основные кнопки
        builder.add(InlineKeyboardButton(
            text="👀 Просмотры", 
            callback_data=f"post_stats_{post['id']}"
        ))
        builder.add(InlineKeyboardButton(
            text="✏️ Обновить", 
            callback_data=f"update_post_{post['id']}"
        ))
        
        # Кнопки управления
        builder.add(InlineKeyboardButton(
            text="🚫/✅" if post['is_active'] else "✅/🚫", 
            callback_data=f"toggle_my_post_{post['id']}"
        ))
        builder.add(InlineKeyboardButton(
            text="📋 Подписчики", 
            callback_data=f"post_subscribers_{post['id']}"
        ))
        
        builder.adjust(2, 2)  # 2 кнопки в ряд
        
        # Формируем ссылку
        bot_username = (await message.bot.get_me()).username
        post_url = f"t.me/{bot_username}?start={post['unique_code']}"
        
        # Формируем сообщение
        post_info = (
            f"📝 <b>{post.get('post_name', 'Без названия')}</b>\n\n"
            f"🆔 Код: <code>{post['unique_code']}</code>\n"
            f"🔗 Ссылка: {post_url}\n"
            f"👀 Просмотров: {post['views']}\n"
            f"👥 Подписчиков: {post.get('subscribers_count', 0)}\n"
            f"📢 Каналов: {len(channels)}\n"
            f"📅 Создан: {post['created_at']}\n"
            f"📊 Статус: {status}\n"
        )
        
        await message.answer(post_info, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    # Кнопка обновить весь список
    refresh_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить список", callback_data="refresh_my_posts")]
    ])
    
    await message.answer(
        "💡 <b>Управление постами:</b>\n\n"
        "• <b>👀 Просмотры</b> - детальная статистика\n"
        "• <b>✏️ Обновить</b> - изменить контент поста\n"
        "• <b>🚫/✅</b> - активировать/деактивировать пост\n"
        "• <b>📋 Подписчики</b> - список подписчиков на обновления\n\n"
        "Нажмите 🔄 чтобы обновить список",
        reply_markup=refresh_keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("update_post_"))
async def update_post_start(callback: CallbackQuery, state: FSMContext):
    """Начало обновления поста"""
    try:
        post_id = int(callback.data.split("_")[2])
        
        # Проверяем владельца поста
        post = await db.get_post_by_id(post_id)
        if not post:
            await callback.answer("❌ Пост не найден")
            return
        
        if post['publisher_id'] != callback.from_user.id and callback.from_user.id not in ADMIN_IDS:
            await callback.answer("❌ Вы не владелец этого поста")
            return
        
        await state.update_data(post_id=post_id, old_content=post)
        
        await callback.message.answer(
            f"✏️ <b>Обновление поста:</b> {post.get('post_name', 'Без названия')}\n\n"
            f"Текущий контент:\n"
            f"• Тип: {post['content_type']}\n"
            f"• Текст: {post['content_text'][:100] if post['content_text'] else 'Нет текста'}\n\n"
            f"<b>Отправьте новый контент:</b>\n"
            f"• Текст сообщения\n"
            f"• Фото с подписью\n"
            f"• Видео с подписью\n\n"
            f"💡 Можно отправить только текст для обновления описания\n\n"
            f"❌ Отправьте /cancel для отмены",
            parse_mode="HTML"
        )
        
        await state.set_state(UpdatePostStates.waiting_content)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в update_post_start: {e}")
        await callback.answer("❌ Ошибка")

@router.message(UpdatePostStates.waiting_content)
async def update_post_process_content(message: Message, state: FSMContext, bot: Bot):
    """Обработка нового контента для поста"""
    data = await state.get_data()
    post_id = data["post_id"]
    old_post = data["old_content"]
    
    # Определяем тип нового контента
    new_content = {
        "content_text": old_post['content_text'],
        "content_type": old_post['content_type'],
        "content_file_id": old_post['content_file_id']
    }
    
    if message.text and not message.text.startswith("/"):
        new_content["content_text"] = message.text
    
    elif message.photo:
        new_content["content_type"] = "photo"
        new_content["content_file_id"] = message.photo[-1].file_id
        new_content["content_text"] = message.caption or old_post['content_text']
    
    elif message.video:
        new_content["content_type"] = "video"
        new_content["content_file_id"] = message.video.file_id
        new_content["content_text"] = message.caption or old_post['content_text']
    
    else:
        await message.answer("❌ Поддерживается только текст, фото или видео")
        return
    
    # Обновляем пост в базе
    await db.update_post_content(
        post_id=post_id,
        content_type=new_content["content_type"],
        content_text=new_content["content_text"],
        content_file_id=new_content["content_file_id"]
    )
    
    # Получаем подписчиков
    subscribers = await db.get_post_subscribers(post_id)
    
    # Отправляем уведомления подписчикам
    if subscribers:
        sent_count = 0
        failed_count = 0
        
        notification_text = (
            f"🔔 <b>Обновление контента!</b>\n\n"
            f"Пост <b>{old_post.get('post_name', 'без названия')}</b> был обновлен автором.\n\n"
            f"Новый контент:"
        )
        
        # Отправляем предварительное уведомление
        for user_id in subscribers:
            try:
                await bot.send_message(user_id, notification_text, parse_mode="HTML")
                
                # Отправляем сам контент
                if new_content["content_type"] == "text":
                    await bot.send_message(user_id, new_content["content_text"])
                elif new_content["content_type"] == "photo":
                    await bot.send_photo(
                        user_id, 
                        new_content["content_file_id"],
                        caption=new_content["content_text"]
                    )
                elif new_content["content_type"] == "video":
                    await bot.send_video(
                        user_id,
                        new_content["content_file_id"],
                        caption=new_content["content_text"]
                    )
                
                sent_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки обновления пользователю {user_id}: {e}")
                failed_count += 1
        
        # Удаляем тех, кому не отправилось (заблокировали бота)
        if failed_count > 0:
            for user_id in subscribers:
                try:
                    await bot.get_chat(user_id)
                except:
                    await db.unsubscribe_from_post_updates(user_id, post_id)
    
    # Формируем ответ автору
    result_message = (
        f"✅ <b>Пост успешно обновлен!</b>\n\n"
        f"📝 Название: {old_post.get('post_name', 'Без названия')}\n"
        f"🆔 ID поста: {post_id}\n\n"
    )
    
    if subscribers:
        result_message += (
            f"📢 <b>Уведомления отправлены:</b>\n"
            f"✅ Получили: {sent_count} подписчиков\n"
            f"❌ Не получили: {failed_count} (заблокировали бота)\n\n"
            f"💡 Подписчики, которые заблокировали бота, автоматически отписаны"
        )
    else:
        result_message += "📭 У этого поста пока нет подписчиков на обновления"
    
    await message.answer(result_message, parse_mode="HTML")
    
    # Обновляем исходное сообщение с постом
    try:
        await callback.message.delete()
    except:
        pass
    
    await state.clear()

@router.callback_query(F.data.startswith("post_stats_"))
async def show_post_stats(callback: CallbackQuery):
    """Показать детальную статистику поста"""
    try:
        post_id = int(callback.data.split("_")[2])
        
        # Получаем пост
        post = await db.get_post_by_id(post_id)
        if not post or post['publisher_id'] != callback.from_user.id:
            await callback.answer("❌ Пост не найден или нет доступа")
            return
        
        # Получаем дополнительную статистику
        async with aiosqlite.connect("bot_database.db") as db_conn:
            # Подписчики
            async with db_conn.execute(
                "SELECT COUNT(*) FROM post_updates_subscriptions WHERE post_id = ?", 
                (post_id,)) as cursor:
                subscribers_count = (await cursor.fetchone())[0]
            
            # Последние просмотры
            async with db_conn.execute(
                "SELECT created_at FROM posts WHERE id = ?", 
                (post_id,)) as cursor:
                created_at = (await cursor.fetchone())[0]
        
        channels = json.loads(post['channels']) if post['channels'] else []
        
        stats_text = (
            f"📊 <b>Статистика поста:</b>\n\n"
            f"📝 Название: {post.get('post_name', 'Без названия')}\n"
            f"🆔 ID: {post['id']}\n"
            f"🔗 Код: {post['unique_code']}\n\n"
            f"👀 <b>Просмотры:</b> {post['views']}\n"
            f"👥 <b>Подписчики на обновления:</b> {subscribers_count}\n"
            f"📢 <b>Каналов для подписки:</b> {len(channels)}\n"
            f"📅 <b>Создан:</b> {created_at}\n"
            f"📊 <b>Статус:</b> {'🟢 Активен' if post['is_active'] else '🔴 Неактивен'}\n\n"
        )
        
        if channels:
            stats_text += "📋 <b>Каналы:</b>\n"
            for channel in channels:
                stats_text += f"• {channel}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="refresh_my_posts")]
        ])
        
        await callback.message.answer(stats_text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в show_post_stats: {e}")
        await callback.answer("❌ Ошибка при получении статистики")

@router.callback_query(F.data.startswith("post_subscribers_"))
async def show_post_subscribers(callback: CallbackQuery):
    """Показать подписчиков на обновления поста"""
    try:
        post_id = int(callback.data.split("_")[2])
        
        post = await db.get_post_by_id(post_id)
        if not post or post['publisher_id'] != callback.from_user.id:
            await callback.answer("❌ Пост не найден или нет доступа")
            return
        
        subscribers = await db.get_post_subscribers(post_id)
        
        if not subscribers:
            await callback.message.answer(
                f"📭 У поста '{post.get('post_name', 'Без названия')}' пока нет подписчиков на обновления."
            )
            await callback.answer()
            return
        
        # Получаем информацию о пользователях
        subscribers_info = []
        for user_id in subscribers[:50]:  # Ограничиваем 50
            user = await db.get_user(user_id)
            if user:
                subscribers_info.append(f"• @{user.get('username', 'без username')} (ID: {user_id})")
        
        subscribers_text = (
            f"👥 <b>Подписчики на обновления:</b>\n"
            f"📝 Пост: {post.get('post_name', 'Без названия')}\n"
            f"📊 Всего: {len(subscribers)} подписчиков\n\n"
        )
        
        if subscribers_info:
            subscribers_text += "\n".join(subscribers_info[:20])
            if len(subscribers) > 20:
                subscribers_text += f"\n\n... и еще {len(subscribers) - 20} подписчиков"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="refresh_my_posts")]
        ])
        
        await callback.message.answer(subscribers_text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в show_post_subscribers: {e}")
        await callback.answer("❌ Ошибка")

@router.callback_query(F.data.startswith("toggle_my_post_"))
async def toggle_my_post_status(callback: CallbackQuery):
    """Активировать/деактивировать пост"""
    try:
        post_id = int(callback.data.split("_")[3])
        
        post = await db.get_post_by_id(post_id)
        if not post or post['publisher_id'] != callback.from_user.id:
            await callback.answer("❌ Пост не найден или нет доступа")
            return
        
        new_status = await db.toggle_post_status(post_id)
        status_text = "деактивирован" if not new_status else "активирован"
        
        await callback.answer(f"✅ Пост {status_text}")
        
        # Обновляем сообщение
        await my_posts_command(callback.message)
        
    except Exception as e:
        logger.error(f"Ошибка в toggle_my_post_status: {e}")
        await callback.answer("❌ Ошибка")

@router.callback_query(F.data == "refresh_my_posts")
async def refresh_my_posts(callback: CallbackQuery):
    """Обновить список постов"""
    try:
        # Удаляем старое сообщение
        try:
            await callback.message.delete()
        except:
            pass
        
        # Показываем обновленный список
        await my_posts_command(callback.message)
        await callback.answer("✅ Список обновлен")
        
    except Exception as e:
        logger.error(f"Ошибка в refresh_my_posts: {e}")
        await callback.answer("❌ Ошибка обновления")