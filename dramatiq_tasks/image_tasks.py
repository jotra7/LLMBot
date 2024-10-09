# dramatiq_tasks/image_tasks.py

import dramatiq
import logging
from performance_metrics import record_response_time, record_error
from image_processing import generate_image_openai, analyze_image_openai
from database import save_conversation, save_user_generation
import time
import io
import asyncio
import base64
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN

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
        logger.debug("Calling analyze_image_openai function")
        analysis = loop.run_until_complete(analyze_image_openai(io.BytesIO(image_bytes)))
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