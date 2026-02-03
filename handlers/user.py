import asyncio
import json
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramAPIError

from config import GLOBAL_CHANNEL, TARIFFS
import database as db
from subscription_checker import SubscriptionChecker

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def start_command(message: Message):
    """Обработчик команды /start"""
    await db.create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )
    
    args = message.text.split()
    
    if len(args) > 1:
        unique_code = args[1]
        await handle_post_access(message, unique_code)
    else:
        await show_main_menu(message)


async def show_main_menu(message: Message):
    """Показывает главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🎭 Мой профиль", callback_data="my_profile")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help_info")]
    ])
    
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "📝 Получайте доступ к эксклюзивному контенту\n"
        "🔒 Гарантированная проверка подписок\n"
        "💰 Монетизация через кредиты",
        reply_markup=keyboard
    )


async def handle_post_access(message: Message, unique_code: str):
    """Обработка доступа к посту с надежной проверкой (для /start команды)"""
    logger.info(f"=== handle_post_access (для /start) ===")
    logger.info(f"message.from_user.id: {message.from_user.id}")
    
    # Просто вызываем новую функцию
    await handle_post_access_for_user(
        bot=message.bot,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        unique_code=unique_code
    )

async def show_subscription_request(message: Message, channel: str, unique_code: str):
    """Запрос на подписку на один канал (для /start команды)"""
    # Просто вызываем новую функцию
    await show_subscription_request_for_user(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        channel=channel,
        unique_code=unique_code
    )

async def show_channels_subscription_request(message: Message, channels: list, unique_code: str):
    """Запрос на подписку на несколько каналов (для /start команды)"""
    # Просто вызываем новую функцию
    await show_channels_subscription_request_for_user(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        channels=channels,
        unique_code=unique_code
    )

async def show_post_content(message: Message, post: dict):
    """Показ контента (для /start команды)"""
    # Просто вызываем новую функцию
    await show_post_content_for_user(
        bot=message.bot,
        chat_id=message.chat.id,
        post=post
    )

async def handle_post_access_for_user(bot: Bot, user_id: int, chat_id: int, unique_code: str):
    """
    Обработка доступа к посту для конкретного пользователя
    """
    logger.info(f"=== handle_post_access_for_user ===")
    logger.info(f"user_id: {user_id}")
    logger.info(f"chat_id: {chat_id}")
    logger.info(f"unique_code: {unique_code}")
    
    # Получаем пост
    post = await db.get_post(unique_code)
    
    if not post:
        await bot.send_message(chat_id, "❌ Пост не найден или был удален")
        return
    
    if not post['is_active']:
        await bot.send_message(chat_id, "❌ Этот пост временно недоступен")
        return
    
    checker = SubscriptionChecker(bot)
    
    # Проверяем подписку на глобальный канал
    if GLOBAL_CHANNEL:
        logger.info(f"Проверка глобального канала {GLOBAL_CHANNEL} для user_id={user_id}")
        
        is_subscribed, error_msg = await checker.check_user_subscription(
            user_id, 
            GLOBAL_CHANNEL
        )
        
        logger.info(f"Глобальная проверка: subscribed={is_subscribed}, error={error_msg}")
        
        if not is_subscribed:
            logger.info(f"Пользователь НЕ подписан на глобальный канал")
            await bot.send_message(chat_id, f"⚠️ {error_msg}")
            await show_subscription_request_for_user(
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                channel=GLOBAL_CHANNEL,
                unique_code=unique_code
            )
            return
        else:
            logger.info(f"✅ Пользователь подписан на глобальный канал")
    
    # Проверяем подписки на каналы разместителя
    channels = json.loads(post['channels']) if post['channels'] else []
    
    if channels:
        logger.info(f"Проверка каналов разместителя: {channels}")
        
        await bot.send_message(chat_id, f"🔍 Проверяем подписки на {len(channels)} канал(ов)...")
        
        results = await checker.check_multiple_subscriptions(user_id, channels)
        
        # Собираем неподписанные каналы
        not_subscribed_channels = []
        all_subscribed = True
        
        for channel, (is_subscribed, error_msg) in results.items():
            await db.update_subscription(user_id, channel, is_subscribed)
            
            if not is_subscribed:
                all_subscribed = False
                not_subscribed_channels.append(channel)
                logger.info(f"❌ Пользователь НЕ подписан на {channel}")
                await bot.send_message(chat_id, f"❌ {error_msg}")
            else:
                logger.info(f"✅ Пользователь подписан на {channel}")
        
        if not all_subscribed:
            logger.info(f"Пользователь не прошел проверку, каналы: {not_subscribed_channels}")
            
            if len(not_subscribed_channels) == 1:
                await show_subscription_request_for_user(
                    bot=bot,
                    chat_id=chat_id,
                    user_id=user_id,
                    channel=not_subscribed_channels[0],
                    unique_code=unique_code
                )
            else:
                await show_channels_subscription_request_for_user(
                    bot=bot,
                    chat_id=chat_id,
                    user_id=user_id,
                    channels=not_subscribed_channels,
                    unique_code=unique_code
                )
            return
        else:
            logger.info(f"✅ Все проверки пройдены")
            await bot.send_message(chat_id, "✅ Все подписки подтверждены")
    
    # Все проверки пройдены - показываем контент
    logger.info(f"Показ контента для пользователя {user_id}")
    await db.increment_post_views(post['id'])
    await show_post_content_for_user(bot, chat_id, post)

async def show_subscription_request_for_user(bot: Bot, chat_id: int, user_id: int, channel: str, unique_code: str):
    """Запрос на подписку для конкретного пользователя"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{channel[1:]}")],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check_sub_{unique_code}_{channel}")]
    ])
    
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"<b>📢 Требуется подписка на канал:</b>\n\n"
            f"👉 {channel}\n\n"
            "1️⃣ Подпишитесь на канал выше ⬆️\n"
            "2️⃣ Нажмите кнопку '✅ Проверить подписку'\n\n"
            "<i>Убедитесь, что действительно подписались!</i>"
        ),
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def show_channels_subscription_request_for_user(bot: Bot, chat_id: int, user_id: int, channels: list, unique_code: str):
    """Запрос на подписку на несколько каналов для конкретного пользователя"""
    buttons = []
    
    for channel in channels:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 Подписаться на {channel}", 
                url=f"https://t.me/{channel[1:]}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="✅ Проверить все подписки", 
            callback_data=f"check_all_{unique_code}"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    channels_list = "\n".join([f"• {channel}" for channel in channels])
    
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"📢 Требуется подписка на каналы:\n\n"
            f"{channels_list}\n\n"
            "1️⃣ Подпишитесь на ВСЕ каналы выше ⬆️\n"
            "2️⃣ Нажмите кнопку '✅ Проверить все подписки'\n\n"
            "💡 Проверьте каждый канал отдельно!"
        ),
        reply_markup=keyboard
    )

async def show_post_content_for_user(bot: Bot, chat_id: int, post: dict):
    """Показ контента для конкретного пользователя"""
    try:
        # Базовый текст с информацией об успешном открытии
        success_text = "🎉 <b>Контент успешно открыт!</b>\n\n"
        
        # Добавляем текст контента, если он есть
        if post['content_text']:
            success_text += f"<b>Текст - </b>\n{post['content_text']}\n\n"
        
        success_text += "Хотите также размещать контент?\nСтаньте разместителем!"
        
        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать свой пост", callback_data="become_publisher")]
        ])
        
        # В зависимости от типа контента отправляем по-разному
        if post['content_type'] == 'text':
            # Для текста просто отправляем сообщение с клавиатурой
            await bot.send_message(
                chat_id=chat_id,
                text=success_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        elif post['content_type'] == 'photo':
            # Для фото отправляем фото с подписью и клавиатурой
            await bot.send_photo(
                chat_id=chat_id,
                photo=post['content_file_id'],
                caption=success_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        elif post['content_type'] == 'video':
            # Для видео отправляем видео с подписью и клавиатурой
            await bot.send_video(
                chat_id=chat_id,
                video=post['content_file_id'],
                caption=success_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        else:
            # Если тип неизвестен, отправляем просто текст
            await bot.send_message(
                chat_id=chat_id,
                text=success_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Ошибка при показе контента: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при показе контента"
        )

@router.callback_query(F.data.startswith("check_sub_"))
async def check_single_subscription(callback: CallbackQuery):
    """Проверка подписки на один канал"""
    try:
        # Формат: check_sub_{unique_code}_{channel}
        parts = callback.data.split("_")
        if len(parts) < 4:
            await callback.answer("❌ Ошибка в данных кнопки")
            return
        
        unique_code = parts[2]
        channel = parts[3]  # Получаем канал из callback_data
        
        logger.info(f"=== check_single_subscription ===")
        logger.info(f"Пользователь (callback.from_user.id): {callback.from_user.id}")
        logger.info(f"Канал: {channel}")
        logger.info(f"Уникальный код: {unique_code}")
        
        await callback.answer("🔍 Проверяем подписку...")
        await asyncio.sleep(5)
        
        # Удаляем сообщение с кнопками
        try:
            await callback.message.delete()
        except:
            pass
        
        # Проверяем только один канал
        checker = SubscriptionChecker(callback.bot)
        is_subscribed, error_msg = await checker.check_user_subscription(
            callback.from_user.id,  # Правильный ID пользователя
            channel
        )
        
        if is_subscribed:
            # Если подписан, проверяем весь пост
            # Для этого создаем правильное сообщение
            await handle_post_access_for_user(
                bot=callback.bot,
                user_id=callback.from_user.id,
                chat_id=callback.message.chat.id,
                unique_code=unique_code
            )
        else:
            # Если не подписан, показываем ошибку прямо через callback.bot
            await callback.bot.send_message(
                chat_id=callback.message.chat.id,
                text=f"❌ {error_msg}"
            )
            # Показываем кнопку для подписки заново
            await show_subscription_request_for_user(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                user_id=callback.from_user.id,
                channel=channel,
                unique_code=unique_code
            )
        
    except Exception as e:
        logger.error(f"Ошибка в check_single_subscription: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data.startswith("check_all_"))
async def check_all_subscriptions(callback: CallbackQuery):
    """Проверка подписок на все каналы"""
    try:
        parts = callback.data.split("_")
        if len(parts) < 3:
            await callback.answer("❌ Ошибка в данных кнопки")
            return
        
        unique_code = parts[2]
        
        logger.info(f"=== check_all_subscriptions ===")
        logger.info(f"Пользователь (callback.from_user.id): {callback.from_user.id}")
        logger.info(f"Уникальный код: {unique_code}")
        
        await callback.answer("🔍 Проверяем все подписки...")
        await asyncio.sleep(5)
        
        # Удаляем сообщение с кнопками
        try:
            await callback.message.delete()
        except:
            pass
        
        # Проверяем весь пост
        await handle_post_access_for_user(
            bot=callback.bot,
            user_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            unique_code=unique_code
        )
        
    except Exception as e:
        logger.error(f"Ошибка в check_all_subscriptions: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "buy_subscription")
async def buy_subscription_callback(callback: CallbackQuery):
    """Покупка подписки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Базовая - 100 руб", callback_data="tariff_basic")],
        [InlineKeyboardButton(text="💰 Стандартная - 250 руб", callback_data="tariff_standard")],
        [InlineKeyboardButton(text="💰 Премиум - 500 руб", callback_data="tariff_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(
        "💰 Выберите тариф подписки:\n\n"
        "🟢 Базовая - 100 руб\n"
        "• 10 кредитов\n"
        "• Создание до 10 постов\n\n"
        "🔵 Стандартная - 250 руб\n"
        "• 30 кредитов\n"
        "• Создание до 30 постов\n"
        "• Приоритетная поддержка\n\n"
        "🟣 Премиум - 500 руб\n"
        "• 70 кредитов\n"
        "• Создание до 70 постов\n"
        "• VIP поддержка\n"
        "• Статистика по постам\n\n"
        "💎 1 кредит = 1 канал в посте\n\n\n"
        "В данный момент пополнение кредитов осуществляется через владельца @SMEPTHbIE",
        reply_markup=keyboard
    )
    await callback.answer()


#@router.callback_query(F.data.startswith("tariff_"))
#async def process_tariff(callback: CallbackQuery):
    #"""Обработка выбора тарифа"""
    #tariff = callback.data.split("_")[1]
    
    #if tariff not in TARIFFS:
        #await callback.answer("❌ Тариф не найден")
        #return
    
    #price = TARIFFS[tariff]["price"]
    #credits = TARIFFS[tariff]["credits"]
    
    # Создаем запись о платеже
    #payment_id = await db.create_payment(
        #user_id=callback.from_user.id,
        #amount=price,
        #credits=credits
    #)
    
    # Начисляем кредиты
    #await db.add_credits(callback.from_user.id, credits)
    #await db.update_payment_status(payment_id, "completed")
    
    # Автоматически назначаем роль разместителя
    #user = await db.get_user(callback.from_user.id)
    #if user['role'] == 'user':
        #await db.update_user_role(callback.from_user.id, 'publisher')
    
    # Обновляем сообщение
    #await callback.message.edit_text(
        #f"✅ Оплата принята!\n\n"
        #f"💎 Начислено: {credits} кредитов\n"
        #f"💰 Сумма: {price} руб\n"
        #f"📦 Тариф: {tariff.capitalize()}\n"
        #f"🎭 Новая роль: Разместитель\n\n"
        #f"🆔 ID платежа: {payment_id}\n\n"
        #f"💡 Теперь вы можете создавать посты командой /create_post"
    #)
    
    # Показываем кнопку для создания поста
    #keyboard = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text="📝 Создать пост", callback_data="create_post_now")],
        #[InlineKeyboardButton(text="💰 Еще кредитов", callback_data="buy_subscription")]
    #])
    
    #await callback.message.answer(
        #"🎉 Готово! Что дальше?",
        #reply_markup=keyboard
    #)
    
    #await callback.answer()


@router.callback_query(F.data == "my_profile")
async def my_profile_callback(callback: CallbackQuery):
    """Показ профиля"""
    user = await db.get_user(callback.from_user.id)
    
    if not user:
        await callback.answer("❌ Вы не зарегистрированы в системе")
        return
    
    role_emoji = {
        "user": "👤",
        "publisher": "📝", 
        "admin": "👑"
    }
    
    role_text = {
        "user": "Пользователь",
        "publisher": "Разместитель",
        "admin": "Администратор"
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    profile_text = (
        f"{role_emoji.get(user['role'], '👤')} Ваш профиль:\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"👤 Имя: {user['full_name']}\n"
        f"📱 Username: @{user['username']}\n"
        f"🎭 Роль: {role_text.get(user['role'], 'Пользователь')}\n"
        f"💰 Кредиты: {user['credits']}\n"
        f"📅 Регистрация: {user['created_at']}\n\n"
    )
    
    if user['role'] == 'user':
        profile_text += "💡 Чтобы стать разместителем, купите подписку"
    elif user['role'] == 'publisher':
        profile_text += f"💡 Вы можете создавать посты. Баланс: {user['credits']} кредитов"
    
    await callback.message.edit_text(
        profile_text,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "help_info")
async def help_info_callback(callback: CallbackQuery):
    """Показ справки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Как создать пост?", callback_data="how_create_post")],
        [InlineKeyboardButton(text="💰 Как купить кредиты?", callback_data="how_buy_credits")],
        [InlineKeyboardButton(text="🔐 Как работает защита?", callback_data="how_protection")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(
        "❓ Помощь по боту:\n\n"
        "Выберите интересующий вас раздел:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "how_create_post")
async def how_create_post_callback(callback: CallbackQuery):
    """Инструкция по созданию поста"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Создать пост сейчас", callback_data="create_post_now")],
        [InlineKeyboardButton(text="🔙 Назад в помощь", callback_data="help_info")]
    ])
    
    await callback.message.edit_text(
        "📝 Как создать пост:\n\n"
        "1. Станьте разместителем\n"
        "   • Купите подписку (/subscribe)\n"
        "   • Или обратитесь к администратору\n\n"
        "2. Купите кредиты\n"
        "   • 1 кредит = 1 канал в посте\n"
        "   • Используйте /subscribe\n\n"
        "3. Создайте пост\n"
        "   • Используйте команду /create_post\n"
        "   • Отправьте текст, фото или видео\n"
        "   • Укажите каналы для подписки\n\n"
        "4. Получите ссылку\n"
        "   • Бот даст уникальную ссылку\n"
        "   • Отправьте её пользователям\n\n"
        "💡 Бот должен быть администратором в указанных каналах!",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "how_buy_credits")
async def how_buy_credits_callback(callback: CallbackQuery):
    """Инструкция по покупке кредитов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Купить кредиты", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад в помощь", callback_data="help_info")]
    ])
    
    await callback.message.edit_text(
        "💰 Как купить кредиты:\n\n"
        "1. Выберите тариф\n"
        "   • Базовая: 100 руб = 10 кредитов\n"
        "   • Стандартная: 250 руб = 30 кредитов\n"
        "   • Премиум: 500 руб = 70 кредитов\n\n"
        "2. Оплатите\n"
        "   • Нажмите на нужный тариф\n"
        "   • Кредиты начислятся мгновенно\n\n"
        "3. Используйте кредиты\n"
        "   • 1 кредит = 1 канал в посте\n"
        "   • При создании поста\n"
        "   • Кредиты спишутся автоматически\n\n"
        "💡 Что дают кредиты:\n"
        "• Создание постов с обязательной подпиской\n"
        "• Привлечение подписчиков в ваши каналы\n"
        "• Монетизация вашего контента",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "how_protection")
async def how_protection_callback(callback: CallbackQuery):
    """Объяснение системы защиты"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в помощь", callback_data="help_info")]
    ])
    
    await callback.message.edit_text(
        "🔐 Как работает защита:\n\n"
        "✅ 100% гарантия подписки:\n"
        "• Бот проверяет подписку через API Telegram\n"
        "• Нельзя обойти или подделать\n"
        "• Проверка в реальном времени\n\n"
        "📢 Обязательные каналы:\n"
        "1. Глобальный канал - обязателен для всех\n"
        "2. Каналы разместителя - на выбор автора\n\n"
        "🛡️ Для разместителей:\n"
        "• Вы гарантированно получаете подписчиков\n"
        "• Каждый пользователь должен подписаться\n"
        "• Проверка перед показом контента\n\n"
        "⚙️ Технически:\n"
        "• Бот проверяет статус подписки\n"
        "• Использует официальный API Telegram\n"
        "• Надежно и безопасно",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "become_publisher")
async def become_publisher_callback(callback: CallbackQuery):
    """Обработка кнопки 'Создать свой пост'"""
    user = await db.get_user(callback.from_user.id)
    
    # Если пользователь уже разместитель
    if user['role'] in ['publisher', 'admin']:
        await callback.answer("🎉 Вы уже разместитель!")
        
        # Показываем инструкцию как создать пост (НОВОЕ сообщение)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать пост сейчас", callback_data="create_post_now")],
            [InlineKeyboardButton(text="💰 Купить кредиты", callback_data="buy_subscription")]
        ])
        
        # Используем answer() вместо edit_text()
        await callback.message.answer(
            f"🎭 <b>Вы уже разместитель!</b>\n\n"
            f"💎 <b>Ваш баланс:</b> {user['credits']} кредитов\n\n"
            f"<b>Что вы можете сделать:</b>\n"
            f"• Создать пост командой /create_post\n"
            f"• Посмотреть свои посты командой /my_posts\n"
            f"• Купить больше кредитов",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    # Если пользователь не разместитель
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🎭 Мой профиль", callback_data="my_profile")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    # Удаляем старое сообщение и отправляем новое
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        "📝 <b>Стать разместителем:</b>\n\n"
        "<b>Вариант 1: Купить подписку</b>\n"
        "• Покупаете любой тариф\n"
        "• Автоматически становитесь разместителем\n"
        "• Получаете кредиты для постов\n\n"
        "<b>Вариант 2: Попросить администратора</b>\n"
        "• Напишите администратору\n"
        "• Попросите назначить вас разместителем\n\n"
        "<b>Что дает роль разместителя:</b>\n"
        "• Создание постов с обязательной подпиской\n"
        "• Привлечение подписчиков в ваши каналы\n"
        "• Монетизация вашего контента\n"
        "• Полная статистика по постам",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "create_post_now")
async def create_post_now_callback(callback: CallbackQuery):
    """Переход к созданию поста"""
    user = await db.get_user(callback.from_user.id)
    
    if user['role'] != 'publisher' and user['role'] != 'admin':
        await callback.answer("❌ У вас нет прав разместителя")
        return
    
    if user['credits'] <= 0:
        await callback.answer("❌ Недостаточно кредитов")
        return
    
    await callback.message.answer(
        f"🎉 Начинаем создание поста!\n\n"
        f"💎 Ваш баланс: {user['credits']} кредитов\n"
        f"📊 1 кредит = 1 канал в посте\n\n"
        f"Используйте команду:\n"
        f"👉 `/create_post`"
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    """Возврат в главное меню"""
    await show_main_menu(callback.message)
    await callback.answer()


@router.message(Command("profile"))
async def profile_command(message: Message):
    """Показ профиля пользователя через команду"""
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ Вы не зарегистрированы в системе")
        return
    
    role_emoji = {
        "user": "👤",
        "publisher": "📝", 
        "admin": "👑"
    }
    
    role_text = {
        "user": "Пользователь",
        "publisher": "Разместитель",
        "admin": "Администратор"
    }
    
    profile_text = (
        f"{role_emoji.get(user['role'], '👤')} Ваш профиль:\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"👤 Имя: {user['full_name']}\n"
        f"📱 Username: @{user['username']}\n"
        f"🎭 Роль: {role_text.get(user['role'], 'Пользователь')}\n"
        f"💰 Кредиты: {user['credits']}\n"
        f"📅 Регистрация: {user['created_at']}\n\n"
    )
    
    if user['role'] == 'user':
        profile_text += "💡 Чтобы стать разместителем, купите подписку командой /subscribe"
    elif user['role'] == 'publisher':
        profile_text += f"💡 Вы можете создавать посты командой /create_post. Баланс: {user['credits']} кредитов"
    
    await message.answer(profile_text)


@router.message(Command("help"))
async def help_command(message: Message):
    """Показ справки через команду"""
    await message.answer(
        "❓ Помощь по боту:\n\n"
        "Основные команды:\n"
        "• /start - Запустить бота\n"
        "• /profile - Ваш профиль\n"
        "• /subscribe - Купить подписку/кредиты\n"
        "• /status - Проверить статус\n"
        "• /help - Эта справка\n\n"
        "Для разместителей:\n"
        "• /create_post - Создать новый пост\n"
        "• /my_posts - Мои посты\n\n"
        "Для администраторов:\n"
        "• /admin - Панель администратора\n\n"
        "Проверка каналов:\n"
        "• /check_channel @channel - Проверить канал"
    )


@router.message(Command("subscribe"))
async def subscribe_command(message: Message):
    """Показ тарифов подписки через команду"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Базовая - 100 руб", callback_data="tariff_basic")],
        [InlineKeyboardButton(text="💰 Стандартная - 250 руб", callback_data="tariff_standard")],
        [InlineKeyboardButton(text="💰 Премиум - 500 руб", callback_data="tariff_premium")],
        [InlineKeyboardButton(text="🎭 Мой профиль", callback_data="my_profile")]
    ])
    
    await message.answer(
        "💰 Выберите тариф подписки:\n\n"
        "🟢 Базовая - 100 руб (10 кредитов)\n"
        "🔵 Стандартная - 250 руб (30 кредитов)\n"
        "🟣 Премиум - 500 руб (70 кредитов)\n\n"
        "💎 Кредиты используются для создания постов.\n"
        "1 кредит = 1 канал в посте.\n\n"
        "💡 При покупке подписки вы автоматически становитесь разместителем!",
        reply_markup=keyboard
    )


@router.message(Command("status"))
async def status_command(message: Message):
    """Проверка статуса пользователя"""
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ Вы не зарегистрированы в системе")
        return
    
    role_text = {
        "user": "👤 Обычный пользователь\n\n"
                "Вы можете:\n"
                "• Переходить по ссылкам на контент\n"
                "• Покупать подписки\n\n"
                "Для получения прав разместителя\n"
                "купите подписку командой /subscribe",
        
        "publisher": "📝 Разместитель\n\n"
                    "Вы можете:\n"
                    "• Создавать посты (/create_post)\n"
                    "• Получать уникальные ссылки\n"
                    "• Просматривать статистику (/my_posts)\n\n"
                    f"💎 Ваш баланс: {user['credits']} кредитов\n"
                    "1 кредит = 1 канал в посте\n\n"
                    "🎯 Для создания поста используйте /create_post",
        
        "admin": "👑 Администратор\n\n"
                "Вы можете:\n"
                "• Управлять пользователями (/admin)\n"
                "• Добавлять кредиты\n"
                "• Назначать разместителей\n"
                "• Блокировать посты\n\n"
                f"💎 Ваш баланс: {user['credits']} кредитов"
    }
    
    await message.answer(f"🎭 Ваш статус:\n\n{role_text.get(user['role'], '❓ Неизвестная роль')}")


@router.message(Command("check_channel"))
async def check_channel_command(message: Message):
    """Проверка канала на наличие прав бота"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("Использование: /check_channel @username_канала")
        return
    
    channel = args[1]
    if not channel.startswith("@"):
        channel = f"@{channel}"
    
    checker = SubscriptionChecker(message.bot)
    
    await message.answer(f"🔍 Проверяем канал {channel}...")
    
    result = await checker.verify_channel(channel)
    
    if result["is_valid"]:
        response = (
            f"✅ Канал настроен правильно!\n\n"
            f"📢 Канал: {result['info']['title']}\n"
            f"👤 Username: {result['info']['username']}\n"
            f"🆔 ID: {result['info']['id']}\n"
            f"📊 Тип: {result['info']['type']}\n\n"
            f"🤖 Бот является администратором ✅\n"
            f"📝 Может постить сообщения ✅\n\n"
            f"💡 Теперь этот канал можно использовать в постах"
        )
    else:
        response = (
            f"❌ Проблемы с каналом {channel}:\n\n"
            f"{result['error']}\n\n"
            f"📋 Что нужно сделать:\n"
            f"1. Добавьте бота как администратора в канал\n"
            f"2. Дайте права на постинг сообщений\n"
            f"3. Убедитесь, что канал существует\n"
            f"4. Проверьте снова командой /check_channel {channel}"
        )
    
    await message.answer(response)