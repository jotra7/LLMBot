import logging
import asyncio
import os
from logging.handlers import RotatingFileHandler
from bot import initialize_bot
from model_cache import update_model_cache
from storage import init_db
from performance_metrics import init_performance_db
from queue_system import start_task_queue
from config import *

# Set up logging to a separate debug file
log_dir = "./logs"
os.makedirs(log_dir, exist_ok=True)

debug_log_file = os.path.join(log_dir, "bot_debug.log")
debug_handler = RotatingFileHandler(debug_log_file, maxBytes=10*1024*1024, backupCount=5)
debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Create a new logger for debugging
debug_logger = logging.getLogger('debug')
debug_logger.setLevel(logging.DEBUG)
debug_logger.addHandler(debug_handler)

async def main():
    debug_logger.info("Starting main function")
    try:
        debug_logger.info("Entering try block")

        # Initialize the database
        debug_logger.info("Initializing database")
        init_db()
        debug_logger.info("Database initialized successfully")

        # Initialize performance metrics database
        debug_logger.info("Initializing performance metrics database")
        init_performance_db()
        debug_logger.info("Performance metrics database initialized successfully")

        # Ensure the model cache is populated before starting the bot
        debug_logger.info("About to update model cache")
        await update_model_cache()
        debug_logger.info("Model cache updated successfully")

        # Start the task queue
        debug_logger.info("Starting task queue")
        try:
            worker_tasks = await start_task_queue()  # Await this coroutine
            debug_logger.info("Task queue started successfully")
        except Exception as e:
            debug_logger.error(f"Failed to start task queue: {e}")
            raise

        # Create the application
        debug_logger.info("About to create application")
        application = await initialize_bot()  # Await the initialize_bot function
        debug_logger.info("Application created successfully")

        # Add the worker tasks to the application
        application.worker_tasks = worker_tasks

        # Initialize the application
        debug_logger.info("About to initialize application")
        await application.initialize()
        debug_logger.info("Application initialized successfully")

        debug_logger.info("About to start application")
        await application.start()
        debug_logger.info("Application started successfully")

        debug_logger.info("About to start polling")
        await application.updater.start_polling()
        debug_logger.info("Polling started successfully")

        debug_logger.info("Bot is running. Entering main loop.")

        # Keep the bot running
        while True:
            debug_logger.debug("Main loop iteration")
            await asyncio.sleep(10)  # Log every 10 seconds to reduce log size
    except Exception as e:
        debug_logger.exception(f"An error occurred in main: {str(e)}")
    finally:
        debug_logger.info("Entering finally block")
        debug_logger.info("Stopping bot")
        if 'application' in locals() and hasattr(application, 'stop'):
            try:
                await application.stop()
                debug_logger.info("Application stop completed")
            except Exception as e:
                debug_logger.exception(f"Error during application stop: {str(e)}")
        if 'application' in locals() and hasattr(application, 'shutdown'):
            try:
                await application.shutdown()
                debug_logger.info("Application shutdown completed")
            except Exception as e:
                debug_logger.exception(f"Error during application shutdown: {str(e)}")
        
        # Cancel worker tasks
        if 'worker_tasks' in locals():
            debug_logger.info("Cancelling worker tasks")
            for task in worker_tasks.values():
                task.cancel()
            await asyncio.gather(*worker_tasks.values(), return_exceptions=True)
            debug_logger.info("Worker tasks cancelled")

        debug_logger.info("Bot stopped")

if __name__ == "__main__":
    debug_logger.info("Script started")
    asyncio.run(main())
    debug_logger.info("Script ended")