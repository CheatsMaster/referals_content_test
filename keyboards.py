from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def publisher_main():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📝 Создать пост"))
    builder.add(KeyboardButton(text="📊 Мои посты"))
    builder.add(KeyboardButton(text="💰 Баланс"))
    builder.add(KeyboardButton(text="❓ Помощь"))
    return builder.as_markup(resize_keyboard=True)

def main_menu():
    """Главное меню пользователя"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать пост"), KeyboardButton(text="📊 Мои посты")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="🎭 Статус")],
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    """Меню администратора"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Пользователи"), KeyboardButton(text="📝 Посты")],
            [KeyboardButton(text="💰 Кредиты"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )