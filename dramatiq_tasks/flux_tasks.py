# flux_tasks.py

import dramatiq
import logging
import asyncio
import time
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, FLUX_MODELS, DEFAULT_FLUX_MODEL, MAX_FLUX_GENERATIONS_PER_DAY
from performance_metrics import record_command_usage, record_response_time, record_error
from database import get_user_generations_today, save_user_generation, get_user_flux_model, save_user_flux_model
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
        progress_message = loop.run_until_complete(bot.send_message(chat_id=chat_id, text="🎨 Initializing Flux generation..."))
        
        # Retrieve the user's model preference or use the default model
        model_name = get_user_flux_model(user_id)
        if not model_name:
            model_name = DEFAULT_FLUX_MODEL
            save_user_flux_model(user_id, model_name)  # Save the default model as the user's preference
        model_id = FLUX_MODELS.get(model_name, 'fal-ai/flux-pro/v1.1')

        # Async progress updater
        async def update_progress():
            steps = [
                "Analyzing prompt", "Preparing canvas", "Sketching outlines", 
                "Adding details", "Applying colors", "Refining image", 
                "Enhancing details", "Adjusting lighting", "Finalizing composition"
            ]
            step_index = 0
            dots = 0
            while True:
                step = steps[step_index % len(steps)]
                await progress_message.edit_text(f"🎨 {step}{'.' * dots}")
                dots = (dots + 1) % 4
                step_index += 1
                await asyncio.sleep(2)

        progress_task = asyncio.ensure_future(update_progress())

        try:
            # Submit task to Fal.ai
            handler = loop.run_until_complete(loop.run_in_executor(None, lambda: fal_client.submit(
                model_id,
                arguments={
                    "prompt": prompt,
                }
            )))

            result = loop.run_until_complete(loop.run_in_executor(None, handler.get))

            if result and 'images' in result and len(result['images']) > 0:
                image_url = result['images'][0]['url']
                logger.info(f"Image URL received: {image_url}")
                loop.run_until_complete(bot.send_photo(chat_id=chat_id, photo=image_url, caption=f"Generated image using {model_name} for: {prompt}"))
                
                # Save user generation
                save_user_generation(user_id, prompt, "flux")
                
                # Calculate and send remaining generations message
                remaining_generations = max_generations - (user_generations_today + 1)
                loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"You have {remaining_generations} Flux image generations left for today."))
            else:
                logger.error("No image URL in the result")
                loop.run_until_complete(bot.send_message(chat_id=chat_id, text="Sorry, I couldn't generate an image. Please try again."))
        finally:
            progress_task.cancel()
            loop.run_until_complete(progress_message.delete())

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Flux image generated using {model_name} in {response_time:.2f} seconds for user {user_id}")

    except Exception as e:
        logger.error(f"Flux image generation error for user {user_id}: {str(e)}")
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred during Flux generation: {str(e)}"))
        record_error("flux_generation_error")
    finally:
        loop.close()
        logger.info(f"Flux command execution completed for user {user_id}")