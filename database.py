import psycopg2
import datetime
from psycopg2 import sql
import redis
import json
from datetime import timedelta
import logging
from typing import List, Dict, Optional
from config import (REDIS_HOST, REDIS_PORT, REDIS_DB,
                    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
                    POSTGRES_USER, POSTGRES_PASSWORD)

logger = logging.getLogger(__name__)

# Redis setup
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

# PostgreSQL setup
def get_postgres_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

def init_db():
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                # ... (existing table creations)

                # Create the user_generations table if it doesn't exist
                cur.execute("""
                CREATE TABLE IF NOT EXISTS user_generations
                (id SERIAL PRIMARY KEY,
                user_id BIGINT,
                prompt TEXT,
                generation_type VARCHAR(20),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
                """)
            conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

def save_user_generation(user_id: int, prompt: str, generation_type: str):
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO user_generations (user_id, prompt, generation_type) VALUES (%s, %s, %s)",
                    (user_id, prompt, generation_type)
                )
            conn.commit()
        logger.info(f"Generation saved for user {user_id} of type {generation_type}")
    except Exception as e:
        logger.error(f"Error saving user generation: {e}")

def get_user_generations_today(user_id: int, generation_type: str = None) -> int:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                if generation_type:
                    cur.execute(
                        "SELECT COUNT(*) FROM user_generations WHERE user_id = %s AND generation_type = %s AND timestamp >= CURRENT_DATE",
                        (user_id, generation_type)
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM user_generations WHERE user_id = %s AND timestamp >= CURRENT_DATE",
                        (user_id,)
                    )
                return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"Error getting user generations: {e}")
        return 0


def save_conversation(user_id: int, user_message: str, bot_response: str, model_type: str = 'claude'):
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                # Insert into conversations table
                cur.execute(
                    "INSERT INTO conversations (user_id, user_message, bot_response, model_type) VALUES (%s, %s, %s, %s)",
                    (user_id, user_message, bot_response, model_type)
                )
                # Update or insert into users table
                cur.execute("""
                    INSERT INTO users (id, total_messages, total_claude_messages, total_gpt_messages, last_interaction) 
                    VALUES (%s, 1, CASE WHEN %s = 'claude' THEN 1 ELSE 0 END, CASE WHEN %s = 'gpt' THEN 1 ELSE 0 END, NOW())
                    ON CONFLICT (id) DO UPDATE SET 
                    total_messages = users.total_messages + 1,
                    total_claude_messages = users.total_claude_messages + CASE WHEN %s = 'claude' THEN 1 ELSE 0 END,
                    total_gpt_messages = users.total_gpt_messages + CASE WHEN %s = 'gpt' THEN 1 ELSE 0 END,
                    last_interaction = NOW()
                """, (user_id, model_type, model_type, model_type, model_type))
            conn.commit()
        logger.info(f"Conversation saved and counts updated for user {user_id} using {model_type} model")
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")

def get_user_conversations(user_id: int, limit: int = 5, model_type: Optional[str] = None) -> List[Dict[str, str]]:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            if model_type:
                cur.execute(
                    "SELECT user_message, bot_response FROM conversations WHERE user_id = %s AND model_type = %s ORDER BY timestamp DESC LIMIT %s",
                    (user_id, model_type, limit)
                )
            else:
                cur.execute(
                    "SELECT user_message, bot_response FROM conversations WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s",
                    (user_id, limit)
                )
            return [{'user_message': row[0], 'bot_response': row[1]} for row in cur.fetchall()]

def get_all_users() -> List[int]:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users")
            return [row[0] for row in cur.fetchall()]

def get_user_count() -> int:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            return cur.fetchone()[0]

def ban_user(user_id: int) -> bool:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO banned_users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING', (user_id,))
                affected = cur.rowcount
            conn.commit()
        return affected > 0
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        return False

def unban_user(user_id: int) -> bool:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM banned_users WHERE user_id = %s', (user_id,))
                affected = cur.rowcount
            conn.commit()
        return affected > 0
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        return False

def is_user_banned(user_id: int) -> bool:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM banned_users WHERE user_id = %s', (user_id,))
            return cur.fetchone() is not None

def clear_user_conversations(user_id: int):
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE user_id = %s",
                    (user_id,)
                )
            conn.commit()
        logger.info(f"Cleared all conversations for user {user_id}")
    except Exception as e:
        logger.error(f"Error clearing conversations for user {user_id}: {e}")


# Redis operations
def save_user_session(user_id: int, session_data: dict):
    session_key = f"user:{user_id}:session"
    redis_client.setex(session_key, timedelta(hours=1), json.dumps(session_data))

def get_user_session(user_id: int) -> dict:
    session_key = f"user:{user_id}:session"
    session_data = redis_client.get(session_key)
    if session_data:
        return json.loads(session_data)
    return {}

def update_user_session(user_id: int, new_data: dict):
    session = get_user_session(user_id)
    session.update(new_data)
    save_user_session(user_id, session)

def delete_user_session(user_id: int):
    session_key = f"user:{user_id}:session"
    redis_client.delete(session_key)
    clear_user_conversations(user_id)
    logger.info(f"Deleted session and cleared conversations for user {user_id}")

def save_partial_response(user_id: int, message_id: str, partial_response: str):
    key = f"user:{user_id}:partial_response:{message_id}"
    redis_client.setex(key, timedelta(minutes=5), partial_response)

def get_partial_response(user_id: int, message_id: str) -> str:
    key = f"user:{user_id}:partial_response:{message_id}"
    return redis_client.get(key) or ""

    
def get_user_stats() -> Dict[str, int]:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                query = """
                SELECT 
                    COUNT(DISTINCT id) as total_users,
                    COALESCE(SUM(total_messages), 0) as total_messages,
                    COALESCE(SUM(total_claude_messages), 0) as total_claude_messages,
                    COALESCE(SUM(total_gpt_messages), 0) as total_gpt_messages,
                    COUNT(DISTINCT CASE WHEN last_interaction > NOW() - INTERVAL '24 hours' THEN id END) as active_users_24h
                FROM users
                """
                cur.execute(query)
                result = cur.fetchone()
                stats = {
                    "total_users": result[0],
                    "total_messages": result[1],
                    "total_claude_messages": result[2],
                    "total_gpt_messages": result[3],
                    "active_users_24h": result[4]
                }
        logger.info(f"Retrieved user stats: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Error retrieving user stats: {e}")
        return {
            "total_users": 0,
            "total_messages": 0,
            "total_claude_messages": 0,
            "total_gpt_messages": 0,
            "active_users_24h": 0
        }

def get_active_users(days: int = 7) -> List[Dict[str, any]]:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, first_interaction, last_interaction, 
                           total_messages, total_claude_messages, total_gpt_messages
                    FROM users
                    WHERE last_interaction > NOW() - (%s || ' days')::INTERVAL
                    ORDER BY last_interaction DESC
                """, (str(days),))
                active_users = [
                    {
                        "id": row[0],
                        "first_interaction": row[1],
                        "last_interaction": row[2],
                        "total_messages": row[3],
                        "total_claude_messages": row[4],
                        "total_gpt_messages": row[5]
                    }
                    for row in cur.fetchall()
                ]
        logger.info(f"Retrieved {len(active_users)} active users in the last {days} days")
        return active_users
    except Exception as e:
        logger.error(f"Error retrieving active users: {e}")
        return []    
    
def save_user_generation(user_id: int, prompt: str, generation_id: str):
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_generations (user_id, prompt, generation_id, timestamp) VALUES (%s, %s, %s, %s)",
                (user_id, prompt, generation_id, datetime.datetime.now())
            )
        conn.commit()

def get_user_generations_today(user_id: int,  generation_id: str) -> int:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM user_generations WHERE user_id = %s AND timestamp >= %s",
                (user_id, datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
            )
            return cur.fetchone()[0]