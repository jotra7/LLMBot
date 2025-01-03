import logging
import asyncio
import time
import requests
from telegram import Update
from telegram.ext import ContextTypes
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
import fal_client
import aiohttp
from config import MAX_VIDEO_GENERATIONS_PER_DAY, MAX_I2V_GENERATIONS_PER_DAY
from database import get_user_generations_today, save_user_generation

logger = logging.getLogger(__name__)

async def generate_text_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_text_to_video")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    # Check user's daily limit
    user_generations_today = get_user_generations_today(user_id, "video")
    logger.info(f"User {user_id} has generated {user_generations_today} videos today")
    if user_generations_today >= MAX_VIDEO_GENERATIONS_PER_DAY:
        await update.message.reply_text(
            f"Sorry {user_name}, you have reached your daily limit of {MAX_VIDEO_GENERATIONS_PER_DAY} video generations. "
            "Please try again tomorrow."
        )
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /video command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested text-to-video generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text(
        "🎬 Initializing video generation...\n\n"
        "Note: Video generation can take up to 10 minutes. You will be notified when it's ready."
    )

    try:
        # Enqueue the video generation task
        from dramatiq_tasks.image_tasks import generate_video_task
        generate_video_task.send(prompt, user_id, update.effective_chat.id, progress_message.message_id)

    except Exception as e:
        logger.error(f"Error queueing video generation for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queueing the video generation: {str(e)}")
        record_error("video_generation_queue_error")

@queue_task('long_run')
async def img2video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("img2video")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    # Check user's daily limit
    user_generations_today = get_user_generations_today(user_id, "img2video")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    if user_generations_today >= MAX_I2V_GENERATIONS_PER_DAY:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_I2V_GENERATIONS_PER_DAY} generations.")
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Please reply to an image with the /img2video command.")
        return

    logger.info(f"User {user_id} requested Img2Video conversion")

    progress_message = await update.message.reply_text("🎬 Initializing video conversion...")

    start_time = time.time()
    try:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_url = file.file_path

        async def update_progress():
            steps = [
                "Processing image", "Generating frames", "Applying motion",
                "Rendering video", "Finalizing output"
            ]
            step_index = 0
            dots = 0
            while True:
                step = steps[step_index % len(steps)]
                await progress_message.edit_text(f"🎬 {step}{'.' * dots}")
                dots = (dots + 1) % 4
                step_index += 1
                await asyncio.sleep(2)

        progress_task = asyncio.create_task(update_progress())

        try:
            loop = asyncio.get_running_loop()
            handler = await loop.run_in_executor(None, lambda: fal_client.submit(
                "fal-ai/stable-video",
                arguments={
                    "image_url": file_url,
                    "motion_bucket_id": 127,
                    "cond_aug": 0.02,
                    "fps": 25
                },
            ))

            result = await loop.run_in_executor(None, handler.get)
            
            await progress_message.edit_text("✅ Video generated! Uploading...")
            
            if result and result.get('video') and result['video'].get('url'):
                video_url = result['video']['url']
                video_content = await loop.run_in_executor(None, lambda: requests.get(video_url).content)
                
                await update.message.reply_video(
                    video_content, 
                    caption="Generated video from the image",
                    supports_streaming=True
                )
                
                await progress_message.delete()

                # Save user generation
                save_user_generation(user_id, "img2video", "video")

                # Get updated user's generations today
                user_generations_today = get_user_generations_today(user_id, "img2video")
                
                remaining_generations = max(0, MAX_I2V_GENERATIONS_PER_DAY - user_generations_today)
                await update.message.reply_text(f"You have {remaining_generations} generations left for today.")
            else:
                logger.error("No video URL in the result")
                await progress_message.edit_text("Sorry, I couldn't generate a video. Please try again.")

        finally:
            progress_task.cancel()

    except Exception as e:
        logger.error(f"Img2Video conversion error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred during video conversion: {str(e)}")
        record_error("img2video_conversion_error")

    finally:
        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Img2Video conversion completed in {response_time:.2f} seconds")