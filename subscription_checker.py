import asyncio
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


class SubscriptionChecker:
    """Надежная проверка подписок и прав администратора"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def check_bot_admin_rights(self, channel_username: str) -> tuple[bool, str]:
        """
        Проверяет, что бот является администратором канала
        """
        try:
            # Пытаемся получить информацию о канале
            try:
                chat = await self.bot.get_chat(channel_username)
            except TelegramAPIError as e:
                logger.error(f"Не могу найти канал {channel_username}: {e}")
                return False, f"❌ Канал {channel_username} не найден"
            
            # Проверяем права бота
            try:
                bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
                
                if bot_member.status == "administrator":
                    if not hasattr(bot_member, 'can_post_messages') or not bot_member.can_post_messages:
                        return False, f"❌ Бот не имеет права постить сообщения в {channel_username}"
                    return True, ""
                elif bot_member.status == "creator":
                    return True, ""
                else:
                    return False, f"❌ Бот не является администратором в {channel_username}"
                    
            except TelegramAPIError as e:
                logger.error(f"Ошибка при проверке прав бота: {e}")
                return False, f"❌ Не могу проверить права бота в {channel_username}"
                
        except Exception as e:
            logger.error(f"Ошибка при проверке прав бота: {e}")
            return False, f"❌ Произошла ошибка при проверке прав бота"
    
    async def check_user_subscription(self, user_id: int, channel_username: str) -> tuple[bool, str]:
        """
        Проверяет подписку пользователя на канал
        Возвращает: (is_subscribed: bool, error_message: str)
        """
        try:
            logger.info(f"=== НАЧАЛО ПРОВЕРКИ ПОДПИСКИ ===")
            logger.info(f"Пользователь ID: {user_id}")
            logger.info(f"Канал: {channel_username}")
            logger.info(f"ID бота: {self.bot.id}")
            
            # УМНАЯ ПРОВЕРКА: если проверяется подписка бота - это может быть нормально
            # Например, когда разместитель тестирует свой канал
            if user_id == self.bot.id:
                logger.warning(f"⚠️ Проверяется подписка самого бота (ID: {user_id})")
                # Продолжаем проверку - бот тоже может быть участником канала
            
            # Сначала проверяем, что бот имеет права администратора
            is_admin, admin_error = await self.check_bot_admin_rights(channel_username)
            if not is_admin:
                logger.error(f"Бот не админ в {channel_username}: {admin_error}")
                return False, admin_error
            
            # Получаем ID канала
            try:
                chat = await self.bot.get_chat(channel_username)
                channel_id = chat.id
                logger.info(f"ID канала: {channel_id}")
            except TelegramAPIError as e:
                logger.error(f"Не могу получить канал {channel_username}: {e}")
                return False, f"❌ Канал {channel_username} не найден или недоступен"
            
            # Проверяем подписку пользователя
            try:
                user_member = await self.bot.get_chat_member(channel_id, user_id)
                
                # Детально логируем статус
                logger.info(f"Статус пользователя {user_id}: {user_member.status}")
                logger.info(f"Информация о пользователе: {user_member.user}")
                
                # Проверяем статусы
                if user_member.status in ["creator", "administrator", "member"]:
                    logger.info(f"✅ Пользователь {user_id} подписан на {channel_username}")
                    return True, ""
                elif user_member.status == "restricted":
                    # Проверяем конкретные атрибуты для restricted пользователей
                    if hasattr(user_member, 'is_member') and user_member.is_member:
                        logger.info(f"✅ Пользователь {user_id} подписан (restricted, но is_member=True)")
                        return True, ""
                    else:
                        logger.info(f"❌ Пользователь {user_id} НЕ подписан (restricted, is_member=False)")
                        return False, f"❌ Вы не подписаны на канал {channel_username}"
                else:
                    logger.info(f"❌ Пользователь {user_id} НЕ подписан (статус: {user_member.status})")
                    return False, f"❌ Вы не подписаны на канал {channel_username}"
                    
            except TelegramAPIError as e:
                error_msg = str(e).lower()
                logger.error(f"Ошибка TelegramAPI при проверке подписки: {e}")
                
                # Анализируем ошибку более точно
                if "user not found" in error_msg or "chat not found" in error_msg:
                    logger.info(f"Пользователь {user_id} не найден в канале {channel_username}")
                    return False, f"❌ Вы не подписаны на канал {channel_username}"
                elif "not enough rights" in error_msg:
                    return False, f"❌ Бот не имеет прав для проверки подписок в {channel_username}"
                elif "bot was blocked by the user" in error_msg:
                    return False, f"❌ Пользователь заблокировал бота"
                else:
                    return False, f"❌ Ошибка при проверке подписки: {str(e)[:100]}"
                    
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при проверке подписки: {e}", exc_info=True)
            return False, f"❌ Произошла ошибка при проверке подписки"
    
    async def check_multiple_subscriptions(self, user_id: int, channels: list) -> dict:
        """
        Проверяет подписки на несколько каналов
        """
        logger.info(f"Множественная проверка для пользователя {user_id}, каналы: {channels}")
        results = {}
        
        for channel in channels:
            try:
                is_subscribed, error_msg = await self.check_user_subscription(user_id, channel)
                results[channel] = (is_subscribed, error_msg)
            except Exception as e:
                logger.error(f"Ошибка при проверке канала {channel}: {e}")
                results[channel] = (False, f"❌ Ошибка при проверке канала {channel}")
        
        logger.info(f"Результаты множественной проверки: {results}")
        return results
    
    async def verify_channel(self, channel_username: str) -> dict:
        """
        Комплексная проверка канала:
        1. Существует ли канал
        2. Является ли бот администратором
        3. Может ли бот проверять подписки
        """
        try:
            # Проверяем существование канала
            try:
                chat = await self.bot.get_chat(channel_username)
                channel_info = {
                    'id': chat.id,
                    'title': chat.title,
                    'username': chat.username,
                    'type': chat.type
                }
            except TelegramAPIError as e:
                return {
                    'is_valid': False,
                    'error': f"Канал не найден: {str(e)[:100]}",
                    'info': None
                }
            
            # Проверяем права бота
            is_admin, admin_error = await self.check_bot_admin_rights(channel_username)
            
            if not is_admin:
                return {
                    'is_valid': False,
                    'error': admin_error,
                    'info': channel_info
                }
            
            # Проверяем возможность проверки подписок (тестовый вызов)
            try:
                # Пробуем получить информацию о самом боте как участнике
                bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
                
                # Проверяем может ли бот видеть участников
                if hasattr(bot_member, 'can_restrict_members'):
                    if not bot_member.can_restrict_members:
                        return {
                            'is_valid': True,
                            'error': None,
                            'info': channel_info,
                            'warning': "Бот не может видеть участников, проверка подписок может не работать"
                        }
            except Exception as e:
                logger.error(f"Ошибка при проверке прав просмотра участников: {e}")
            
            return {
                'is_valid': True,
                'error': None,
                'info': channel_info
            }
            
        except Exception as e:
            logger.error(f"Ошибка при верификации канала: {e}")
            return {
                'is_valid': False,
                'error': f"Ошибка проверки: {str(e)[:100]}",
                'info': None
            }
    
    async def debug_check_subscription(self, user_id: int, channel_username: str):
        """
        Дебаг функция для проверки подписки с детальным выводом
        """
        try:
            logger.info(f"=== ДЕБАГ проверка подписки ===")
            logger.info(f"User ID: {user_id}")
            logger.info(f"Channel: {channel_username}")
            logger.info(f"Bot ID: {self.bot.id}")
            
            # Проверяем канал
            chat = await self.bot.get_chat(channel_username)
            logger.info(f"Chat ID: {chat.id}")
            logger.info(f"Chat type: {chat.type}")
            
            # Проверяем права бота
            bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
            logger.info(f"Bot status: {bot_member.status}")
            logger.info(f"Bot can_post_messages: {getattr(bot_member, 'can_post_messages', 'N/A')}")
            
            # Проверяем пользователя
            user_member = await self.bot.get_chat_member(chat.id, user_id)
            logger.info(f"User status: {user_member.status}")
            
            # Проверяем атрибуты для restricted
            if user_member.status == "restricted":
                logger.info(f"User is_member: {getattr(user_member, 'is_member', 'N/A')}")
                logger.info(f"User until_date: {getattr(user_member, 'until_date', 'N/A')}")
            
            return True
        except Exception as e:
            logger.error(f"Дебаг ошибка: {e}")
            return False