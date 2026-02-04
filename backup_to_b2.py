#!/usr/bin/env python3
"""
Скрипт бэкапа БД в Backblaze B2.
Запускается каждый час, сохраняет 24 бэкапа в облаке.
"""
import os
import sqlite3
import gzip
import hashlib
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
import logging
import schedule
import time
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.WARNING,  # Меньше шума - только WARNING и ERROR
    format='%(asctime)s - [Backup] - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class B2Backup:
    def __init__(self):
        # Конфигурация Backblaze B2
        self.b2_key_id = os.getenv('B2_KEY_ID')
        self.b2_app_key = os.getenv('B2_APPLICATION_KEY')  # Исправлено имя переменной!
        self.b2_bucket = os.getenv('B2_BUCKET', 'referals-content')
        self.endpoint_url = 'https://s3.us-east-005.backblazeb2.com'
        
        # Локальные пути
        self.db_path = os.getenv('DB_PATH', 'bot_database.db')
        self.local_backup_dir = '/tmp/backups'
        
        # Инициализация S3 клиента
        self.s3_client = None
        self.init_b2_client()
        
    def init_b2_client(self):
        """Инициализировать клиент Backblaze B2"""
        if not self.b2_key_id or not self.b2_app_key:
            logger.error("❌ B2_KEY_ID или B2_APPLICATION_KEY не установлены!")
            return False
            
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.b2_key_id,
                aws_secret_access_key=self.b2_app_key
            )
            logger.info("✅ B2 клиент инициализирован")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации B2: {e}")
            return False
    
    def create_local_backup(self):
        """Создать локальную копию БД"""
        try:
            # Создаем директорию для бэкапов
            os.makedirs(self.local_backup_dir, exist_ok=True)
            
            # Генерируем имя файла
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'bot_backup_{timestamp}.db.gz'
            local_path = os.path.join(self.local_backup_dir, backup_filename)
            
            # Проверяем что исходная БД существует
            if not os.path.exists(self.db_path):
                logger.error(f"❌ Исходная БД не найдена: {self.db_path}")
                return None
            
            # Создаем сжатый бэкап
            with open(self.db_path, 'rb') as f_in:
                with gzip.open(local_path, 'wb') as f_out:
                    f_out.write(f_in.read())
            
            # Проверяем размер
            file_size = os.path.getsize(local_path) / 1024  # в KB
            logger.info(f"📦 Локальный бэкап создан: {backup_filename} ({file_size:.1f} KB)")
            
            return {
                'local_path': local_path,
                'filename': backup_filename,
                'size': file_size,
                'timestamp': timestamp
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания локального бэкапа: {e}")
            return None
    
    def upload_to_b2(self, backup_info):
        """Загрузить бэкап в Backblaze B2"""
        if not self.s3_client:
            logger.error("❌ B2 клиент не инициализирован")
            return False
        
        try:
            local_path = backup_info['local_path']
            filename = backup_info['filename']
            
            # Загружаем файл
            self.s3_client.upload_file(
                Filename=local_path,
                Bucket=self.b2_bucket,
                Key=filename,
                ExtraArgs={
                    'ContentType': 'application/gzip',
                    'ContentEncoding': 'gzip'
                }
            )
            
            logger.info(f"☁️  Бэкап загружен в B2: {filename}")
            return True
            
        except ClientError as e:
            logger.error(f"❌ Ошибка загрузки в B2: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка: {e}")
            return False
    
    def cleanup_old_backups(self, keep_hours=24):
        """Удалить старые бэкапы из B2 (оставить только keep_hours)"""
        if not self.s3_client:
            return False
        
        try:
            # Получаем список всех бэкапов
            response = self.s3_client.list_objects_v2(Bucket=self.b2_bucket)
            
            if 'Contents' not in response:
                logger.info("ℹ️  Нет бэкапов для очистки")
                return True
            
            # Сортируем по дате
            backups = sorted(response['Contents'], key=lambda x: x['LastModified'])
            
            # Определяем cutoff время
            cutoff_time = datetime.now() - timedelta(hours=keep_hours)
            
            deleted_count = 0
            for obj in backups:
                if obj['LastModified'].replace(tzinfo=None) < cutoff_time:
                    # Удаляем старый бэкап
                    self.s3_client.delete_object(
                        Bucket=self.b2_bucket,
                        Key=obj['Key']
                    )
                    logger.info(f"🗑️  Удален старый бэкап: {obj['Key']}")
                    deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"🧹 Удалено {deleted_count} старых бэкапов")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки старых бэкапов: {e}")
            return False
    
    def cleanup_local_backups(self):
        """Очистить локальные временные файлы"""
        try:
            import shutil
            if os.path.exists(self.local_backup_dir):
                shutil.rmtree(self.local_backup_dir)
                logger.info("🧹 Локальные временные файлы удалены")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка очистки локальных файлов: {e}")
            return False
    
    def perform_backup(self):
        """Выполнить полный цикл бэкапа"""
        logger.info("=" * 50)
        logger.info("🔄 Начинаю процесс бэкапа...")
        
        # 1. Создаем локальный бэкап
        backup_info = self.create_local_backup()
        if not backup_info:
            logger.error("❌ Не удалось создать локальный бэкап")
            return False
        
        # 2. Загружаем в B2
        if not self.upload_to_b2(backup_info):
            logger.error("❌ Не удалось загрузить бэкап в B2")
            return False
        
        # 3. Удаляем старые бэкапы в B2 (оставляем 24 часа)
        self.cleanup_old_backups(keep_hours=24)
        
        # 4. Удаляем локальные временные файлы
        self.cleanup_local_backups()
        
        logger.info("✅ Процесс бэкапа завершен успешно!")
        logger.info("=" * 50)
        return True
    
    def list_backups(self):
        """Показать список доступных бэкапов"""
        if not self.s3_client:
            return []
        
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.b2_bucket)
            
            if 'Contents' not in response:
                logger.info("📭 Бэкапы не найдены")
                return []
            
            backups = []
            for obj in response['Contents']:
                backups.append({
                    'name': obj['Key'],
                    'size': obj['Size'] / 1024,  # KB
                    'last_modified': obj['LastModified']
                })
            
            # Сортируем по дате (новые первые)
            backups.sort(key=lambda x: x['last_modified'], reverse=True)
            
            logger.info("📋 Доступные бэкапы:")
            for i, backup in enumerate(backups[:10]):  # показываем 10 последних
                logger.info(f"  {i+1}. {backup['name']} ({backup['size']:.1f} KB)")
            
            if len(backups) > 10:
                logger.info(f"  ... и еще {len(backups) - 10} бэкапов")
            
            return backups
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка бэкапов: {e}")
            return []

def backup_job():
    """Задача для планировщика"""
    backup = B2Backup()
    return backup.perform_backup()

def schedule_backups():
    """Запустить планировщик бэкапов (ИСПРАВЛЕННАЯ ВЕРСИЯ)"""
    logger.info("⏰ Настройка расписания бэкапов...")
    
    # Создаем бэкап сразу при запуске (только один раз!)
    logger.info("🚀 Выполняю начальный бэкап...")
    backup_job()
    
    # Настраиваем расписание (правильно!)
    schedule.every(1).hours.do(backup_job)  # КАЖДЫЙ ЧАС, не каждую секунду!
    
    logger.info("✅ Расписание установлено: бэкап каждый час")
    logger.info(f"⏰ Следующий бэкап в: {schedule.next_run()}")
    
    # Бесконечный цикл (с правильной проверкой)
    while True:
        try:
            schedule.run_pending()  # проверяет, нужно ли запускать задачу
            time.sleep(60)  # ждем 60 секунд до следующей проверки
        except KeyboardInterrupt:
            logger.info("🛑 Остановка планировщика бэкапов...")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике: {e}")
            time.sleep(300)  # ждем 5 минут при ошибке

def main():
    """Точка входа"""
    # Проверяем переменные окружения
    required_vars = ['B2_KEY_ID', 'B2_APPLICATION_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Отсутствуют переменные окружения: {', '.join(missing_vars)}")
        logger.error("ℹ️  Добавьте их в Railway Variables:")
        logger.error("   - B2_KEY_ID: Application Key ID из Backblaze B2")
        logger.error("   - B2_APPLICATION_KEY: Application Key из Backblaze B2")
        logger.error("   - B2_BUCKET: referals-content (опционально)")
        sys.exit(1)
    
    # Запускаем планировщик
    schedule_backups()

if __name__ == "__main__":
    main()
