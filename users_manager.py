import json
import os

# Шлях до файлу, де зберігатимуться ID користувачів
USERS_FILE = "config/users.json"

def load_users() -> set:
    """Завантажує список chat_id з JSON-файлу у set() для швидкої роботи."""
    # Переконуємось, що папка config існує
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except Exception as e:
            print(f"⚠️ Помилка читання файлу користувачів: {e}")
            return set()
    return set()

def save_users(users_set: set) -> None:
    """Зберігає поточний set() назад у JSON-файл."""
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            # Перетворюємо set у звичайний список для збереження в JSON
            json.dump(list(users_set), f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ Помилка збереження файлу користувачів: {e}")

def add_user(chat_id: int, users_set: set) -> bool:
    """Додає нового користувача, якщо його ще немає. Повертає True, якщо користувач новий."""
    if chat_id not in users_set:
        users_set.add(chat_id)
        save_users(users_set)
        return True
    return False