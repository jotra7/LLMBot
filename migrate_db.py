import psycopg2
import logging
from config import (POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
                    POSTGRES_USER, POSTGRES_PASSWORD)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_postgres_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

def migrate_db():
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                # Create users table if it doesn't exist
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users
                (id BIGINT PRIMARY KEY,
                first_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
                """)
                logger.info("Created users table if it didn't exist")

                # Check if the model_type column exists in conversations table
                cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='conversations' AND column_name='model_type'
                """)
                if not cur.fetchone():
                    # Create a new table with the desired structure
                    cur.execute("""
                    CREATE TABLE conversations_new
                    (id SERIAL PRIMARY KEY, 
                    user_id BIGINT, 
                    user_message TEXT, 
                    bot_response TEXT, 
                    model_type VARCHAR(10) DEFAULT 'claude',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
                    """)
                    
                    # Copy data from the old table to the new one
                    cur.execute("""
                    INSERT INTO conversations_new (id, user_id, user_message, bot_response, timestamp)
                    SELECT id, user_id, user_message, bot_response, timestamp
                    FROM conversations
                    """)
                    
                    # Rename the tables
                    cur.execute("ALTER TABLE conversations RENAME TO conversations_old")
                    cur.execute("ALTER TABLE conversations_new RENAME TO conversations")
                    
                    # Drop the old table
                    cur.execute("DROP TABLE conversations_old")
                    
                    logger.info("Added model_type column to conversations table")
                else:
                    logger.info("model_type column already exists in conversations table")

            conn.commit()
        logger.info("Database migration completed successfully")
    except Exception as e:
        logger.error(f"Error during database migration: {e}")
        raise

if __name__ == "__main__":
    migrate_db()