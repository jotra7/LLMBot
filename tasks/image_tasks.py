import dramatiq
import logging
import datetime
import redis
from config import REDIS_HOST, REDIS_PORT, REDIS_DB
from tasks.task_utils import track_active_task

from image_processing import generate_image_openai

logger = logging.getLogger(__name__)

# Initialize Redis client for checking task status
redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

@dramatiq.actor
def generate_image_task(task_id, image_params):
    """
    Actor for generating an image based on provided parameters.

    Args:
        task_id (str): Unique identifier for the image generation task.
        image_params (dict): Dictionary containing parameters required for generating the image.
    """
    try:
        user_id = image_params['user_id']
        track_active_task(user_id, task_id)

        start_time = datetime.datetime.now()
        logger.info(f"Started image generation for Task ID: {task_id} at {start_time}")

        # Call the function to process image generation using OpenAI
        result_url = generate_image_openai(image_params['prompt'])

        # Log successful completion and store the result in Redis
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Image generation completed for Task ID: {task_id} in {duration} seconds. Result URL: {result_url}")

        # Save result in Redis for notification purposes
        redis_client.hmset(f"task:{task_id}:completed", {
            "result_url": result_url,
            "user_id": user_id
        })
    except Exception as e:
        logger.error(f"Error generating image for Task ID: {task_id}, Error: {e}")

