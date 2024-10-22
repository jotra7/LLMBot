# run_workers.py

import dramatiq
from dramatiq.cli import main
import sys
import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging():
    log_dir = "./logs"
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "dramatiq_workers.log")
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # Set Dramatiq logger to use file handler
    dramatiq_logger = logging.getLogger("dramatiq")
    dramatiq_logger.addHandler(file_handler)
    dramatiq_logger.propagate = False  # Prevent double logging

if __name__ == "__main__":
    setup_logging()
    
    # Set sys.argv for Dramatiq modules to load
    sys.argv = ["dramatiq", "dramatiq_tasks.image_tasks", "dramatiq_tasks.suno_tasks", "dramatiq_tasks.flux_tasks", "dramatiq_tasks.voice_tasks"]
    
    # Call the main function to start Dramatiq workers
    main()
