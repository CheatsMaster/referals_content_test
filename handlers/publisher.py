from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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