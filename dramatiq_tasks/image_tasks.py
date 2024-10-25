# dramatiq_tasks/image_tasks.py

import dramatiq
import logging
from performance_metrics import record_response_time, record_error
from image_processing import generate_image_openai, analyze_image_openai
from database import save_conversation, save_user_generation, get_user_generations_today
from image_processing import analyze_image_openai_bytes  # Import the new function
import time
import asyncio
import base64
import fal_client
from telegram import Bot
import io
import aiohttp
from config import TELEGRAM_BOT_TOKEN, MAX_VIDEO_GENERATIONS_PER_DAY



logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

@dramatiq.actor
def generate_image_task(prompt: str, user_id: int, chat_id: int):
    start_time = time.time()
    try:
        logger.info(f"Starting image generation for user {user_id} with prompt: '{prompt}'")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        image_url = loop.run_until_complete(generate_image_openai(prompt))
        loop.close()
        
        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image generated in {response_time:.2f} seconds for user {user_id}")
        
        save_conversation(user_id, prompt, "Image generated (Dramatiq)", "image")
        save_user_generation(user_id, prompt, "image")
        
        logger.info(f"Sending image result for user {user_id}")
        send_image_result.send(chat_id, image_url, prompt)
    except Exception as e:
        logger.error(f"Image generation error for user {user_id}: {str(e)}", exc_info=True)
        record_error("image_generation_error")
        send_error_message.send(chat_id, str(e))

@dramatiq.actor
def analyze_image_task(image_base64: str, user_id: int, chat_id: int):
    start_time = time.time()
    try:
        logger.info(f"Starting image analysis for user {user_id}")
        logger.debug(f"Received base64 string of length: {len(image_base64)}")
        
        # Decode base64 string back to bytes
        image_bytes = base64.b64decode(image_base64)
        logger.debug(f"Decoded image bytes of length: {len(image_bytes)}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug("Calling analyze_image_openai_bytes function")
        analysis = loop.run_until_complete(analyze_image_openai_bytes(image_bytes))
        loop.close()
        
        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image analyzed in {response_time:.2f} seconds for user {user_id}")
        
        save_conversation(user_id, "Image analysis request", analysis, "image_analysis")
        
        logger.info(f"Sending analysis result for user {user_id}")
        send_analysis_result.send(chat_id, analysis)
    except Exception as e:
        logger.error(f"Image analysis error for user {user_id}: {str(e)}", exc_info=True)
        record_error("image_analysis_error")
        send_error_message.send(chat_id, str(e))

@dramatiq.actor
def send_image_result(chat_id: int, image_url: str, prompt: str):
    logger.info(f"Sending image result to chat {chat_id}")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.send_photo(chat_id=chat_id, photo=image_url, caption=f"Generated image for: {prompt}"))
        logger.info(f"Image result sent successfully to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending image result to chat {chat_id}: {str(e)}", exc_info=True)
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred while sending the generated image: {str(e)}"))
    finally:
        loop.close()

@dramatiq.actor
def send_analysis_result(chat_id: int, analysis: str):
    logger.info(f"Sending analysis result to chat {chat_id}")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"Image analysis:\n\n{analysis}"))
        logger.info(f"Analysis result sent successfully to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending analysis result to chat {chat_id}: {str(e)}", exc_info=True)
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred while sending the image analysis: {str(e)}"))
    finally:
        loop.close()

@dramatiq.actor
def send_error_message(chat_id: int, error: str):
    logger.info(f"Sending error message to chat {chat_id}")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred: {error}"))
        logger.info(f"Error message sent successfully to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending error message to chat {chat_id}: {str(e)}", exc_info=True)
    finally:
        loop.close()


MAX_VIDEO_PER_DAY = 2  # Limit to 2 videos per day
VIDEO_GENERATION_TIMEOUT = 600  # 10 minutes total timeout

@dramatiq.actor(max_retries=0)  # No retries for video generation
def generate_video_task(prompt: str, user_id: int, chat_id: int, progress_message_id: int):
    start_time = time.time()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    async def generate_video():
        last_progress_time = time.time()
        last_message = ""

        def on_queue_update(update):
            nonlocal last_progress_time, last_message
            if isinstance(update, fal_client.InProgress):
                logs = getattr(update, 'logs', None)
                if logs:
                    message = logs[-1].get("message", "Processing video...") if logs else "Processing video..."
                    current_time = time.time()
                    
                    # Only update message if it's different or if 10 seconds have passed
                    if message != last_message or (current_time - last_progress_time) >= 10:
                        logger.info(f"Generation progress for user {user_id}: {message}")
                        try:
                            loop.run_until_complete(
                                bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=progress_message_id,
                                    text=f"🎬 {message}\n\nThis is slow AF and may take up to 10 minutes..."
                                )
                            )
                            last_progress_time = current_time
                            last_message = message
                        except Exception as e:
                            if "Message is not modified" not in str(e):
                                logger.error(f"Error updating progress message: {str(e)}")

        try:
            # Check generation limit first
            user_generations_today = get_user_generations_today(user_id, "video")
            if user_generations_today >= MAX_VIDEO_PER_DAY:
                raise Exception(f"You have reached your daily limit of {MAX_VIDEO_PER_DAY} video generations. Please try again tomorrow.")

            logger.info(f"Submitting video generation request for user {user_id}")
            
            async with asyncio.timeout(VIDEO_GENERATION_TIMEOUT):
                result = await fal_client.subscribe_async(
                    "fal-ai/fast-animatediff/turbo/text-to-video",
                    arguments={
                        "prompt": prompt,
                    },
                    with_logs=True,
                    on_queue_update=on_queue_update
                )

                if not result:
                    raise Exception("No result received from video generation")

                if 'video' not in result or not result['video'].get('url'):
                    raise Exception("Video generation failed: No video URL in result")

                video_url = result['video']['url']
                logger.info(f"Video URL received for user {user_id}: {video_url}")

                # Add a small delay to ensure video is ready
                await asyncio.sleep(2)

                async with asyncio.timeout(60):  # 1 minute timeout for download
                    async with aiohttp.ClientSession() as session:
                        async with session.get(video_url) as response:
                            if response.status == 200:
                                video_content = await response.read()
                                
                                try:
                                    await bot.delete_message(chat_id=chat_id, message_id=progress_message_id)
                                except Exception as e:
                                    logger.error(f"Error deleting progress message: {str(e)}")
                                
                                await bot.send_video(
                                    chat_id=chat_id,
                                    video=io.BytesIO(video_content),
                                    caption=f"Generated video for: {prompt}",
                                    supports_streaming=True
                                )
                                
                                save_user_generation(user_id, prompt, "video")
                                remaining_generations = MAX_VIDEO_PER_DAY - (user_generations_today + 1)
                                
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=f"You have {remaining_generations} video generations left for today."
                                )
                            else:
                                raise Exception(f"Failed to download video: HTTP {response.status}")

        except asyncio.TimeoutError:
            logger.error(f"Video generation timed out for user {user_id}")
            raise Exception("Video generation timed out. Please note that video generation can take up to 10 minutes. Try again with a simpler prompt if this persists.")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Video generation error for user {user_id}: {error_msg}")
            
            user_msg = "An error occurred while generating the video. "
            if "daily limit" in error_msg.lower():
                user_msg = error_msg  # Use the limit message directly
            elif "timed out" in error_msg.lower():
                user_msg += "The generation process timed out. Note that video generation can take up to 10 minutes. Please try again with a simpler prompt."
            elif "no video url" in error_msg.lower():
                user_msg += "The video generation failed. Please try again with a different prompt."
            else:
                user_msg += "Please try again later or with a different prompt."
            
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_message_id,
                    text=f"❌ {user_msg}"
                )
            except Exception as e:
                if "Message to edit not found" not in str(e):
                    logger.error(f"Error sending error message: {str(e)}")
                    await bot.send_message(chat_id=chat_id, text=f"❌ {user_msg}")

            record_error("video_generation_error")
            raise

    try:
        logger.info(f"Starting video generation for user {user_id} with prompt: '{prompt}'")
        loop.run_until_complete(generate_video())
        
        end_time = time.time()
        record_response_time(end_time - start_time)
        logger.info(f"Video generation process completed in {end_time - start_time:.2f} seconds for user {user_id}")

    except Exception as e:
        logger.error(f"Video task error for user {user_id}: {str(e)}")
        loop.run_until_complete(
            bot.send_message(
                chat_id=chat_id,
                text=f"An error occurred while generating the video: {str(e)}"
            )
        )
    finally:
        loop.close()