import logging
import asyncio
import time
import requests
from telegram import Update
from telegram.ext import ContextTypes
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
import fal_client

logger = logging.getLogger(__name__)

@queue_task('long_run')
async def generate_text_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_text_to_video")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /video command.")
        return

    prompt = ' '.join(context.args)
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested text-to-video generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text("🎬 Initializing video generation...")

    start_time = time.time()
    try:
        async def update_progress():
            steps = [
                "Analyzing prompt", "Preparing scene", "Generating frames",
                "Rendering video", "Applying effects", "Finalizing output"
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
                "fal-ai/fast-animatediff/text-to-video",
                arguments={
                    "prompt": prompt,
                    "num_frames": 64,
                    "num_inference_steps": 25,
                    "guidance_scale": 7.5,
                    "fps": 16,
                    "video_size": "square"
                }
            ))

            result = await loop.run_in_executor(None, handler.get)
            video_url = result['video']['url']
            
            await progress_message.edit_text("✅ Video generated! Uploading...")
            
            video_content = await loop.run_in_executor(None, lambda: requests.get(video_url).content)
            
            await update.message.reply_video(video_content, caption=f"Generated video for: {prompt}")
            
            await progress_message.delete()

            logger.info(f"Video generated successfully for user {user_id}")

        finally:
            progress_task.cancel()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Video generated in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Video generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"❌ An error occurred while generating the video: {str(e)}")
        record_error("video_generation_error")
    
    finally:
        logger.info(f"Video generation process completed for user {user_id}")

@queue_task('long_run')
async def img2video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("img2video")
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Please reply to an image with the /img2video command.")
        return

    user_id = update.effective_user.id
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