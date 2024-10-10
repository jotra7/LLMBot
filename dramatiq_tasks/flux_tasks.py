# flux_tasks.py

import dramatiq
import logging
import time
from performance_metrics import record_response_time, record_error
from database import save_user_generation, get_user_generations_today
import fal_client
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, MAX_FLUX_GENERATIONS_PER_DAY, FLUX_MODELS
import asyncio

logger = logging.getLogger(__name__)

@dramatiq.actor
def generate_flux_image_task(prompt: str, model_id: str, user_id: int, chat_id: int, progress_message_id: int):
    start_time = time.time()
    try:
        logger.info(f"Starting Flux image generation for user {user_id} with prompt: '{prompt}'")
        
        # Create a new event loop for this task
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Submit the task to fal_client
        handler = fal_client.submit(
            model_id,
            arguments={
                "prompt": prompt,
            }
        )

        # Wait for the result
        result = handler.get()

        if result and 'images' in result and len(result['images']) > 0:
            image_url = result['images'][0]['url']
            logger.info(f"Image URL received: {image_url}")
            
            # Use run_coroutine_threadsafe to send messages
            loop.run_until_complete(bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=f"Generated Flux image for: {prompt}"
            ))
            
            # Save user generation
            save_user_generation(user_id, prompt, "flux")
            
            # Calculate and send remaining generations message
            user_generations_today = get_user_generations_today(user_id, "flux")
            remaining_generations = MAX_FLUX_GENERATIONS_PER_DAY - user_generations_today
            loop.run_until_complete(bot.send_message(
                chat_id=chat_id,
                text=f"You have {remaining_generations} Flux image generations left for today."
            ))
        else:
            logger.error("No image URL in the result")
            loop.run_until_complete(bot.send_message(
                chat_id=chat_id,
                text="Sorry, I couldn't generate an image. Please try again."
            ))

        # Delete the progress message
        loop.run_until_complete(bot.delete_message(chat_id=chat_id, message_id=progress_message_id))

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Flux image generated in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Flux image generation error for user {user_id}: {str(e)}")
        loop.run_until_complete(bot.send_message(
            chat_id=chat_id,
            text=f"An error occurred while generating the Flux image: {str(e)}"
        ))
        record_error("flux_image_generation_error")
    finally:
        loop.close()