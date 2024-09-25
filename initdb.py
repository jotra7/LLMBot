import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from config import POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT

# Connect to PostgreSQL server
conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password=POSTGRES_PASSWORD,  # Assuming the superuser password is the same as the app user password
    host=POSTGRES_HOST,
    port=POSTGRES_PORT
)

conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

# Create database
cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(POSTGRES_DB)))

# Create user
cur.execute(sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
    sql.Identifier(POSTGRES_USER), sql.Literal(POSTGRES_PASSWORD)
))

# Grant privileges
cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
    sql.Identifier(POSTGRES_DB), sql.Identifier(POSTGRES_USER)
))

# Close connection to postgres database
cur.close()
conn.close()

# Connect to the new database
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
CREATE TABLE IF NOT EXISTS banned_users (
    user_id BIGINT PRIMARY KEY,
    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Grant privileges on the tables
cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON TABLE conversations TO {}").format(
    sql.Identifier(POSTGRES_USER)
))

cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON TABLE users TO {}").format(
    sql.Identifier(POSTGRES_USER)
))

cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON TABLE banned_users TO {}").format(
    sql.Identifier(POSTGRES_USER)
))

# Grant privileges on the sequences (for the SERIAL columns)
cur.execute(sql.SQL("GRANT USAGE, SELECT ON SEQUENCE conversations_id_seq TO {}").format(
    sql.Identifier(POSTGRES_USER)
))

print("Database, user, and tables created successfully.")

# Close the connection
cur.close()
conn.close()