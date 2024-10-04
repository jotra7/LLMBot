import logging
import asyncio
import time
import functools
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from config import FLUX_MODELS, DEFAULT_FLUX_MODEL, MAX_FLUX_GENERATIONS_PER_DAY, MAX_BRR_PER_DAY
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
from database import get_user_generations_today, save_user_generation
import fal_client

logger = logging.getLogger(__name__)

async def list_flux_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_flux_models")
    models_text = "Available Flux models:\n" + "\n".join([f"• {name}" for name in FLUX_MODELS.keys()])
    await update.message.reply_text(models_text)

async def set_flux_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_flux_model")
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"set_flux_model:{model_id}")]
        for name, model_id in FLUX_MODELS.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a Flux model:", reply_markup=reply_markup)

async def flux_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    model_id = query.data.split(':')[1]
    model_name = next((name for name, id in FLUX_MODELS.items() if id == model_id), None)
    
    if model_name:
        context.user_data['flux_model'] = model_name
        await query.edit_message_text(f"Flux model set to {model_name}")
    else:
        await query.edit_message_text("Invalid model selection. Please try again.")

async def current_flux_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_flux_model")
    current = context.user_data.get('flux_model', DEFAULT_FLUX_MODEL)
    await update.message.reply_text(f"Current Flux model: {current}")

from config import FLUX_MODELS, DEFAULT_FLUX_MODEL, MAX_FLUX_GENERATIONS_PER_DAY
from database import get_user_generations_today, save_user_generation

@queue_task('long_run')
async def flux_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("flux")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    if MAX_FLUX_GENERATIONS_PER_DAY is None:
        logger.error("MAX_FLUX_GENERATIONS_PER_DAY is not defined in config.py")
        await update.message.reply_text("Sorry, there's an issue with the generation limit configuration. Please try again later or contact support.")
        return

    user_generations_today = get_user_generations_today(user_id, "flux")
    logger.info(f"User {user_id} has generated {user_generations_today} Flux images today")
    if user_generations_today >= MAX_FLUX_GENERATIONS_PER_DAY:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_FLUX_GENERATIONS_PER_DAY} Flux image generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /flux command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested Flux image generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text("🎨 Initializing Flux image generation...")

    start_time = time.time()
    try:
        model_name = context.user_data.get('flux_model', DEFAULT_FLUX_MODEL)
        model_id = FLUX_MODELS[model_name]

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

        progress_task = asyncio.create_task(update_progress())

        try:
            loop = asyncio.get_running_loop()
            handler = await loop.run_in_executor(None, lambda: fal_client.submit(
                model_id,
                arguments={
                    "prompt": prompt,
                }
            ))

            result = await loop.run_in_executor(None, handler.get)

            if result and 'images' in result and len(result['images']) > 0:
                image_url = result['images'][0]['url']
                logger.info(f"Image URL received: {image_url}")
                await update.message.reply_photo(photo=image_url, caption=f"Generated image using {model_name} for: {prompt}")
                
                # Save user generation
                save_user_generation(user_id, image_url, "flux")
                
                # Calculate and send remaining generations message
                remaining_generations = MAX_FLUX_GENERATIONS_PER_DAY - (user_generations_today + 1)
                await update.message.reply_text(f"You have {remaining_generations} Flux image generations left for today.")
            else:
                logger.error("No image URL in the result")
                await update.message.reply_text("Sorry, I couldn't generate an image. Please try again.")
        finally:
            progress_task.cancel()
            await progress_message.delete()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Flux image generated using {model_name} in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Flux image generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while generating the image: {str(e)}")
        record_error("flux_image_generation_error")
    finally:
        logger.info(f"Flux command execution completed for user {user_id}")

@queue_task('long_run')
async def remove_background(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("remove_background")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    # Check user's daily limit
    user_generations_today = get_user_generations_today(user_id, "rbb")
    logger.info(f"User {user_id} has removed {user_generations_today} backgrounds today")
    if user_generations_today >= MAX_BRR_PER_DAY:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_FLUX_GENERATIONS_PER_DAY} Flux generations.")
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Please reply to an image with the /remove_bg command.")
        return

    logger.info(f"User {user_id} requested background removal")

    progress_message = await update.message.reply_text("🖼️ Processing image for background removal...")

    start_time = time.time()
    try:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_url = file.file_path

        async def update_progress():
            steps = [
                "Analyzing image", "Identifying foreground", "Removing background",
                "Refining edges", "Finalizing image"
            ]
            step_index = 0
            dots = 0
            while True:
                step = steps[step_index % len(steps)]
                await progress_message.edit_text(f"🖼️ {step}{'.' * dots}")
                dots = (dots + 1) % 4
                step_index += 1
                await asyncio.sleep(2)

        progress_task = asyncio.create_task(update_progress())

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, functools.partial(
                fal_client.run,
                "fal-ai/birefnet",
                arguments={
                    "image_url": file_url
                }
            ))
            logger.info(f"API response from fal.ai: {result}")

            # Check for the 'image' key instead of 'no_background_image'
            if result and 'image' in result and 'url' in result['image']:
                image_url = result['image']['url']
                await update.message.reply_photo(photo=image_url, caption="Here's your image with the background removed!")
                await progress_message.delete()

                # Save user generation
                save_user_generation(user_id, "remove_bg", "rbb")

                user_generations_today = get_user_generations_today(user_id, "rbb")
                remaining_generations = max(0, MAX_BRR_PER_DAY - user_generations_today)
                await update.message.reply_text(f"You have {remaining_generations} background removals left for today.")

                logger.info(f"Background removed successfully for user {user_id}")
            else:
                raise ValueError("Unexpected response format from fal.ai API")

        finally:
            progress_task.cancel()

    except Exception as e:
        logger.error(f"Background removal error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred during background removal: {str(e)}")
        record_error("background_removal_error")

    finally:
        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Background removal completed in {response_time:.2f} seconds")

def setup_flux_handlers(application):
    application.add_handler(CommandHandler("list_flux_models", list_flux_models))
    application.add_handler(CommandHandler("set_flux_model", set_flux_model))
    application.add_handler(CommandHandler("current_flux_model", current_flux_model))
    application.add_handler(CommandHandler("flux", flux_command))
    application.add_handler(CommandHandler("remove_bg", remove_background))