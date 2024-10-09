# task_manager.py

import logging
from telegram.ext import ContextTypes
from dramatiq.results import Results
from dramatiq.results.errors import ResultMissing
import asyncio

logger = logging.getLogger(__name__)

async def check_pending_tasks(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function should be called periodically to check for completed tasks
    and send results to users.
    """
    results = Results()
    logger.info("Starting to check pending tasks")

    try:
        # Get all pending results
        pending_results = results.get_all()

        for task_id, result in pending_results.items():
            try:
                if result['success']:
                    if 'image_url' in result:
                        await context.bot.send_photo(chat_id=result['chat_id'], photo=result['image_url'], caption=f"Generated image for: {result['prompt']}")
                    elif 'analysis' in result:
                        await context.bot.send_message(chat_id=result['chat_id'], text=f"Image analysis:\n\n{result['analysis']}")
                else:
                    await context.bot.send_message(chat_id=result['chat_id'], text=f"An error occurred: {result['error']}")

                # Remove the result after processing
                results.forget(task_id)

            except Exception as e:
                logger.error(f"Error processing task result {task_id}: {str(e)}", exc_info=True)

    except Exception as e:
        logger.error(f"Error checking pending tasks: {str(e)}", exc_info=True)

    logger.info("Finished checking pending tasks")