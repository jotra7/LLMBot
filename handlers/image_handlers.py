import logging
import asyncio
import time
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from image_processing import generate_image_openai, analyze_image_openai
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task

logger = logging.getLogger(__name__)

@queue_task('long_run')
async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_image")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /generate_image command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {update.effective_user.id} requested image generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text("🎨 Initializing image generation...")

    start_time = time.time()
    try:
        # Create a progress updater
        async def update_progress():
            dots = 0
            while True:
                await progress_message.edit_text(f"🎨 Generating image{'.' * dots}")
                dots = (dots + 1) % 4
                await asyncio.sleep(2)

        # Start the progress updater
        progress_task = asyncio.create_task(update_progress())

        try:
            image_url = await generate_image_openai(prompt)
            await update.message.reply_photo(photo=image_url, caption=f"Generated image for: {prompt}")
        finally:
            # Cancel the progress task
            progress_task.cancel()
            
            # Delete the progress message
            await progress_message.delete()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image generated in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Image generation error for user {update.effective_user.id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while generating the image: {str(e)}")
        record_error("image_generation_error")

@queue_task('long_run')
async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("analyze_image")
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
    else:
        await update.message.reply_text("Please send an image or reply to an image with the /analyze_image command.")
        return

    logger.info(f"User {update.effective_user.id} requested image analysis")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    start_time = time.time()
    try:
        async def keep_typing():
            while True:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
                await asyncio.sleep(5)

        typing_task = asyncio.create_task(keep_typing())

        try:
            file = await context.bot.get_file(photo.file_id)
            file_bytes = await file.download_as_bytearray()
            analysis = await analyze_image_openai(file_bytes)
            await update.message.reply_text(f"Image analysis:\n\n{analysis}")
        finally:
            typing_task.cancel()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image analyzed in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Image analysis error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while analyzing the image: {str(e)}")
        record_error("image_analysis_error")

# Ensure these functions are exported
__all__ = ['generate_image', 'analyze_image']