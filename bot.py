import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_BOT_TOKEN
from handlers import (
    conv_handler,
    help_menu,
    list_models, set_model, current_model,
    tts_command, list_voices, set_voice, current_voice, voice_button_callback,
    generate_image, analyze_image,
    generate_text_to_video,
    admin_broadcast, admin_user_stats, admin_ban_user, admin_unban_user,
    admin_set_global_system_message, admin_view_logs, admin_restart_bot,
    admin_update_model_cache, admin_performance, notify_admins, on_startup,
    list_flux_models, set_flux_model, current_flux_model, flux_model_callback, flux_command,
    handle_message, error_handler, delete_session_command, img2video_command,
    list_leonardo_models, set_leonardo_model, current_leonardo_model,
    leonardo_generate_image, update_leonardo_model_cache, leonardo_model_callback, leonardo_unzoom,
    get_history, set_system_message, get_system_message
)
from utils import periodic_cache_update, periodic_voice_cache_update
from database import init_db
from performance_metrics import init_performance_db, save_performance_data
from datetime import timedelta
import model_cache
from storage import delete_user_session
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

    # Add the conversation handler for start and other interactive features
    application.add_handler(conv_handler)

    # Add a separate handler for the help command
    application.add_handler(CommandHandler("help", help_menu))

    # Add other command handlers
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
    application.add_handler(CommandHandler("current_flux_model", current_flux_model))
    application.add_handler(CommandHandler("queue_status", check_queue_status))
    application.add_handler(CommandHandler("video", generate_text_to_video))
    application.add_handler(CommandHandler("img2video", img2video_command))
    application.add_handler(CommandHandler("delete_session", delete_session_command))
    application.add_handler(CommandHandler("list_leonardo_models", list_leonardo_models))
    application.add_handler(CommandHandler("set_leonardo_model", set_leonardo_model))
    application.add_handler(CommandHandler("current_leonardo_model", current_leonardo_model))
    application.add_handler(CommandHandler("leo", leonardo_generate_image))
    application.add_handler(CommandHandler("unzoom", leonardo_unzoom))

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

    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(voice_button_callback, pattern=r"^voice_"))
    application.add_handler(CallbackQueryHandler(flux_model_callback, pattern=r"^set_flux_model:"))
    application.add_handler(CallbackQueryHandler(leonardo_model_callback, pattern="^leo_model:"))

    # Add message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.PRIVATE | filters.Entity("mention")),
        handle_message
    ))

    # Set up error handler
    application.add_error_handler(error_handler)

    # Schedule periodic tasks
    application.job_queue.run_repeating(periodic_cache_update, interval=timedelta(days=1), first=10)
    application.job_queue.run_repeating(periodic_voice_cache_update, interval=timedelta(days=1), first=10)
    application.job_queue.run_once(lambda context: asyncio.create_task(update_leonardo_model_cache(context)), when=0)
    application.job_queue.run_repeating(lambda context: asyncio.create_task(update_leonardo_model_cache(context)), interval=timedelta(days=1), first=timedelta(days=1))   
    
    async def save_performance_data_job(context):
        await save_performance_data()

    application.job_queue.run_repeating(save_performance_data_job, interval=timedelta(hours=1), first=10)
    application.job_queue.run_once(on_startup, when=0)

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

    # Schedule the admin notification
    application.job_queue.run_once(notify_admins, when=1)

    return application

def main():
    application = initialize_bot()
    application.run_polling()

if __name__ == '__main__':
    main()