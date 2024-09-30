import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from config import POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT

# Connect to PostgreSQL server
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
        cur.execute(sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8'").format(sql.Identifier(POSTGRES_DB)))
        print(f"Database {POSTGRES_DB} created successfully.")
    else:
        print(f"Database {POSTGRES_DB} already exists.")

    # Close the connection to the 'postgres' database
    cur.close()
    conn.close()

    # Connect to the bot's database
    conn = psycopg2.connect(
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Create tables
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        user_message TEXT,
        bot_response TEXT,
        model_type VARCHAR(10) DEFAULT 'claude',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS banned_users (
        user_id BIGINT PRIMARY KEY,
        banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS command_usage (
        command TEXT PRIMARY KEY,
        count INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_generations (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        prompt TEXT,
        generation_type VARCHAR(20),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS response_times (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        avg_duration FLOAT,
        min_duration FLOAT,
        max_duration FLOAT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS model_usage (
        model TEXT PRIMARY KEY,
        count INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS errors (
        error_type TEXT PRIMARY KEY,
        count INTEGER DEFAULT 0
    )
    """)

    print("Tables created successfully.")

except psycopg2.Error as e:
    print(f"An error occurred: {e}")
finally:
    if cur:
        cur.close()
    if conn:
        conn.close()

print("\nDatabase setup complete.")