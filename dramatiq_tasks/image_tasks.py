# dramatiq_tasks/image_tasks.py

import dramatiq
import logging
from performance_metrics import record_response_time, record_error
from image_processing import generate_image_openai, analyze_image_openai
from database import save_conversation, save_user_generation
import time
import io
import asyncio

logger = logging.getLogger(__name__)

@dramatiq.actor
def generate_image_task(prompt: str, user_id: int, chat_id: int):
    start_time = time.time()
    try:
        logger.info(f"Generating image for user {user_id} with prompt: '{prompt}'")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        image_url = loop.run_until_complete(generate_image_openai(prompt))
        loop.close()
        
        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image generated in {response_time:.2f} seconds")
        
        save_conversation(user_id, prompt, "Image generated (Dramatiq)", "image")
        save_user_generation(user_id, prompt, "image")
        
        # Instead of returning, we'll use a separate actor to send the result
        send_image_result.send(chat_id, image_url, prompt)
    except Exception as e:
        logger.error(f"Image generation error for user {user_id}: {str(e)}")
        record_error("image_generation_error")
        send_error_message.send(chat_id, str(e))

@dramatiq.actor
def analyze_image_task(image_bytes: bytes, user_id: int, chat_id: int):
    start_time = time.time()
    try:
        logger.info(f"Analyzing image for user {user_id}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        analysis = loop.run_until_complete(analyze_image_openai(io.BytesIO(image_bytes)))
        loop.close()
        
        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image analyzed in {response_time:.2f} seconds")
        
        save_conversation(user_id, "Image analysis request", analysis, "image_analysis")
        
        # Instead of returning, we'll use a separate actor to send the result
        send_analysis_result.send(chat_id, analysis)
    except Exception as e:
        logger.error(f"Image analysis error for user {user_id}: {str(e)}")
        record_error("image_analysis_error")
        send_error_message.send(chat_id, str(e))

@dramatiq.actor
def send_image_result(chat_id: int, image_url: str, prompt: str):
    from telegram import Bot
    from config import TELEGRAM_BOT_TOKEN
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.send_photo(chat_id=chat_id, photo=image_url, caption=f"Generated image for: {prompt}"))
    loop.close()

@dramatiq.actor
def send_analysis_result(chat_id: int, analysis: str):
    from telegram import Bot
    from config import TELEGRAM_BOT_TOKEN
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"Image analysis:\n\n{analysis}"))
    loop.close()

@dramatiq.actor
def send_error_message(chat_id: int, error: str):
    from telegram import Bot
    from config import TELEGRAM_BOT_TOKEN
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred: {error}"))
    loop.close()