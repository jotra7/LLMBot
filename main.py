import logging
import asyncio
import os
from logging.handlers import RotatingFileHandler
from bot import initialize_bot
from model_cache import update_model_cache
from storage import init_db
from performance_metrics import init_performance_db
from queue_system import start_task_queue
from config import ADMIN_USER_IDS

def setup_logging():
    log_dir = "./logs"
    os.makedirs(log_dir, exist_ok=True)

    # Main log file
    main_log_file = os.path.join(log_dir, "bot.log")
    main_handler = RotatingFileHandler(main_log_file, maxBytes=10*1024*1024, backupCount=5)
    main_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_handler.setFormatter(main_formatter)
    main_handler.setLevel(logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Set to DEBUG to allow fine-grained control
    root_logger.addHandler(main_handler)

    # Set levels for specific loggers
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)
    logging.getLogger('apscheduler').setLevel(logging.INFO)

    # Ensure your application's logger is set to INFO
    logging.getLogger('__main__').setLevel(logging.INFO)
    logging.getLogger('bot').setLevel(logging.INFO)
    logging.getLogger('handlers').setLevel(logging.INFO)

setup_logging()

logger = logging.getLogger(__name__)
logging.getLogger('apscheduler').setLevel(logging.INFO)

async def main():
    logger.info("Starting main function")
    try:
        logger.info("Entering try block")

        # Initialize the database
        logger.info("Initializing database")
        init_db()
        logger.info("Database initialized successfully")

        # Initialize performance metrics database
        logger.info("Initializing performance metrics database")
        init_performance_db()
        logger.info("Performance metrics database initialized successfully")

        # Ensure the model cache is populated before starting the bot
        logger.info("About to update model cache")
        try:
            await update_model_cache()
        except Exception as e:
            logger.error(f'Error updating model cache: {str(e)}')
            raise
        logger.info("Model cache updated successfully")

        # Start the task queue
        logger.info("Starting task queue")
        try:
            worker_tasks = await start_task_queue()  # Await this coroutine
            logger.info("Task queue started successfully")
        except Exception as e:
            logger.error(f"Failed to start task queue: {e}")
            raise

        # Create the application
        logger.info("About to create application")
        application = await initialize_bot()  # Await the initialize_bot function
        logger.info("Application created successfully")

        # Add the worker tasks to the application
        application.worker_tasks = worker_tasks

        # Initialize the application
        logger.info("About to initialize application")
        await application.initialize()
        logger.info("Application initialized successfully")

        logger.info("About to start application")
        try:
            await application.start()
        except Exception as e:
            logger.error(f'Error starting application: {str(e)}')
            raise
        logger.info("Application started successfully")

        logger.info("About to start polling")
        await application.updater.start_polling()
        logger.info("Polling started successfully")

        # Notify admins that the bot has been restarted
        logger.info("Bot restarted or rebooted successfully. Notifying admins.")
        for admin_id in ADMIN_USER_IDS:
            try:
                await application.bot.send_message(chat_id=admin_id, text='🚀 Bot has been rebooted or restarted successfully!')
                logger.info(f'Sent restart notification to admin {admin_id}')
            except Exception as e:
                logger.error(f'Failed to send restart notification to admin {admin_id}: {str(e)}')

        logger.info("Bot is running. Entering main loop.")

        # Keep the bot running
        while True:
            await asyncio.sleep(10)  # Log every 10 seconds to reduce log size
    except Exception as e:
        logger.exception(f"An error occurred in main: {str(e)}")
    finally:
        logger.info("Entering finally block")
        logger.info("Stopping bot")
        if 'application' in locals() and hasattr(application, 'stop'):
            try:
                await application.stop()
            except Exception as e:
                logger.error(f'Error during application stop: {str(e)}')
                raise
            logger.info("Application stop completed")
        if 'application' in locals() and hasattr(application, 'shutdown'):
            try:
                await application.shutdown()
                logger.info("Application shutdown completed")
            except Exception as e:
                logger.exception(f"Error during application shutdown: {str(e)}")
        
        # Cancel worker tasks
        if 'worker_tasks' in locals():
            logger.info("Cancelling worker tasks")
            for task in worker_tasks.values():
                task.cancel()
            await asyncio.gather(*worker_tasks.values(), return_exceptions=True)
            logger.info("Worker tasks cancelled")

        logger.info("Bot stopped")

if __name__ == "__main__":
    logger.info("Script started")
    asyncio.run(main())
    logger.info("Script ended")