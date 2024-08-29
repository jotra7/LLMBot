import logging
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import FLUX_MODELS, DEFAULT_FLUX_MODEL
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
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

@queue_task('long_run')
async def flux_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("flux")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /flux command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {update.effective_user.id} requested Flux image generation: '{prompt[:50]}...'")

    # Send an initial message
    progress_message = await update.message.reply_text("🎨 Initializing image generation...")

    start_time = time.time()
    try:
        logger.info("Starting Flux image generation process")
        
        model_name = context.user_data.get('flux_model', DEFAULT_FLUX_MODEL)
        model_id = FLUX_MODELS[model_name]

        # Create a progress updater
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
                await asyncio.sleep(2)  # Update every 2 seconds

        # Start the progress updater
        progress_task = asyncio.create_task(update_progress())

        try:
            logger.info(f"Submitting Flux image generation request with model: {model_name}")
            handler = fal_client.submit(
                model_id,
                arguments={
                    "prompt": prompt,
                    "image_size": "landscape_4_3",
                    "num_inference_steps": 28,
                    "guidance_scale": 3.5,
                    "num_images": 1,
                    "safety_tolerance": "2" if model_name == "flux-pro" else None,
                },
            )

            logger.info("Waiting for Flux image generation result")
            result = handler.get()
            logger.info("Flux image generation result received")
            
            # Cancel the progress task
            progress_task.cancel()
            
            # Update the progress message
            await progress_message.edit_text("✅ Image generated! Uploading...")
            
            if result and result.get('images') and len(result['images']) > 0:
                image_url = result['images'][0]['url']
                logger.info(f"Image URL received: {image_url}")
                await update.message.reply_photo(photo=image_url, caption=f"Generated image using {model_name} for: {prompt}")
                
                # Delete the progress message
                await progress_message.delete()
            else:
                logger.error("No image URL in the result")
                await progress_message.edit_text("Sorry, I couldn't generate an image. Please try again.")
        except Exception as e:
            logger.error(f"Error during Flux image generation: {str(e)}")
            await progress_message.edit_text(f"An error occurred while generating the image: {str(e)}")
        finally:
            if not progress_task.cancelled():
                progress_task.cancel()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Flux image generated using {model_name} in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Flux image generation error for user {update.effective_user.id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while setting up image generation: {str(e)}")
        record_error("flux_image_generation_error")
    finally:
        logger.info(f"Flux command execution completed for user {update.effective_user.id}")