#!/usr/bin/env python3
"""
ПРОСТОЙ бэкап - один раз в час.
"""
import os
import time
from datetime import datetime
import sqlite3
import gzip
import boto3
import sys

def log(msg):
    """Минимальное логирование"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def backup():
    """Выполнить один бэкап"""
    try:
        # Конфигурация
        key_id = os.getenv('B2_KEY_ID')
        app_key = os.getenv('B2_APPLICATION_KEY')
        bucket = os.getenv('B2_BUCKET', 'referals-content')
        db_path = os.getenv('DB_PATH', 'bot_database.db')
        
        if not key_id or not app_key:
            log("⚠️  Бэкапы отключены (нет ключей)")
            return False
        
        # Подключаемся к B2
        s3 = boto3.client(
            's3',
            endpoint_url='https://s3.us-east-005.backblazeb2.com',
            aws_access_key_id=key_id,
            aws_secret_access_key=app_key
        )
        
        # Имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'backup_{timestamp}.db.gz'
        
        # Создаем сжатый бэкап
        with open(db_path, 'rb') as f_in:
            with gzip.open(f'/tmp/{backup_name}', 'wb') as f_out:
                f_out.write(f_in.read())
        
        # Загружаем в B2
        s3.upload_file(
            Filename=f'/tmp/{backup_name}',
            Bucket=bucket,
            Key=backup_name,
            ExtraArgs={'ContentType': 'application/gzip'}
        )
        
        # Удаляем временный файл
        os.remove(f'/tmp/{backup_name}')
        
        log(f"📦 Бэкап создан: {backup_name}")
        return True
        
    except Exception as e:
        log(f"❌ Ошибка: {str(e)[:50]}")
        return False

def cleanup_old(s3, bucket):
    """Очистить старые бэкапы (оставить 24)"""
    try:
        response = s3.list_objects_v2(Bucket=bucket)
        if 'Contents' not in response:
            return
        
        # Фильтруем и сортируем бэкапы
        backups = []
        for obj in response['Contents']:
            if obj['Key'].startswith('backup_'):
                backups.append({
                    'key': obj['Key'],
                    'date': obj['LastModified']
                })
        
        backups.sort(key=lambda x: x['date'])
        
        # Удаляем старые (оставляем 24)
        if len(backups) > 24:
            for backup in backups[:-24]:
                s3.delete_object(Bucket=bucket, Key=backup['key'])
            log(f"🧹 Удалено {len(backups)-24} старых бэкапов")
            
    except:
        pass  # Тихий fail

def main():
    """Основной цикл"""
    log("⏰ Служба бэкапов запущена (раз в час)")
    
    # Первый бэкап сразу
    backup()
    
    # Основной цикл
    last_backup = time.time()
    
    while True:
        try:
            current_time = time.time()
            
            # Проверяем, прошёл ли час (3600 секунд)
            if current_time - last_backup >= 3600:
                backup()
                last_backup = current_time
            
            # Ждем 5 минут до следующей проверки
            time.sleep(300)
            
        except KeyboardInterrupt:
            log("🛑 Остановка")
            break
        except Exception as e:
            log(f"💥 Ошибка: {e}")
            time.sleep(600)

if __name__ == "__main__":
    main()
