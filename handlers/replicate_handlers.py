import logging
import asyncio
import time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from config import MAX_REPLICATE_GENERATIONS_PER_DAY
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
from database import get_user_generations_today, save_user_generation
import replicate

logger = logging.getLogger(__name__)

# Ensure you have set the REPLICATE_API_TOKEN environment variable
if "REPLICATE_API_TOKEN" not in os.environ:
    logger.error("REPLICATE_API_TOKEN environment variable is not set")

SAN_ANDREAS_MODEL = "levelsio/san-andreas:61cdb2f6a8f234ea9ca3cce88d5454f9b951f93619f5f353a331407f4a05a314"
TRIGGER_WORD = "STL"

async def list_replicate_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_replicate_models")
    models_text = "Available Replicate models:\n• San Andreas (GTA style image generation)"
    await update.message.reply_text(models_text)

@queue_task('long_run')
async def san_andreas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("san_andreas")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "replicate")
    logger.info(f"User {user_id} has generated {user_generations_today} Replicate images today")
    if user_generations_today >= MAX_REPLICATE_GENERATIONS_PER_DAY:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_REPLICATE_GENERATIONS_PER_DAY} Replicate image generations.")
        return

    if not context.args:
        await update.message.reply_text(f"Please provide a prompt after the /san_andreas command. Be sure to include the trigger word '{TRIGGER_WORD}' in your prompt for best results.")
        return

    prompt = ' '.join(context.args)
    if TRIGGER_WORD not in prompt:
        prompt = f"{TRIGGER_WORD} {prompt}"
        await update.message.reply_text(f"I've added the trigger word '{TRIGGER_WORD}' to your prompt for better results.")

    logger.info(f"User {user_id} requested San Andreas image generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text("🎮 Initializing San Andreas image generation...")

    start_time = time.time()
    try:
        async def update_progress():
            steps = [
                "Loading San Andreas assets", "Preparing scene", "Generating characters",
                "Adding vehicles", "Setting up lighting", "Rendering image",
                "Applying GTA filters", "Finalizing output"
            ]
            step_index = 0
            dots = 0
            while True:
                step = steps[step_index % len(steps)]
                await progress_message.edit_text(f"🎮 {step}{'.' * dots}")
                dots = (dots + 1) % 4
                step_index += 1
                await asyncio.sleep(2)

        progress_task = asyncio.create_task(update_progress())

        try:
            input_data = {
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "num_outputs": 1,
                "guidance_scale": 3.5,
                "num_inference_steps": 28,
            }

            loop = asyncio.get_running_loop()
            output = await loop.run_in_executor(None, lambda: replicate.run(SAN_ANDREAS_MODEL, input=input_data))

            if output and len(output) > 0:
                image_url = output[0]
                await update.message.reply_photo(photo=image_url, caption=f"Generated San Andreas style image for: {prompt}")
                
                # Save user generation
                save_user_generation(user_id, prompt, "replicate")
                
                # Calculate and send remaining generations message
                remaining_generations = MAX_REPLICATE_GENERATIONS_PER_DAY - (user_generations_today + 1)
                await update.message.reply_text(f"You have {remaining_generations} San Andreas image generations left for today.")
            else:
                logger.error("No image URL in the result")
                await update.message.reply_text("Sorry, I couldn't generate an image. Please try again.")
        finally:
            progress_task.cancel()
            await progress_message.delete()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"San Andreas image generated in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"San Andreas image generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while generating the image: {str(e)}")
        record_error("san_andreas_image_generation_error")
    finally:
        logger.info(f"San Andreas command execution completed for user {user_id}")

def setup_replicate_handlers(application):
    application.add_handler(CommandHandler("list_replicate_models", list_replicate_models))
    application.add_handler(CommandHandler("san_andreas", san_andreas_command))