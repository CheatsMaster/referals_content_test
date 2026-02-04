#!/usr/bin/env python3
import asyncio
import logging
import os
import time
import threading
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ==================== HEALTHCHECK СЕРВЕР ====================
def start_simple_healthcheck():
    """Простой healthcheck сервер для Railway"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'OK')
                # Тихий лог для дебага
                print(f"[Healthcheck] OK - {time.ctime()}")
            else:
                self.send_response(404)
                self.end_headers()
        
        def log_message(self, format, *args):
            pass  # Отключаем стандартное логирование
    
    try:
        server = HTTPServer(('0.0.0.0', 8080), HealthHandler)
        print("✅ Healthcheck сервер запущен на порту 8080")
        print("🔗 URL: http://0.0.0.0:8080/health")
        server.serve_forever()
    except Exception as e:
        print(f"❌ Ошибка healthcheck сервера: {e}")

# Запускаем healthcheck сразу при старте
health_thread = threading.Thread(target=start_simple_healthcheck, daemon=True)
health_thread.start()

# ==================== БЭКАП СЕРВИС ====================
def start_backup_service():
    """Запустить службу бэкапов в B2"""
    
    def backup_worker():
        """Рабочая функция для бэкапов"""
        import sqlite3
        import gzip
        import boto3
        from datetime import datetime
        
        print("📦 Служба бэкапов инициализирована")
        
        time.sleep(60)
        
        while True:
            try:
                # Проверяем есть ли ключи B2
                key_id = os.getenv('B2_KEY_ID')
                app_key = os.getenv('B2_APPLICATION_KEY')
                
                if not key_id or not app_key:
                    print("⚠️  Бэкапы отключены (нет ключей B2)")
                    # Ждем час и проверяем снова
                    time.sleep(3600)
                    continue
                
                # Проверяем что БД существует
                db_path = os.getenv('DB_PATH', 'bot_database.db')
                if not os.path.exists(db_path):
                    print(f"⚠️  БД не найдена: {db_path}")
                    time.sleep(3600)
                    continue
                
                # Создаем бэкап
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_name = f'backup_{timestamp}.db.gz'
                temp_path = f'/tmp/{backup_name}'
                
                print(f"🔄 Создаю бэкап: {backup_name}")
                
                # Сжимаем БД
                with open(db_path, 'rb') as f_in:
                    with gzip.open(temp_path, 'wb') as f_out:
                        f_out.write(f_in.read())
                
                # Загружаем в B2
                s3 = boto3.client(
                    's3',
                    endpoint_url='https://s3.us-east-005.backblazeb2.com',
                    aws_access_key_id=key_id,
                    aws_secret_access_key=app_key
                )
                
                bucket = os.getenv('B2_BUCKET', 'referals-content')
                s3.upload_file(
                    Filename=temp_path,
                    Bucket=bucket,
                    Key=backup_name,
                    ExtraArgs={'ContentType': 'application/gzip'}
                )
                
                # Удаляем временный файл
                os.remove(temp_path)
                
                print(f"✅ Бэкап создан и загружен: {backup_name}")
                
                # Ждем 1 час до следующего бэкапа
                time.sleep(3600)
                
            except Exception as e:
                print(f"❌ Ошибка бэкапа: {e}")
                time.sleep(300)  # ждем 5 минут при ошибке
    
    # Запускаем в отдельном потоке
    backup_thread = threading.Thread(target=backup_worker, daemon=True)
    backup_thread.start()
    return backup_thread

# ==================== ОСНОВНОЙ КОД БОТА ====================
async def main():
    """Основная функция запуска бота"""
    
    print("=" * 50)
    print("🤖 ЗАПУСК TELEGRAM БОТА")
    print("=" * 50)
    
    # Даем время healthcheck серверу запуститься
    print("⏳ Инициализация...")
    time.sleep(3)
    
    # Импорт конфига
    try:
        from config import BOT_TOKEN
    except ImportError as e:
        logger.error(f"❌ Не удалось импортировать config.py: {e}")
        print("Убедитесь что файл config.py существует")
        return
    
    # Проверка токена
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        print("Добавьте BOT_TOKEN в Railway Variables")
        return
    
    print(f"🔑 Токен: {BOT_TOKEN[:10]}...")
    
    # Запускаем службу бэкапов если есть ключи
    if os.getenv('B2_KEY_ID') and os.getenv('B2_APPLICATION_KEY'):
        start_backup_service()
        print("✅ Служба бэкапов запущена")
    else:
        print("⚠️  Бэкапы отключены (нет ключей B2)")
        print("Добавьте в Railway Variables:")
        print("  - B2_KEY_ID")
        print("  - B2_APPLICATION_KEY")
    
    # Создаем бота
    try:
        bot = Bot(token=BOT_TOKEN)
    except Exception as e:
        logger.error(f"❌ Ошибка создания бота: {e}")
        return
    
    dp = Dispatcher(storage=MemoryStorage())
    
    # ==================== РЕШЕНИЕ КОНФЛИКТА БОТОВ ====================
    print("🔄 Сбрасываю старые соединения с Telegram...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Вебхук сброшен")
    except Exception as e:
        print(f"⚠️  Не удалось сбросить вебхук: {e}")
    
    # Ждем чтобы старый бот отключился
    print("⏳ Жду 10 секунд чтобы старый бот отключился...")
    await asyncio.sleep(10)
    
    # ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ====================
    try:
        from database import init_db
        await init_db()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        # Продолжаем даже если БД не инициализировалась
    
    # ==================== ЗАГРУЗКА ХЕНДЛЕРОВ ====================
    try:
        from handlers import user, publisher, admin
        
        # Регистрация роутеров
        dp.include_router(admin.router)
        dp.include_router(publisher.router)
        dp.include_router(user.router)
        logger.info("✅ Хендлеры загружены")
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта хендлеров: {e}")
        # Создаем простой эхо-хендлер если основные не загрузились
        from aiogram import types
        
        @dp.message()
        async def echo_handler(message: types.Message):
            await message.answer(f"Бот работает! Вы написали: {message.text}")
        
        logger.info("✅ Загружен эхо-хендлер")
    
    # ==================== НАСТРОЙКА КОМАНД БОТА ====================
    try:
        await bot.set_my_commands([
            {"command": "start", "description": "Запустить бота"},
            {"command": "profile", "description": "Мой профиль"},
            {"command": "subscribe", "description": "Купить подписку"},
            {"command": "help", "description": "Помощь"},
            {"command": "status", "description": "Проверить статус"},
            {"command": "check_channel", "description": "Проверить канал"},
        ])
        logger.info("✅ Команды бота настроены")
    except Exception as e:
        logger.warning(f"⚠️  Не удалось настроить команды: {e}")
    
    # ==================== ЗАПУСК БОТА ====================
    try:
        bot_info = await bot.get_me()
        logger.info(f"🎉 Бот @{bot_info.username} запущен!")
        print(f"🎉 Бот @{bot_info.username} успешно запущен!")
        print(f"🆔 ID бота: {bot_info.id}")
        print(f"📛 Имя бота: {bot_info.first_name}")
    except Exception as e:
        logger.error(f"❌ Не удалось получить информацию о боте: {e}")
        return
    
    print("=" * 50)
    print("✅ БОТ УСПЕШНО ЗАПУЩЕН И РАБОТАЕТ")
    print("=" * 50)
    print("📊 Статус:")
    print(f"  • Healthcheck: http://0.0.0.0:8080/health")
    print(f"  • Бэкапы: {'✅ Включены' if os.getenv('B2_KEY_ID') else '❌ Выключены'}")
    print(f"  • Бот: @{bot_info.username}")
    print("=" * 50)
    
    # Основной цикл бота
    try:
        print("🔄 Запуск polling (основной цикл бота)...")
        await dp.start_polling(bot, drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Ошибка при работе бота: {e}")
        print(f"💥 Критическая ошибка: {e}")

# ==================== ЗАПУСК ПРИЛОЖЕНИЯ ====================
if __name__ == "__main__":
    print("🚀 Запуск приложения...")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Программа остановлена пользователем")
    except Exception as e:
        print(f"💥 Необработанная ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n👋 Завершение работы...")


