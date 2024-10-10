# database.py

import sqlite3
import logging
import asyncio
import requests
import psycopg2
import redis
import uuid
import json
from psycopg2 import sql
from datetime import timedelta
from typing import List, Dict, Optional
from config import (LEONARDO_API_BASE_URL, LEONARDO_AI_KEY, REDIS_HOST, REDIS_PORT, REDIS_DB,
                    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)
import openai

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
                # Create user_generations table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS user_generations
                (id SERIAL PRIMARY KEY,
                user_id BIGINT,
                prompt TEXT,
                generation_type VARCHAR(20),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
                """)

                # Create user_preferences table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id BIGINT PRIMARY KEY,
                    flux_model TEXT,
                    suno_model TEXT,
                    image_model TEXT,
                    openai_model TEXT,
                    leonardo_model TEXT,
                    replicate_model TEXT
                )
                """)

                # Create conversations table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    user_message TEXT,
                    bot_response TEXT,
                    model_type VARCHAR(20),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)

                # Create users table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    total_messages INT DEFAULT 0,
                    total_claude_messages INT DEFAULT 0,
                    total_gpt_messages INT DEFAULT 0,
                    last_interaction TIMESTAMP
                )
                """)
            conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

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

def get_user_generations_today(user_id: int, generation_type: str) -> int:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM user_generations WHERE user_id = %s AND generation_type = %s AND timestamp::date = CURRENT_DATE", (user_id, generation_type))
                count = cur.fetchone()[0]
                return count
    except Exception as e:
        logger.error(f"Error getting user generations: {e}")
        return 0

def save_user_generation(user_id: int, prompt: str, generation_type: str) -> None:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                generation_id = str(uuid.uuid4())
                cur.execute("INSERT INTO user_generations (user_id, prompt, generation_type, timestamp) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)", (user_id, prompt, generation_type))
            conn.commit()
        logger.info(f"Generation saved for user {user_id} of type {generation_type}")
    except Exception as e:
        logger.error(f"Error saving user generation: {e}")

def get_user_model(user_id: int, model_type: str) -> str:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {model_type} FROM user_preferences WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                if result:
                    return result[0]
                return None
    except Exception as e:
        logger.error(f"Database error in get_user_model: {e}")
        return None

def save_user_model(user_id: int, model_type: str, model_name: str) -> None:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO user_preferences (user_id, {model_type})
                    VALUES (%s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET {model_type} = excluded.{model_type}
                """, (user_id, model_name))
            conn.commit()
        logger.info(f"Model preference saved for user {user_id}: {model_type} = {model_name}")
    except Exception as e:
        logger.error(f"Database error in save_user_model: {e}")

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
    logger.info(f"Deleted session for user {user_id}")

# Functions for fetching models from external sources
async def fetch_gpt_models():
    try:
        models = await openai.Model.list()
        gpt_models = [
            model['id'] for model in models['data']
            if model['id'].startswith('gpt') and 'realtime' not in model['id'].lower()
        ]
        gpt_models.sort(reverse=True)
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

# Initialize the database
init_db()
