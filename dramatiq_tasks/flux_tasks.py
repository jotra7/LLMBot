# flux_tasks.py

import dramatiq
import logging
import asyncio
import time
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, FLUX_MODELS, DEFAULT_FLUX_MODEL, MAX_FLUX_GENERATIONS_PER_DAY
from performance_metrics import record_command_usage, record_response_time, record_error
from database import get_user_generations_today, save_user_generation
import fal_client

logger = logging.getLogger(__name__)

@dramatiq.actor
def generate_flux_task(prompt: str, user_id: int, chat_id: int):
    """
    Handles the Flux model generation task asynchronously.
    """
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    start_time = time.time()
    
    logger.info(f"Flux generation task started for user {user_id} with prompt: '{prompt}'")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Check daily generation limits
        user_generations_today = get_user_generations_today(user_id, "flux")
        logger.info(f"User {user_id} has generated {user_generations_today} Flux generations today")
        
        max_generations = int(MAX_FLUX_GENERATIONS_PER_DAY)
        if user_generations_today >= max_generations:
            loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"Sorry, you have reached your daily limit of {max_generations} Flux generations."))
            return

        # Initialize Flux generation
        progress_message = loop.run_until_complete(bot.send_message(chat_id=chat_id, text="⚙️ Initializing Flux generation..."))
        
        # Call the Fal.ai client to generate the output (adjusted to use subscribe_async)
        model_id = 'fal-ai/flux-pro/v1.1'  # Default to flux-pro-1.1 as specified

        async def generate_flux():
            def on_queue_update(update):
                if isinstance(update, fal_client.InProgress):
                    for log in update.logs:
                        logger.info(f"Flux generation progress: {log['message']}")

            result = await fal_client.subscribe_async(
                model_id,
                arguments={
                    "prompt": prompt,
                },
                on_queue_update=on_queue_update,
            )
            return result

        handler = loop.run_until_complete(generate_flux())
        logger.info(f"Flux API response for user {user_id}: {handler}")
        
        # Assuming handler contains a URL to the generated image
        if handler and 'image' in handler and 'url' in handler['image']:
            image_url = handler['image']['url']
            loop.run_until_complete(bot.send_photo(chat_id=chat_id, photo=image_url, caption="Here is your Flux-generated image!"))
        else:
            raise ValueError("Unexpected response format from Flux API")

        # Save the generation to the database
        save_user_generation(user_id, prompt, "flux")
        
    except Exception as e:
        logger.error(f"Flux generation error for user {user_id}: {str(e)}")
        record_error("flux_generation_error")
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred during Flux generation: {str(e)}"))
    
    finally:
        end_time = time.time()
        record_response_time(end_time - start_time)
        logger.info(f"Flux generation completed in {end_time - start_time:.2f} seconds for user {user_id}")
        loop.close()