import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from functools import partial

logger = logging.getLogger(__name__)

class TaskQueue:
    def __init__(self):
        self.queues = {
            'long_run': asyncio.Queue(),
            'quick': asyncio.Queue()
        }
        self.workers = {}
        self.loop = asyncio.get_event_loop()
        logger.info("TaskQueue initialized")

    async def add_task(self, task_type: str, user_id: int, task_func, *args, **kwargs):
        logger.info(f"Adding {task_type} task for user {user_id} to queue")
        await self.queues[task_type].put((user_id, task_func, args, kwargs))
        logger.info(f"{task_type.capitalize()} task added to queue for user {user_id}. Queue size: {self.queues[task_type].qsize()}")
        if task_type not in self.workers or self.workers[task_type].done():
            self.workers[task_type] = asyncio.create_task(self.worker(task_type))

    async def worker(self, queue_type: str):
        logger.info(f"Worker for {queue_type} queue started")
        while True:
            try:
                user_id, task_func, args, kwargs = await self.queues[queue_type].get()
                logger.info(f"Processing {queue_type} task for user {user_id}")
                try:
                    await task_func(*args, **kwargs)
                    logger.info(f"{queue_type.capitalize()} task completed for user {user_id}")
                except Exception as e:
                    logger.error(f"Error processing {queue_type} task for user {user_id}: {str(e)}")
                    logger.exception("Exception details:")
                finally:
                    self.queues[queue_type].task_done()
            except Exception as e:
                logger.error(f"Error in {queue_type} worker: {str(e)}")
                await asyncio.sleep(1)

    def start(self):
        logger.info("Starting task queues")
        for queue_type in self.queues.keys():
            self.workers[queue_type] = asyncio.create_task(self.worker(queue_type))
        logger.info(f"Task queue workers started: {', '.join(self.workers.keys())}")

task_queue = TaskQueue()

def queue_task(task_type='quick'):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            user_name = update.effective_user.username    
            logger.info(f"Queueing {task_type} task for user {user_name}({user_id})")
            
            async def task_wrapper():
                try:
                    result = await func(update, context, *args, **kwargs)
                    if task_type == 'long_run':
                        logger.info(f"{task_type} task for user {user_name}({user_id}) completed.")
                    return result
                except Exception as e:
                    logger.error(f"Error in {task_type} task for user {user_id}: {str(e)}")
                    await update.message.reply_text("An error occurred while processing your request. Please try again later.")
            
            await task_queue.add_task(task_type, user_id, task_wrapper)
            
#            if task_type == 'long_run':
#                await update.message.reply_text("Your request has been queued. You'll be notified when it's ready.")
        
        return wrapper
    return decorator

async def start_task_queue():
    logger.info("Starting task queue")
    task_queue.start()
    logger.info(f"Task queue started with workers: {', '.join(task_queue.workers.keys())}")
    return task_queue.workers

async def check_queue_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    long_run_size = task_queue.queues['long_run'].qsize()
    quick_size = task_queue.queues['quick'].qsize()
    worker_status = ", ".join([f"{k}: {'running' if not v.done() else 'stopped'}" for k, v in task_queue.workers.items()])
    status_message = (
        f"Queue Status:\n"
        f"Long-running tasks in queue: {long_run_size}\n"
        f"Quick tasks in queue: {quick_size}\n"
        f"Worker status: {worker_status}"
    )
    await update.message.reply_text(status_message)