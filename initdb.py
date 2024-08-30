import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Database configuration
DB_NAME = "llmbot1"
DB_USER = "llmbot"
DB_PASSWORD = "Stipulations.States.Sufficient.Photograph"  # Replace with a secure password
DB_HOST = "localhost"
DB_PORT = "5432"

# Connect to PostgreSQL server
conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="Stipulations.States.Sufficient.Photograph",  # Replace with your PostgreSQL superuser password
    host=DB_HOST,
    port=DB_PORT
)

conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

# Create database
cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))

# Create user
cur.execute(sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
    sql.Identifier(DB_USER), sql.Literal(DB_PASSWORD)
))

# Grant privileges
cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
    sql.Identifier(DB_NAME), sql.Identifier(DB_USER)
))

# Close connection to postgres database
cur.close()
conn.close()

# Connect to the new database
conn = psycopg2.connect(
    dbname=DB_NAME,
    user="postgres",
    password="your_postgres_password",  # Replace with your PostgreSQL superuser password
    host=DB_HOST,
    port=DB_PORT
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
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Grant privileges on the table
cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON TABLE conversations TO {}").format(
    sql.Identifier(DB_USER)
))

# Grant privileges on the sequence (for the SERIAL column)
cur.execute(sql.SQL("GRANT USAGE, SELECT ON SEQUENCE conversations_id_seq TO {}").format(
    sql.Identifier(DB_USER)
))

print("Database, user, and tables created successfully.")

# Close the connection
cur.close()
conn.close()