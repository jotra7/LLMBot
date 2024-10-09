import dramatiq
import logging
from telegram.ext import Application
from config import TELEGRAM_BOT_TOKEN
from tasks.image_tasks import generate_image_task  # Corrected import here
from tasks.task_utils import check_completed_tasks  # Corrected import here
import asyncio

# Set up logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create an instance of the bot to interact with Telegram
bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

@dramatiq.actor
def handle_generate_image(task_id, image_params):
    """
    Dramatiq actor for handling image generation tasks.

    Args:
        task_id (str): Unique identifier for the image generation task.
        image_params (dict): Dictionary containing parameters for image generation.
    """
    try:
        logger.info(f"Handling image generation request for Task ID: {task_id} with params: {image_params}")
        # Offload to the generate_image_task actor
        generate_image_task.send(task_id, image_params)
    except Exception as e:
        logger.error(f"Error handling image generation request for Task ID: {task_id}, Error: {e}")

@dramatiq.actor
def generate_image_command_handler(update, context):
    """
    Dramatiq actor to handle the /gen_img command for generating an image.

    Args:
        update: Telegram update object.
        context: Telegram context object.
    """
    task_id = str(update.message.message_id)
    prompt = update.message.text.replace('/gen_img', '').strip()
    user_id = update.message.chat_id

    image_params = {
        'prompt': prompt,
        'user_id': user_id
    }

    logger.info(f"Received /gen_img request from User ID: {user_id} with prompt: '{prompt}'")

    # Record the incoming request and offload the task to Dramatiq
    handle_generate_image.send(task_id, image_params)

    # Notify the user that their request is being processed
    asyncio.run_coroutine_threadsafe(
        update.message.reply_text("Your image generation request is in progress. We will notify you when it is ready."),
        bot_app.bot.loop
    )

# Middleware to track task completion
class TaskCompletionMiddleware(dramatiq.Middleware):
    def after_complete(self, broker, message, result=None, exception=None):
        if exception is None:
            logger.info(f"Task completed: {message.actor_name} with ID {message.message_id}")
        else:
            logger.error(f"Task failed: {message.actor_name} with ID {message.message_id}, exception={exception}")

    def after_failure(self, broker, message, exception):
        logger.error(f"Task failed: {message.actor_name} with ID {message.message_id}, exception={exception}")

# Add any additional coordination tasks if needed
check_completed_tasks()
