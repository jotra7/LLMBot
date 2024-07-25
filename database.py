import sqlite3
from typing import List, Dict, Optional

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations
    (id INTEGER PRIMARY KEY, user_id INTEGER, user_message TEXT, bot_response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS banned_users
    (user_id INTEGER PRIMARY KEY, banned_at DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()

def save_conversation(user_id: int, user_message: str, bot_response: str):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO conversations (user_id, user_message, bot_response) VALUES (?, ?, ?)',
                   (user_id, user_message, bot_response))
    conn.commit()
    conn.close()

def get_user_conversations(user_id: int, limit: int = 5) -> List[Dict[str, str]]:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_message, bot_response FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?',
                   (user_id, limit))
    conversations = [{'user_message': row[0], 'bot_response': row[1]} for row in cursor.fetchall()]
    conn.close()
    return conversations

def get_all_users() -> List[int]:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM conversations")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def ban_user(user_id: int) -> bool:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO banned_users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # User is already banned
        conn.close()
        return False

def unban_user(user_id: int) -> bool:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
    if cursor.rowcount > 0:
        conn.commit()
        conn.close()
        return True
    else:
        conn.close()
        return False

def is_user_banned(user_id: int) -> bool:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result

# You might want to add more database functions as needed