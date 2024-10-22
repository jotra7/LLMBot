import time
from collections import defaultdict
import psycopg2
import statistics
import logging
from telegram.ext import ContextTypes
from database import get_postgres_connection

logger = logging.getLogger(__name__)

# Initialize performance tracking
performance_data = {
    'response_times': [],
    'model_usage': defaultdict(int),
    'command_usage': defaultdict(int),
    'errors': defaultdict(int)
}

def init_performance_db():
    conn = get_postgres_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS response_times (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        avg_duration FLOAT,
        min_duration FLOAT,
        max_duration FLOAT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS model_usage (
        model TEXT PRIMARY KEY,
        count INTEGER
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS command_usage (
        command TEXT PRIMARY KEY,
        count INTEGER
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS errors (
        error_type TEXT PRIMARY KEY,
        count INTEGER
    )
    ''')

    conn.commit()
    conn.close()
    logger.info("Performance database initialized")

def record_response_time(duration):
    performance_data['response_times'].append(duration)
    logger.debug(f"Recorded response time: {duration}")

def record_model_usage(model):
    performance_data['model_usage'][model] += 1
    logger.debug(f"Recorded model usage: {model}")

def record_command_usage(command, user_id=None, username=None):
    performance_data['command_usage'][command] += 1
    
    if user_id and username:
        logger.debug(f"Recorded command usage: {command} by user {username} (ID: {user_id})")
    elif user_id:
        logger.debug(f"Recorded command usage: {command} by user with ID: {user_id} (username not available)")
    elif username:
        logger.debug(f"Recorded command usage: {command} by user {username} (ID not available)")
    else:
        logger.debug(f"Recorded command usage: {command} by anonymous user (ID and username not available)")

def record_error(error_type):
    performance_data['errors'][error_type] += 1
    logger.debug(f"Recorded error: {error_type}")

async def save_performance_data(context: ContextTypes.DEFAULT_TYPE = None):
    conn = get_postgres_connection()
    cursor = conn.cursor()

    try:
        # Save response times
        if performance_data['response_times']:
            avg_duration = statistics.mean(performance_data['response_times'])
            min_duration = min(performance_data['response_times'])
            max_duration = max(performance_data['response_times'])
            cursor.execute('INSERT INTO response_times (avg_duration, min_duration, max_duration) VALUES (%s, %s, %s)',
                           (avg_duration, min_duration, max_duration))
            logger.info(f"Saved response times: avg={avg_duration}, min={min_duration}, max={max_duration}")
            performance_data['response_times'].clear()

        # Save model usage
        for model, count in performance_data['model_usage'].items():
            cursor.execute('''
            INSERT INTO model_usage (model, count) 
            VALUES (%s, %s) 
            ON CONFLICT (model) 
            DO UPDATE SET count = model_usage.count + %s
            ''', (model, count, count))
            logger.info(f"Saved model usage: {model} = {count}")
        performance_data['model_usage'].clear()

        # Save command usage
        for command, count in performance_data['command_usage'].items():
            cursor.execute('''
            INSERT INTO command_usage (command, count) 
            VALUES (%s, %s) 
            ON CONFLICT (command) 
            DO UPDATE SET count = command_usage.count + %s
            ''', (command, count, count))
            logger.info(f"Saved command usage: {command} = {count}")
        performance_data['command_usage'].clear()

        # Save errors
        for error_type, count in performance_data['errors'].items():
            cursor.execute('''
            INSERT INTO errors (error_type, count) 
            VALUES (%s, %s) 
            ON CONFLICT (error_type) 
            DO UPDATE SET count = errors.count + %s
            ''', (error_type, count, count))
            logger.info(f"Saved error count: {error_type} = {count}")
        performance_data['errors'].clear()

        conn.commit()
        logger.info("Performance data saved to database")
    except Exception as e:
        logger.error(f"Error saving performance data: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_performance_metrics():
    conn = get_postgres_connection()
    cursor = conn.cursor()

    # Get average, min, and max response times
    cursor.execute('SELECT AVG(avg_duration), MIN(min_duration), MAX(max_duration) FROM response_times')
    avg_response_time, min_response_time, max_response_time = cursor.fetchone()

    # Get model usage
    cursor.execute('SELECT model, SUM(count) FROM model_usage GROUP BY model ORDER BY SUM(count) DESC')
    model_usage = dict(cursor.fetchall())

    # Get command usage
    cursor.execute('SELECT command, SUM(count) FROM command_usage GROUP BY command ORDER BY SUM(count) DESC')
    command_usage = dict(cursor.fetchall())

    # Get error counts
    cursor.execute('SELECT error_type, SUM(count) FROM errors GROUP BY error_type ORDER BY SUM(count) DESC')
    errors = dict(cursor.fetchall())

    conn.close()

    metrics = f"Response times:\n"
    metrics += f"  Average: {avg_response_time:.2f} seconds\n"
    metrics += f"  Minimum: {min_response_time:.2f} seconds\n"
    metrics += f"  Maximum: {max_response_time:.2f} seconds\n\n"
    
    metrics += "Model usage:\n"
    for model, count in model_usage.items():
        metrics += f"  {model}: {count} times\n"
    
    metrics += "\nCommand usage:\n"
    for command, count in command_usage.items():
        metrics += f"  {command}: {count} times\n"
    
    metrics += "\nErrors:\n"
    for error_type, count in errors.items():
        metrics += f"  {error_type}: {count} times\n"
    
    logger.info(f"Retrieved performance metrics")
    return metrics
def record_connection_error(error_type: str, details: str = None):
    """Record connection error details for monitoring"""
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO connection_errors (error_type, details, timestamp)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                """, (error_type, details))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to record connection error: {e}")

# Make sure all necessary functions are exported
__all__ = ['init_performance_db', 'record_response_time', 'record_model_usage', 
           'record_command_usage', 'record_error', 'save_performance_data', 
           'get_performance_metrics','record_connection_error']