import time
from collections import defaultdict
import sqlite3
import statistics

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
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS response_times
    (id INTEGER PRIMARY KEY, timestamp REAL, avg_duration REAL, min_duration REAL, max_duration REAL)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS model_usage
    (id INTEGER PRIMARY KEY, model TEXT, count INTEGER)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS command_usage
    (id INTEGER PRIMARY KEY, command TEXT, count INTEGER)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS errors
    (id INTEGER PRIMARY KEY, error_type TEXT, count INTEGER)
    ''')
    conn.commit()
    conn.close()

def record_response_time(duration):
    performance_data['response_times'].append(duration)

def record_model_usage(model):
    performance_data['model_usage'][model] += 1

def record_command_usage(command):
    performance_data['command_usage'][command] += 1

def record_error(error_type):
    performance_data['errors'][error_type] += 1

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
        performance_data['response_times'].clear()

    # Save model usage
    for model, count in performance_data['model_usage'].items():
        cursor.execute('INSERT OR REPLACE INTO model_usage (model, count) VALUES (?, COALESCE((SELECT count FROM model_usage WHERE model = ?) + ?, ?))',
                       (model, model, count, count))
    performance_data['model_usage'].clear()

    # Save command usage
    for command, count in performance_data['command_usage'].items():
        cursor.execute('INSERT OR REPLACE INTO command_usage (command, count) VALUES (?, COALESCE((SELECT count FROM command_usage WHERE command = ?) + ?, ?))',
                       (command, command, count, count))
    performance_data['command_usage'].clear()

    # Save errors
    for error_type, count in performance_data['errors'].items():
        cursor.execute('INSERT OR REPLACE INTO errors (error_type, count) VALUES (?, COALESCE((SELECT count FROM errors WHERE error_type = ?) + ?, ?))',
                       (error_type, error_type, count, count))
    performance_data['errors'].clear()

    conn.commit()
    conn.close()

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
    
    return metrics