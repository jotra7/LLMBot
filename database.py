# database.py

import sqlite3
import logging
import asyncio
import requests
from config import LEONARDO_API_BASE_URL, LEONARDO_AI_KEY
import openai

logger = logging.getLogger(__name__)

DATABASE_PATH = 'database.db'

def get_db_connection():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return None

def get_user_generations_today(user_id: int, generation_type: str) -> int:
    conn = get_db_connection()
    if conn is None:
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM user_generations
            WHERE user_id = ? AND generation_type = ? AND DATE(timestamp) = DATE('now')
        """, (user_id, generation_type))
        count = cursor.fetchone()[0]
        return count
    except sqlite3.Error as e:
        logger.error(f"Database error in get_user_generations_today: {e}")
        return 0
    finally:
        conn.close()

def save_user_generation(user_id: int, prompt: str, generation_type: str) -> None:
    conn = get_db_connection()
    if conn is None:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_generations (user_id, prompt, generation_type, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        """, (user_id, prompt, generation_type))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in save_user_generation: {e}")
    finally:
        conn.close()

def get_user_model(user_id: int, model_type: str) -> str:
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {model_type} FROM user_preferences WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error in get_user_model: {e}")
        return None
    finally:
        conn.close()

def save_user_model(user_id: int, model_type: str, model_name: str) -> None:
    conn = get_db_connection()
    if conn is None:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO user_preferences (user_id, {model_type})
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET {model_type} = excluded.{model_type}
        """, (user_id, model_name))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in save_user_model: {e}")
    finally:
        conn.close()

async def fetch_gpt_models():
    try:
        models = await openai.Model.list()
        gpt_models = [
            model['id'] for model in models['data']
            if model['id'].startswith('gpt') and 'realtime' not in model['id'].lower()
        ]
        gpt_models.sort(reverse=True)  # Sort models in descending order
        return gpt_models
    except Exception as e:
        logger.error(f"Error fetching GPT models: {e}")
        return []

async def update_leonardo_model_cache(context=None):
    global leonardo_model_cache
    url = f"{LEONARDO_API_BASE_URL}/platformModels"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {LEONARDO_AI_KEY}"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        custom_models = data.get('custom_models', [])
        leonardo_model_cache = {model['id']: model['name'] for model in custom_models}
        logger.info(f"Leonardo model cache updated successfully. Models: {leonardo_model_cache}")
    except Exception as e:
        logger.error(f"Error updating Leonardo model cache: {str(e)}")

# Create the user_preferences table if it doesn't exist
def create_user_preferences_table():
    conn = get_db_connection()
    if conn is None:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                flux_model TEXT,
                suno_model TEXT,
                image_model TEXT,
                openai_model TEXT,
                leonardo_model TEXT,
                replicate_model TEXT
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in create_user_preferences_table: {e}")
    finally:
        conn.close()

# Initialize the user_preferences table
create_user_preferences_table()