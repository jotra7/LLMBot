import logging
import requests
from telegram import Update
from telegram.ext import ContextTypes
from performance_metrics import record_command_usage, record_error
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

    progress_message = await update.message.reply_text("🎬 Generating video... This may take 20-30 seconds or more.")

    try:
        handler = fal_client.submit(
            "fal-ai/fast-animatediff/text-to-video",
            arguments={
                "prompt": prompt,
                "num_frames": 150,
                "num_inference_steps": 25,
                "guidance_scale": 7.5,
                "fps": 30,
                "video_size": "square"
            }
        )

        result = handler.get()
        video_url = result['video']['url']
        
        await progress_message.edit_text("✅ Video generated! Uploading...")
        
        video_content = requests.get(video_url).content
        
        await update.message.reply_video(video_content, caption=f"Generated video for: {prompt}")
        
        await progress_message.delete()

        logger.info(f"Video generated successfully for user {user_id}")

    except Exception as e:
        logger.error(f"Video generation error for user {user_id}: {str(e)}")
        try:
            await progress_message.edit_text(f"❌ An error occurred while generating the video: {str(e)}")
        except Exception as edit_error:
            logger.error(f"Error updating progress message: {str(edit_error)}")
        record_error("video_generation_error")
    
    finally:
        logger.info(f"Video generation process completed for user {user_id}")