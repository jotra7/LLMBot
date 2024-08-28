import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_BOT_TOKEN
from handlers import (
    start, help_command, list_models, set_model, current_model,
    tts_command, list_voices, set_voice, current_voice, get_history,
    generate_image, analyze_image, button_callback, handle_message,
    set_system_message, get_system_message, generate_sound, flux_command,
    list_flux_models, set_flux_model, current_flux_model, flux_model_callback, 
    generate_text_to_video, queue_status,
    # Admin commands
    admin_broadcast, admin_user_stats, admin_ban_user, admin_unban_user,
    admin_set_global_system_message, admin_view_logs, admin_restart_bot,
    admin_update_model_cache, admin_performance
)
from utils import periodic_cache_update, periodic_voice_cache_update
from database import init_db
from performance_metrics import init_performance_db, save_performance_data
from datetime import timedelta
import model_cache
from queue_system import start_task_queue, task_queue, check_queue_status

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

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
    application.add_handler(CommandHandler("set_system_message", set_system_message))
    application.add_handler(CommandHandler("get_system_message", get_system_message))
    application.add_handler(CommandHandler("flux", flux_command))
    application.add_handler(CommandHandler("list_flux_models", list_flux_models))
    application.add_handler(CommandHandler("set_flux_model", set_flux_model))
    application.add_handler(CallbackQueryHandler(flux_model_callback, pattern=r"^set_flux_model:"))
    application.add_handler(CommandHandler("current_flux_model", current_flux_model))
    application.add_handler(CommandHandler("queue_status", check_queue_status))
    application.add_handler(CommandHandler("generatesound", generate_sound))
    application.add_handler(CommandHandler("video", generate_text_to_video))

    # Admin command handlers
    application.add_handler(CommandHandler("admin_broadcast", admin_broadcast))
    application.add_handler(CommandHandler("admin_user_stats", admin_user_stats))
    application.add_handler(CommandHandler("admin_ban", admin_ban_user))
    application.add_handler(CommandHandler("admin_unban", admin_unban_user))
    application.add_handler(CommandHandler("admin_set_global_system", admin_set_global_system_message))
    application.add_handler(CommandHandler("admin_logs", admin_view_logs))
    application.add_handler(CommandHandler("admin_restart", admin_restart_bot))
    application.add_handler(CommandHandler("admin_update_models", admin_update_model_cache))
    application.add_handler(CommandHandler("admin_performance", admin_performance))

    application.add_handler(CallbackQueryHandler(button_callback))

    # Only respond to messages that are either in private chats or mention the bot
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.PRIVATE | filters.Entity("mention")),
        handle_message
    ))

    # Schedule periodic tasks
    application.job_queue.run_repeating(periodic_cache_update, interval=timedelta(days=1), first=10)
    application.job_queue.run_repeating(periodic_voice_cache_update, interval=timedelta(days=1), first=10)

    async def save_performance_data_job(context):
        await save_performance_data()

    application.job_queue.run_repeating(save_performance_data_job, interval=timedelta(hours=1), first=10)

    return application

def initialize_bot():
    # Initialize the database
    init_db()
    init_performance_db()

    # Start the task queue and keep a reference to the worker tasks
    worker_tasks = start_task_queue()

    # Create the application
    application = create_application()

    # Add the worker tasks to the application so they don't get garbage collected
    application.worker_tasks = worker_tasks

    return application