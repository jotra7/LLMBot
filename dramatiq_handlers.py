# dramatiq_handlers.py

import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from performance_metrics import record_command_usage
from database import get_user_generations_today
from config import MAX_GENERATIONS_PER_DAY
from dramatiq_tasks.image_tasks import generate_image_task, analyze_image_task
from dramatiq_tasks.suno_tasks import generate_music_task, generate_custom_music_task
import base64
from dramatiq_tasks.flux_tasks import generate_flux_image_task
from config import *

TITLE, IS_INSTRUMENTAL, LYRICS, TAGS, CONFIRM = range(5)


logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
async def analyze_image_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("analyze_image_dramatiq")
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
    else:
        await update.message.reply_text("Please send an image or reply to an image with the /analyze_image_dramatiq command.")
        return

    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested image analysis via Dramatiq")

    progress_message = await update.message.reply_text("🔍 Initializing image analysis with Dramatiq...")

    try:
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        # Convert image bytes to base64 string
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Enqueue the task
        analyze_image_task.send(image_base64, user_id, update.effective_chat.id)

        await progress_message.edit_text("Your image analysis task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq image analysis error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the image analysis task: {str(e)}")


async def generate_image_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_image_dramatiq")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "image")
    logger.info(f"User {user_id} has generated {user_generations_today} images today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} image generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /generate_image_dramatiq command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested image generation via Dramatiq: '{prompt}'")

    progress_message = await update.message.reply_text("🎨 Initializing image generation with Dramatiq...")

    try:
        # Enqueue the task
        generate_image_task.send(prompt, user_id, update.effective_chat.id)

        await progress_message.edit_text("Your image generation task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq image generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the image generation task: {str(e)}")

async def generate_flux_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_flux_dramatiq")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "flux")
    logger.info(f"User {user_id} has generated {user_generations_today} Flux generations today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} Flux generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /newflux command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested Flux generation via Dramatiq: '{prompt}'")

    progress_message = await update.message.reply_text("⚙️ Initializing Flux generation with Dramatiq...")

    try:
        # Enqueue the task
        generate_flux_image_task.send(prompt, user_id, update.effective_chat.id)

        await progress_message.edit_text("Your Flux generation task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq Flux generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the Flux generation task: {str(e)}")

async def suno_generate_music_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_generate_music_dramatiq")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} music generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /gen_music command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested Suno music generation via Dramatiq: '{prompt}'")

    progress_message = await update.message.reply_text("🎵 Initializing music generation with Dramatiq...")

    try:
        # Enqueue the task
        generate_music_task.send(prompt, user_id, update.effective_chat.id)

        await progress_message.edit_text("Your music generation task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq Suno music generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the music generation task: {str(e)}")

async def suno_generate_instrumental_dramatiq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_generate_instrumental_dramatiq")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} music generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /gen_inst command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested Suno instrumental music generation via Dramatiq: '{prompt}'")

    progress_message = await update.message.reply_text("🎵 Initializing instrumental music generation with Dramatiq...")

    try:
        # Enqueue the task with make_instrumental=True
        generate_music_task.send(prompt, user_id, update.effective_chat.id, make_instrumental=True)

        await progress_message.edit_text("Your instrumental music generation task has been queued. You'll be notified when it's ready.")

    except Exception as e:
        logger.error(f"Dramatiq Suno instrumental music generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the instrumental music generation task: {str(e)}")

async def fluxnew_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("fluxnew")
    user_id = update.effective_user.id
    user_name = update.effective_user.username
    chat_id = update.effective_chat.id

    user_generations_today = get_user_generations_today(user_id, "flux")
    logger.info(f"User {user_id} has generated {user_generations_today} Flux images today")
    if user_generations_today >= MAX_FLUX_GENERATIONS_PER_DAY:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_FLUX_GENERATIONS_PER_DAY} Flux image generations.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /fluxnew command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {user_id} requested Flux image generation: '{prompt[:50]}...'")

    model_name = context.user_data.get('flux_model', DEFAULT_FLUX_MODEL)
    model_id = FLUX_MODELS[model_name]

    progress_message = await update.message.reply_text("🎨 Initializing Flux image generation...")

    try:
        # Enqueue the task
        generate_flux_image_task.send(prompt, model_id, user_id, chat_id, progress_message.message_id)

    except Exception as e:
        logger.error(f"Dramatiq Flux image generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while queuing the Flux image generation task: {str(e)}")

TITLE, IS_INSTRUMENTAL, LYRICS, TAGS, CONFIRM = range(5)

async def cust_mus_gen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    record_command_usage("cust_mus_gen")
    user_id = update.effective_user.id
    user_name = update.effective_user.username

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    
    max_generations = int(MAX_GENERATIONS_PER_DAY)
    
    if user_generations_today >= max_generations:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {max_generations} generations.")
        return ConversationHandler.END

    await update.message.reply_text("Let's create a custom song! What's the title of your song?")
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Should this be an instrumental track? (Yes/No)")
    return IS_INSTRUMENTAL

async def get_is_instrumental(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_instrumental = update.message.text.lower() == 'yes'
    context.user_data['make_instrumental'] = is_instrumental
    if is_instrumental:
        await update.message.reply_text("What genre or style tags would you like for your instrumental? (e.g., 'pop metal male melancholic')")
        return TAGS
    else:
        await update.message.reply_text("Please enter the lyrics for your song. Use line breaks to separate verses and choruses.")
        return LYRICS

async def get_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lyrics'] = update.message.text
    await update.message.reply_text("What genre or style tags would you like for your song? (e.g., 'pop metal male melancholic')")
    return TAGS

async def get_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['tags'] = update.message.text
    
    confirmation = f"Title: {context.user_data['title']}\n"
    confirmation += f"Instrumental: {'Yes' if context.user_data['make_instrumental'] else 'No'}\n"
    if not context.user_data['make_instrumental']:
        confirmation += f"Lyrics: {context.user_data['lyrics'][:50]}...\n"
    confirmation += f"Tags: {context.user_data['tags']}\n"
    
    confirmation += "\nIs this correct? Type 'yes' to generate or 'no' to start over."
    
    await update.message.reply_text(confirmation)
    return CONFIRM

async def generate_custom_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.lower() != 'yes':
        await update.message.reply_text("Generation cancelled. Please start over with /cust_mus_gen")
        return ConversationHandler.END

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    title = context.user_data['title']
    make_instrumental = context.user_data['make_instrumental']
    lyrics = context.user_data.get('lyrics', '')
    tags = context.user_data['tags']

    progress_message = await update.message.reply_text("🎵 Queueing custom music generation task...")

    try:
        generate_custom_music_task.send(title, make_instrumental, lyrics, tags, user_id, chat_id)
        await progress_message.edit_text("Your custom music generation task has been queued. You'll be notified when it's ready.")
    except Exception as e:
        logger.error(f"Error queueing custom music generation for user {user_id}: {str(e)}")
        await update.message.reply_text("An error occurred while queueing your custom music generation. Please try again later.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Custom music generation cancelled. Feel free to start over when you're ready.")
    return ConversationHandler.END

def setup_cust_mus_gen_handler(application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("custom_generate_music", cust_mus_gen)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            IS_INSTRUMENTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_is_instrumental)],
            LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lyrics)],
            TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tags)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_custom_music)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)