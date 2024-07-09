import sqlite3
import json
from datetime import datetime

def get_db_connection():
    conn = sqlite3.connect('conversations.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS conversations
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER NOT NULL,
                     timestamp DATETIME NOT NULL,
                     user_message TEXT NOT NULL,
                     bot_response TEXT NOT NULL)''')
    conn.close()

def save_conversation(user_id, user_message, bot_response):
    conn = get_db_connection()
    conn.execute('INSERT INTO conversations (user_id, timestamp, user_message, bot_response) VALUES (?, ?, ?, ?)',
                 (user_id, datetime.now().isoformat(), user_message, json.dumps(bot_response)))
    conn.commit()
    conn.close()

def get_user_conversations(user_id, limit=10):
    conn = get_db_connection()
    conversations = conn.execute('SELECT * FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?',
                                 (user_id, limit)).fetchall()
    conn.close()
    return [dict(conv) for conv in conversations]