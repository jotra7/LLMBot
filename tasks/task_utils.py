# task_utils.py
import logging
import redis
from config import REDIS_HOST, REDIS_PORT, REDIS_DB

logger = logging.getLogger(__name__)

# Initialize Redis client for checking task status
redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

def check_completed_tasks():
    """
    Check completed tasks and handle results.
    """
    try:
        task_keys = redis_client.keys("task:*:completed")
        for key in task_keys:
            result_data = redis_client.hgetall(key)
            user_id = result_data.get(b'user_id').decode("utf-8")
            result_url = result_data.get(b'result_url').decode("utf-8")
            logger.info(f"Task completed for User ID {user_id}: {result_url}")
            # Notify the user by sending them the result URL

            # Remove the task from Redis after handling
            redis_client.delete(key)

            # Decrement active task count for user
            active_key = f"user:{user_id}:active_tasks"
            redis_client.decr(active_key)

            # If there are no more active tasks, remove the key
            if redis_client.get(active_key) == b'0':
                redis_client.delete(active_key)
    except Exception as e:
        logger.error(f"Error while checking completed tasks: {e}")

def track_active_task(user_id, task_id):
    """
    Track active tasks for a user.
    """
    active_key = f"user:{user_id}:active_tasks"
    redis_client.incr(active_key)
    redis_client.hset(f"task:{task_id}:info", "user_id", user_id)

