import sqlite3
from statistics import mean

def init_performance_db():
    conn = sqlite3.connect('performance_metrics.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS image_generation_times
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  generation_time REAL NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def add_image_generation_time(generation_time):
    conn = sqlite3.connect('performance_metrics.db')
    c = conn.cursor()
    c.execute("INSERT INTO image_generation_times (generation_time) VALUES (?)", (generation_time,))
    conn.commit()
    conn.close()

def get_average_generation_time():
    conn = sqlite3.connect('performance_metrics.db')
    c = conn.cursor()
    c.execute("SELECT generation_time FROM image_generation_times ORDER BY timestamp DESC LIMIT 100")
    times = c.fetchall()
    conn.close()
    if times:
        return mean([t[0] for t in times])
    return None

# Initialize the database when this module is imported
init_performance_db()