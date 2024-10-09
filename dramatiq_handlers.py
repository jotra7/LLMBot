# dramatiq_handlers.py

import logging
from telegram import Update
from telegram.ext import ContextTypes
from performance_metrics import record_command_usage
from database import get_user_generations_today
from config import MAX_GENERATIONS_PER_DAY
from dramatiq_tasks.image_tasks import generate_image_task, analyze_image_task
from dramatiq_tasks.suno_tasks import generate_music_task
import base64

logger = logging.getLogger(__name__)

async def generate_image_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_image_dramatiq")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "image")
    logger.info(f"User {user_id} has generated {user_generations_today} images today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} image generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /generate_image_dramatiq command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested image generation via Dramatiq: '{prompt}'")

    progress_message = await update.message.reply_text("🎨 Initializing image generation with Dramatiq...")

    try:
        # Enqueue the task
        generate_image_task.send(prompt, user_id, update.effective_chat.id)

        await progress_message.edit_text("Your image generation task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq image generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the image generation task: {str(e)}")

async def analyze_image_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("analyze_image_dramatiq")
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
    else:
        await update.message.reply_text("Please send an image or reply to an image with the /analyze_image_dramatiq command.")
        return

    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested image analysis via Dramatiq")

    progress_message = await update.message.reply_text("🔍 Initializing image analysis with Dramatiq...")

    try:
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        # Convert image bytes to base64 string
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Enqueue the task
        analyze_image_task.send(image_base64, user_id, update.effective_chat.id)

        await progress_message.edit_text("Your image analysis task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq image analysis error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the image analysis task: {str(e)}")

async def suno_generate_music_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_generate_music_dramatiq")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} music generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /suno_gen command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested Suno music generation via Dramatiq: '{prompt}'")

    progress_message = await update.message.reply_text("🎵 Initializing music generation with Dramatiq...")

    try:
        # Enqueue the task
        generate_music_task.send(prompt, user_id, update.effective_chat.id)

        await progress_message.edit_text("Your music generation task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq Suno music generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the music generation task: {str(e)}")

async def suno_generate_instrumental_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_generate_instrumental_dramatiq")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} music generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /gen_inst command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested Suno instrumental music generation via Dramatiq: '{prompt}'")

    progress_message = await update.message.reply_text("🎵 Initializing instrumental music generation with Dramatiq...")

    try:
        # Enqueue the task with make_instrumental=True
        generate_music_task.send(prompt, user_id, update.effective_chat.id, make_instrumental=True)

        await progress_message.edit_text("Your instrumental music generation task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq Suno instrumental music generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the instrumental music generation task: {str(e)}")