import logging
import asyncio
import time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
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
PHOTOMAKER_MODEL = "tencentarc/photomaker:ddfc2b08d209f9fa8c1eca692712918bd449f695dabb4a958da31802a9570fe4"
SAN_ANDREAS_TRIGGER_WORD = "STL"
PHOTOMAKER_TRIGGER_WORD = "IMG"

PHOTOMAKER_STYLES = [
    "(No style)", "Cinematic", "Disney Charactor", "Digital Art", 
    "Photographic (Default)", "Fantasy art", "Neonpunk", "Enhance", 
    "Comic book", "Lowpoly", "Line art"
]

# Define conversation states
UPLOADING, PROMPT, STYLE = range(3)

async def photomaker_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    record_command_usage("photomaker")
    user_id = update.effective_user.id
    user_name = update.effective_user.username
    logger.info(f"Photomaker started by user {user_id} ({user_name})")

    user_generations_today = get_user_generations_today(user_id, "replicate")
    logger.info(f"User {user_id} has generated {user_generations_today} Replicate images today")
    if user_generations_today >= MAX_REPLICATE_GENERATIONS_PER_DAY:
        logger.warning(f"User {user_id} reached daily limit for Replicate generations")
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_REPLICATE_GENERATIONS_PER_DAY} Replicate image generations.")
        return ConversationHandler.END

    await update.message.reply_text("Please upload 1 to 4 images of the subject. Send /done when you're finished uploading.")
    context.user_data['photomaker_images'] = []
    return UPLOADING

async def upload_images(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_url = file.file_path
        context.user_data['photomaker_images'].append(file_url)
        await update.message.reply_text(f"Image received. Total images: {len(context.user_data['photomaker_images'])}")
        if len(context.user_data['photomaker_images']) >= 4:
            await update.message.reply_text(f"Maximum number of images reached. Please provide your prompt. Remember to include the trigger word '{PHOTOMAKER_TRIGGER_WORD}' at the end of your prompt for best results.")
            return PROMPT
        return UPLOADING
    elif update.message.text == "/done":
        if not context.user_data['photomaker_images']:
            await update.message.reply_text("You need to upload at least one image. Please upload an image.")
            return UPLOADING
        await update.message.reply_text(f"Image upload complete. Please provide your prompt. Remember to include the trigger word '{PHOTOMAKER_TRIGGER_WORD}' at the end of your prompt for best results.")
        return PROMPT
    else:
        await update.message.reply_text("Please upload an image or send /done when finished.")
        return UPLOADING

async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = update.message.text
    if not prompt.strip().__contains__(PHOTOMAKER_TRIGGER_WORD):
        prompt = f"{prompt.strip()} {PHOTOMAKER_TRIGGER_WORD}"
        await update.message.reply_text(f"I've added the trigger word '{PHOTOMAKER_TRIGGER_WORD}' to the end of your prompt for better results.")
    
    context.user_data['photomaker_prompt'] = prompt
    
    keyboard = [[InlineKeyboardButton(style, callback_data=f"style_{i}")] for i, style in enumerate(PHOTOMAKER_STYLES)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please select a style:", reply_markup=reply_markup)
    
    return STYLE

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from config import MAX_REPLICATE_GENERATIONS_PER_DAY
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
from database import get_user_generations_today, save_user_generation
import replicate

logger = logging.getLogger(__name__)

PHOTOMAKER_MODEL = "tencentarc/photomaker:ddfc2b08d209f9fa8c1eca692712918bd449f695dabb4a958da31802a9570fe4"
PHOTOMAKER_TRIGGER_WORD = "img"

PHOTOMAKER_STYLES = [
    "(No style)", "Cinematic", "Disney Charactor", "Digital Art", 
    "Photographic (Default)", "Fantasy art", "Neonpunk", "Enhance", 
    "Comic book", "Lowpoly", "Line art"
]

# Define conversation states
UPLOADING, PROMPT, STYLE = range(3)

# ... [previous functions remain unchanged]

async def get_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    style_index = int(query.data.split('_')[1])
    selected_style = PHOTOMAKER_STYLES[style_index]
    context.user_data['photomaker_style'] = selected_style

    await query.edit_message_text(f"Style selected: {selected_style}")
    
    # Prepare data for the job
    job_data = {
        'chat_id': update.effective_chat.id,
        'user_id': update.effective_user.id,
        'photomaker_prompt': context.user_data.get('photomaker_prompt'),
        'photomaker_style': selected_style,
        'photomaker_images': context.user_data.get('photomaker_images', [])
    }
    
    # Schedule the image generation task
    context.job_queue.run_once(generate_image, 0, data=job_data, name=f"generate_image_{update.effective_user.id}")
    
    await query.message.reply_text("Your image generation request has been queued. Please wait...")
    return ConversationHandler.END

async def generate_image(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    data = job.data
    chat_id = data.get('chat_id')
    user_id = data.get('user_id')
    
    if not chat_id or not user_id:
        logger.error(f"Chat ID or User ID not found")
        return

    try:
        await context.bot.send_message(chat_id=chat_id, text="Generating image, please wait...")

        input_data = {
            "prompt": data['photomaker_prompt'],
            "num_steps": 20,  # Default value
            "style_name": data['photomaker_style'],
            "num_outputs": 1,
            "guidance_scale": 5,  # Default value
            "input_image": data['photomaker_images'][0],
        }
        for i, img in enumerate(data['photomaker_images'][1:], start=2):
            input_data[f"input_image{i}"] = img

        logger.info(f"Sending request to Replicate API with input data: {input_data}")
        output = replicate.run(PHOTOMAKER_MODEL, input=input_data)
        logger.info(f"Received output from Replicate API: {output}")

        if output and len(output) > 0:
            image_url = output[0]
            caption = f"Generated image using Photomaker:\nPrompt: {data['photomaker_prompt']}\nStyle: {data['photomaker_style']}"
            await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption)
            
            save_user_generation(user_id, data['photomaker_prompt'], "replicate")
            
            user_generations_today = get_user_generations_today(user_id, "replicate")
            remaining_generations = MAX_REPLICATE_GENERATIONS_PER_DAY - user_generations_today
            await context.bot.send_message(chat_id=chat_id, text=f"You have {remaining_generations} Replicate image generations left for today.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Sorry, I couldn't generate an image. Please try again.")

    except Exception as e:
        logger.error(f"Photomaker image generation error for user {user_id}: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text=f"An error occurred while generating the image: {str(e)}")
        record_error("photomaker_image_generation_error")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Photomaker process cancelled.")
    return ConversationHandler.END


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
        await update.message.reply_text(f"Please provide a prompt after the /san_andreas command. Be sure to include the trigger word '{SAN_ANDREAS_TRIGGER_WORD}' at the end of your prompt for best results.")
        return

    prompt = ' '.join(context.args)
    if not prompt.strip().endswith(SAN_ANDREAS_TRIGGER_WORD):
        prompt = f"{prompt.strip()} {SAN_ANDREAS_TRIGGER_WORD}"
        await update.message.reply_text(f"I've added the trigger word '{SAN_ANDREAS_TRIGGER_WORD}' to the end of your prompt for better results.")

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
    logger.info("Setting up replicate handlers")
    
    photomaker_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("photomaker", photomaker_start)],
        states={
            UPLOADING: [MessageHandler(filters.PHOTO | filters.Regex('^/done$'), upload_images)],
            PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prompt)],
            STYLE: [CallbackQueryHandler(get_style)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(photomaker_conv_handler)
    application.add_handler(CommandHandler("san_andreas", san_andreas_command))  
    logger.info("Replicate handlers set up successfully")
