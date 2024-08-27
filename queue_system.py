import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class TaskQueue:
    def __init__(self):
        self.queues = {
            'long_run': asyncio.Queue(),
            'quick': asyncio.Queue()
        }
        self.active_tasks = set()
        logger.info("TaskQueue initialized")

    async def add_task(self, task_type: str, user_id: int, task_func, *args, **kwargs):
        logger.info(f"Adding {task_type} task for user {user_id} to queue")
        await self.queues[task_type].put((user_id, task_func, args, kwargs))
        logger.info(f"{task_type.capitalize()} task added to queue for user {user_id}. Queue size: {self.queues[task_type].qsize()}")

    async def process_queue(self, queue_type: str):
        while True:
            user_id, task_func, args, kwargs = await self.queues[queue_type].get()
            logger.info(f"Processing {queue_type} task for user {user_id}")
            try:
                await task_func(*args, **kwargs)
                logger.info(f"{queue_type.capitalize()} task completed for user {user_id}")
            except Exception as e:
                logger.error(f"Error processing {queue_type} task for user {user_id}: {str(e)}")
            finally:
                self.queues[queue_type].task_done()

    async def start(self):
        logger.info("Starting task queues")
        self.active_tasks.add(asyncio.create_task(self.process_queue('long_running')))
        self.active_tasks.add(asyncio.create_task(self.process_queue('quick')))

task_queue = TaskQueue()

def queue_task(task_type='quick'):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            logger.info(f"Queueing {task_type} task for user {user_id}")
            await task_queue.add_task(task_type, user_id, func, update, context, *args, **kwargs)
            if task_type == 'long_running':
                await update.message.reply_text("Your request has been queued. You'll be notified when it's ready.")
        return wrapper
    return decorator

async def start_task_queue(application):
    await task_queue.start()
    logger.info("Task queues started")

async def check_queue_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    long_running_size = task_queue.queues['long_running'].qsize()
    quick_size = task_queue.queues['quick'].qsize()
    await update.message.reply_text(f"Long-running tasks in queue: {long_running_size}\nQuick tasks in queue: {quick_size}")

logger.info("queue_system module loaded")