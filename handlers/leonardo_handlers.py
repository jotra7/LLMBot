import logging
import json
import requests
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from config import LEONARDO_AI_KEY, LEONARDO_API_BASE_URL, DEFAULT_LEONARDO_MODEL
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task

logger = logging.getLogger(__name__)

leonardo_model_cache = {}

async def update_leonardo_model_cache(context: ContextTypes.DEFAULT_TYPE = None):
    global leonardo_model_cache
    url = f"{LEONARDO_API_BASE_URL}/platformModels"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {LEONARDO_AI_KEY}"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        custom_models = data.get('custom_models', [])
        leonardo_model_cache = {model['id']: model['name'] for model in custom_models}
        logger.info(f"Leonardo model cache updated successfully. Models: {leonardo_model_cache}")
    except Exception as e:
        logger.error(f"Error updating Leonardo model cache: {str(e)}")

async def list_leonardo_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_leonardo_models")
    logger.info(f"Current Leonardo model cache: {leonardo_model_cache}")
    if not leonardo_model_cache:
        await update_leonardo_model_cache()
        logger.info(f"Leonardo model cache after update: {leonardo_model_cache}")
    
    if leonardo_model_cache:
        models_text = "Available Leonardo.ai models:\n" + "\n".join([f"• {name} (ID: {id})" for id, name in leonardo_model_cache.items()])
    else:
        models_text = "No Leonardo.ai models available. Please try again later."
    
    await update.message.reply_text(models_text)

async def set_leonardo_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_leonardo_model")
    if not leonardo_model_cache:
        await update_leonardo_model_cache()
    
    keyboard = []
    for model_id, model_name in leonardo_model_cache.items():
        keyboard.append([InlineKeyboardButton(model_name, callback_data=f"leo_model:{model_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a Leonardo.ai model:", reply_markup=reply_markup)

async def leonardo_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    model_id = query.data.split(':')[1]
    model_name = leonardo_model_cache.get(model_id, "Unknown")
    
    context.user_data['leonardo_model'] = model_id
    await query.edit_message_text(f"Leonardo.ai model set to {model_name} (ID: {model_id})")
    logger.info(f"User {update.effective_user.id} set Leonardo model to {model_name} (ID: {model_id})")
    

async def current_leonardo_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_leonardo_model")
    model_id = context.user_data.get('leonardo_model', DEFAULT_LEONARDO_MODEL)
    if not leonardo_model_cache:
        await update_leonardo_model_cache()
    model_name = leonardo_model_cache.get(model_id, "Unknown")
    await update.message.reply_text(f"Current Leonardo.ai model: {model_name} (ID: {model_id})")

@queue_task('long_run')
async def leonardo_generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("leonardo_generate_image")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /leonardo_generate command.")
        return

    prompt = ' '.join(context.args)
    model_id = context.user_data.get('leonardo_model', DEFAULT_LEONARDO_MODEL)
    logger.info(f"User {update.effective_user.id} requested Leonardo.ai image generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text("🎨 Generating image with Leonardo.ai...")

    start_time = time.time()
    try:
        async def update_progress():
            dots = 1
            while True:
                await progress_message.edit_text(f"🎨 Generating image with Leonardo.ai{'.' * dots}")
                dots = (dots % 3) + 1
                await asyncio.sleep(2)

        progress_task = asyncio.create_task(update_progress())

        try:
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Bearer {LEONARDO_AI_KEY}"
            }
            
            payload = {
                "height": 512,
                "modelId": model_id,
                "prompt": prompt,
                "width": 512,
            }
            
            response = requests.post(f"{LEONARDO_API_BASE_URL}/generations", json=payload, headers=headers)
            response.raise_for_status()
            
            generation_id = response.json()['sdGenerationJob']['generationId']
            
            # Wait for the generation to complete
            for _ in range(30):  # Maximum wait time: 60 seconds
                await asyncio.sleep(2)
                response = requests.get(f"{LEONARDO_API_BASE_URL}/generations/{generation_id}", headers=headers)
                response.raise_for_status()
                status = response.json()['generations_by_pk']['status']
                if status == 'COMPLETE':
                    break
            
            if status != 'COMPLETE':
                raise Exception("Image generation timed out")
            
            image_url = response.json()['generations_by_pk']['generated_images'][0]['url']
            
            await update.message.reply_photo(photo=image_url, caption=f"Generated image for: {prompt}")
            await progress_message.delete()

        finally:
            progress_task.cancel()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Leonardo.ai image generated in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Leonardo.ai image generation error for user {update.effective_user.id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while generating the image: {str(e)}")
        record_error("leonardo_image_generation_error")