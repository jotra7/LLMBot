import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_BOT_TOKEN
from handlers import (
    start, help_command, list_models, set_model, current_model,
    tts_command, list_voices, set_voice, current_voice, get_history,
    generate_image, analyze_image, button_callback, handle_message
)
from utils import periodic_cache_update, periodic_voice_cache_update
from database import init_db
from datetime import timedelta

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

# Initialize the database
init_db()

def create_application():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("listmodels", list_models))
    application.add_handler(CommandHandler("setmodel", set_model))
    application.add_handler(CommandHandler("currentmodel", current_model))
    application.add_handler(CommandHandler("tts", tts_command))
    application.add_handler(CommandHandler("listvoices", list_voices))
    application.add_handler(CommandHandler("setvoice", set_voice))
    application.add_handler(CommandHandler("currentvoice", current_voice))
    application.add_handler(CommandHandler("history", get_history))
    application.add_handler(CommandHandler("generate_image", generate_image))
    application.add_handler(CommandHandler("analyze_image", analyze_image))
    application.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Only respond to messages that are either in private chats or mention the bot
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.PRIVATE | filters.Entity("mention")),
        handle_message
    ))

    # Schedule the periodic cache updates
    application.job_queue.run_repeating(periodic_cache_update, interval=timedelta(days=1), first=10)
    application.job_queue.run_repeating(periodic_voice_cache_update, interval=timedelta(days=1), first=10)

    return application