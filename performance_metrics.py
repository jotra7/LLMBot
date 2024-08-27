import time
from collections import defaultdict
import sqlite3
import statistics
import logging

logger = logging.getLogger(__name__)

# Initialize performance tracking
performance_data = {
    'response_times': [],
    'model_usage': defaultdict(int),
    'command_usage': defaultdict(int),
    'errors': defaultdict(int)
}

def init_performance_db():
    conn = sqlite3.connect('performance_metrics.db')
    cursor = conn.cursor()
    # ... (create tables code remains the same)
    conn.commit()
    conn.close()
    logger.info("Performance database initialized")

def record_response_time(duration):
    performance_data['response_times'].append(duration)
    logger.debug(f"Recorded response time: {duration}")

def record_model_usage(model):
    performance_data['model_usage'][model] += 1
    logger.debug(f"Recorded model usage: {model}")

def record_command_usage(command):
    performance_data['command_usage'][command] += 1
    logger.debug(f"Recorded command usage: {command}")

def record_error(error_type):
    performance_data['errors'][error_type] += 1
    logger.debug(f"Recorded error: {error_type}")

def save_performance_data():
    conn = sqlite3.connect('performance_metrics.db')
    cursor = conn.cursor()

    # Save response times
    if performance_data['response_times']:
        avg_duration = statistics.mean(performance_data['response_times'])
        min_duration = min(performance_data['response_times'])
        max_duration = max(performance_data['response_times'])
        cursor.execute('INSERT INTO response_times (timestamp, avg_duration, min_duration, max_duration) VALUES (?, ?, ?, ?)',
                       (time.time(), avg_duration, min_duration, max_duration))
        logger.info(f"Saved response times: avg={avg_duration}, min={min_duration}, max={max_duration}")
        performance_data['response_times'].clear()

    # Save model usage
    for model, count in performance_data['model_usage'].items():
        cursor.execute('INSERT OR REPLACE INTO model_usage (model, count) VALUES (?, COALESCE((SELECT count FROM model_usage WHERE model = ?) + ?, ?))',
                       (model, model, count, count))
        logger.info(f"Saved model usage: {model} = {count}")
    performance_data['model_usage'].clear()

    # Save command usage
    for command, count in performance_data['command_usage'].items():
        cursor.execute('INSERT OR REPLACE INTO command_usage (command, count) VALUES (?, COALESCE((SELECT count FROM command_usage WHERE command = ?) + ?, ?))',
                       (command, command, count, count))
        logger.info(f"Saved command usage: {command} = {count}")
    performance_data['command_usage'].clear()

    # Save errors
    for error_type, count in performance_data['errors'].items():
        cursor.execute('INSERT OR REPLACE INTO errors (error_type, count) VALUES (?, COALESCE((SELECT count FROM errors WHERE error_type = ?) + ?, ?))',
                       (error_type, error_type, count, count))
        logger.info(f"Saved error count: {error_type} = {count}")
    performance_data['errors'].clear()

    conn.commit()
    conn.close()
    logger.info("Performance data saved to database")

def get_performance_metrics():
    conn = sqlite3.connect('performance_metrics.db')
    cursor = conn.cursor()

    cursor.execute('SELECT AVG(avg_duration) FROM response_times')
    avg_response_time = cursor.fetchone()[0] or 0

    cursor.execute('SELECT model, SUM(count) FROM model_usage GROUP BY model')
    model_usage = dict(cursor.fetchall())

    cursor.execute('SELECT command, SUM(count) FROM command_usage GROUP BY command')
    command_usage = dict(cursor.fetchall())

    cursor.execute('SELECT error_type, SUM(count) FROM errors GROUP BY error_type')
    errors = dict(cursor.fetchall())

    conn.close()

    metrics = f"Average response time: {avg_response_time:.2f} seconds\n\n"
    
    metrics += "Model usage:\n"
    for model, count in model_usage.items():
        metrics += f"{model}: {count} times\n"
    
    metrics += "\nCommand usage:\n"
    for command, count in command_usage.items():
        metrics += f"{command}: {count} times\n"
    
    metrics += "\nErrors:\n"
    for error_type, count in errors.items():
        metrics += f"{error_type}: {count} times\n"
    
    logger.info(f"Retrieved performance metrics: {metrics}")
    return metrics

# Make sure all necessary functions are exported
__all__ = ['init_performance_db', 'record_response_time', 'record_model_usage', 
           'record_command_usage', 'record_error', 'save_performance_data', 
           'get_performance_metrics']