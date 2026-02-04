import aiosqlite
import json
import hashlib
import time
from datetime import datetime

DB_PATH = "bot_database.db"

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'user',
            credits INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Таблица постов
        await db.execute('''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publisher_id INTEGER,
            post_name TEXT,
            content_type TEXT,
            content_text TEXT,
            content_file_id TEXT,
            channels TEXT,
            unique_code TEXT UNIQUE,
            views INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Таблица подписок
        await db.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id TEXT,
            subscribed BOOLEAN DEFAULT 0,
            UNIQUE(user_id, channel_id)
        )''')
        
        # Таблица платежей
        await db.execute('''CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            credits INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS post_updates_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            user_id INTEGER,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            UNIQUE(post_id, user_id)
        )''')
        
        await db.commit()

# Функции для работы с пользователями
async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name)
        )
        await db.commit()

async def update_user_role(user_id: int, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET role = ? WHERE user_id = ?",
            (role, user_id)
        )
        await db.commit()

async def add_credits(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET credits = credits + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

# Функции для работы с постами
async def create_post(publisher_id: int, post_name: str, content_type: str, content_text: str, 
                     content_file_id: str, channels: list) -> str:
    """Создать пост с названием"""
    unique_code = hashlib.md5(f"{publisher_id}{time.time()}".encode()).hexdigest()[:10]
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT INTO posts 
            (publisher_id, post_name, content_type, content_text, content_file_id, channels, unique_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)''', (
            publisher_id, 
            post_name,
            content_type, 
            content_text, 
            content_file_id,
            json.dumps(channels),
            unique_code
        ))
        await db.commit()
    
    return unique_code

async def subscribe_to_post_updates(user_id: int, post_id: int):
    """Подписать пользователя на обновления поста"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute('''INSERT OR IGNORE INTO post_updates_subscriptions 
                (post_id, user_id) VALUES (?, ?)''', 
                (post_id, user_id))
            await db.commit()
            return True
        except:
            return False

async def unsubscribe_from_post_updates(user_id: int, post_id: int):
    """Отписать пользователя от обновлений поста"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''DELETE FROM post_updates_subscriptions 
            WHERE post_id = ? AND user_id = ?''', 
            (post_id, user_id))
        await db.commit()
        return True

async def is_subscribed_to_updates(user_id: int, post_id: int) -> bool:
    """Проверить подписку на обновления"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''SELECT 1 FROM post_updates_subscriptions 
            WHERE post_id = ? AND user_id = ?''', 
            (post_id, user_id)) as cursor:
            return await cursor.fetchone() is not None

async def get_post_subscribers(post_id: int):
    """Получить всех подписчиков на обновления поста"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''SELECT user_id FROM post_updates_subscriptions 
            WHERE post_id = ?''', (post_id,)) as cursor:
            rows = await cursor.fetchall()
            return [row['user_id'] for row in rows]

async def update_post_content(post_id: int, content_type: str = None, 
                             content_text: str = None, content_file_id: str = None):
    """Обновить контент поста"""
    updates = []
    params = []
    
    if content_type:
        updates.append("content_type = ?")
        params.append(content_type)
    
    if content_text is not None:
        updates.append("content_text = ?")
        params.append(content_text)
    
    if content_file_id:
        updates.append("content_file_id = ?")
        params.append(content_file_id)
    
    if not updates:
        return False
    
    params.append(post_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'''UPDATE posts SET {', '.join(updates)} 
            WHERE id = ?''', params)
        await db.commit()
        return True
    
async def get_user_posts_with_stats(user_id: int):
    """Получить посты пользователя со статистикой"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''SELECT 
            p.*,
            (SELECT COUNT(*) FROM post_updates_subscriptions WHERE post_id = p.id) as subscribers_count
            FROM posts p 
            WHERE p.publisher_id = ? 
            ORDER BY p.created_at DESC''', (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_post_by_id(post_id: int):
    """Получить пост по ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_post_by_unique_code(unique_code: str):
    """Получить пост по уникальному коду"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM posts WHERE unique_code = ?", (unique_code,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_post(unique_code: str):
    """Алиас для совместимости"""
    return await get_post_by_unique_code(unique_code)

async def increment_post_views(post_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE posts SET views = views + 1 WHERE id = ?",
            (post_id,)
        )
        await db.commit()

async def get_user_posts(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM posts WHERE publisher_id = ? ORDER BY created_at DESC", 
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def toggle_post_status(post_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_active FROM posts WHERE id = ?", (post_id,)) as cursor:
            current = await cursor.fetchone()
            new_status = 0 if current[0] else 1
        
        await db.execute(
            "UPDATE posts SET is_active = ? WHERE id = ?",
            (new_status, post_id)
        )
        await db.commit()
        return new_status

# Функции для работы с подписками
async def check_subscription(user_id: int, channel_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT subscribed FROM subscriptions WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False

async def update_subscription(user_id: int, channel_id: str, subscribed: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT OR REPLACE INTO subscriptions (user_id, channel_id, subscribed)
            VALUES (?, ?, ?)''', (user_id, channel_id, 1 if subscribed else 0))
        await db.commit()

# Функции для работы с платежами
async def create_payment(user_id: int, amount: float, credits: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments (user_id, amount, credits) VALUES (?, ?, ?)",
            (user_id, amount, credits)
        )
        await db.commit()
        return cursor.lastrowid

async def update_payment_status(payment_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = ? WHERE id = ?",
            (status, payment_id)
        )
        await db.commit()

# Статистика
async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM posts") as cursor:
            total_posts = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT SUM(views) FROM posts") as cursor:
            total_views = (await cursor.fetchone())[0] or 0
        
        return {
            "total_users": total_users,
            "total_posts": total_posts,
            "total_views": total_views
        }

async def get_all_users():
    """Получить всех пользователей"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_all_posts():
    """Получить все посты"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT p.*, u.username 
               FROM posts p 
               LEFT JOIN users u ON p.publisher_id = u.user_id 
               ORDER BY p.created_at DESC"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_user_by_username(username: str):
    """Найти пользователя по username"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", 
            (username,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None