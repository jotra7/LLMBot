import redis
import psycopg2
from psycopg2 import sql
import json
from datetime import timedelta
import logging
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
                cur.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS conversations
                (id SERIAL PRIMARY KEY, 
                user_id BIGINT, 
                user_message TEXT, 
                bot_response TEXT, 
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
                '''))
            conn.commit()
        logger.info("Database initialized successfully")
    except psycopg2.errors.InsufficientPrivilege as e:
        logger.error(f"Insufficient privileges to create table: {e}")
        logger.error("Please grant necessary permissions to the database user.")
        logger.error("Run the following SQL commands as a superuser:")
        logger.error(f"GRANT ALL PRIVILEGES ON DATABASE {POSTGRES_DB} TO {POSTGRES_USER};")
        logger.error(f"GRANT ALL PRIVILEGES ON SCHEMA public TO {POSTGRES_USER};")
        logger.error(f"ALTER USER {POSTGRES_USER} WITH CREATEDB;")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

def save_conversation(user_id: int, user_message: str, bot_response: str):
    try:
        # Save to Redis cache
        conversation = f"{user_message}|{bot_response}"
        redis_client.lpush(f"user:{user_id}:conversations", conversation)
        redis_client.ltrim(f"user:{user_id}:conversations", 0, 99)  # Keep last 100 messages

        # Save to PostgreSQL
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO conversations (user_id, user_message, bot_response) VALUES (%s, %s, %s)",
                    (user_id, user_message, bot_response)
                )
            conn.commit()
        logger.info(f"Conversation saved for user {user_id}")
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")

def get_recent_conversations(user_id: int, limit: int = 10):
    conversations = redis_client.lrange(f"user:{user_id}:conversations", 0, limit - 1)
    return [conv.decode().split('|') for conv in conversations]

def get_old_conversations(user_id: int, limit: int = 10):
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_message, bot_response FROM conversations WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s",
                (user_id, limit)
            )
            return cur.fetchall()

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

def save_partial_response(user_id: int, message_id: str, partial_response: str):
    key = f"user:{user_id}:partial_response:{message_id}"
    redis_client.setex(key, timedelta(minutes=5), partial_response)

def get_partial_response(user_id: int, message_id: str) -> str:
    key = f"user:{user_id}:partial_response:{message_id}"
    return redis_client.get(key) or ""

def get_all_users():
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT user_id FROM conversations")
            return [row[0] for row in cur.fetchall()]

def delete_user_session(user_id: int):
    session_key = f"user:{user_id}:session"
    redis_client.delete(session_key)
    logger.info(f"Deleted session for user {user_id}")