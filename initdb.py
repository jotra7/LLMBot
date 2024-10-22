import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from config import POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT
import logging

logger = logging.getLogger(__name__)

def init_db():
    # First, connect to PostgreSQL server to create database if needed
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        # Check if the database exists
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (POSTGRES_DB,))
        exists = cur.fetchone()

        if not exists:
            print(f"Creating database: {POSTGRES_DB}")
            cur.execute(sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8'").format(
                sql.Identifier(POSTGRES_DB)))
            print(f"Database {POSTGRES_DB} created successfully.")
        else:
            print(f"Database {POSTGRES_DB} already exists.")

        cur.close()
        conn.close()

        # Now connect to the bot's database
        conn = psycopg2.connect(
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        # Create users table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            first_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_messages INTEGER DEFAULT 0,
            total_claude_messages INTEGER DEFAULT 0,
            total_gpt_messages INTEGER DEFAULT 0
        )
        """)

        # Create conversations table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            user_message TEXT,
            bot_response TEXT,
            model_type VARCHAR(50) DEFAULT 'claude',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create banned_users table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id BIGINT PRIMARY KEY,
            banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create command_usage table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS command_usage (
            command TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
        """)

        # Create user_generations table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_generations (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            prompt TEXT,
            generation_type VARCHAR(20),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create response_times table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS response_times (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            avg_duration FLOAT,
            min_duration FLOAT,
            max_duration FLOAT
        )
        """)

        # Create model_usage table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS model_usage (
            model TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
        """)

        # Create errors table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            error_type TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
        """)

        # Create user_data table for conversation histories and other user-specific data
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_data (
            user_id BIGINT,
            data_type VARCHAR(50),
            data JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, data_type)
        )
        """)

        # Create index for user_data
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_data_lookup 
        ON user_data(user_id, data_type)
        """)

        # Create connection_errors table for monitoring connection issues
        cur.execute("""
        CREATE TABLE IF NOT EXISTS connection_errors (
            id SERIAL PRIMARY KEY,
            error_type VARCHAR(100),
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        print("All tables created successfully.")

    except psycopg2.Error as e:
        print(f"An error occurred: {e}")
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize the database
    try:
        init_db()
        print("\nDatabase initialization complete.")
    except Exception as e:
        print(f"\nDatabase initialization failed: {e}")