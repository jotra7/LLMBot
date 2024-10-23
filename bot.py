from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_BOT_TOKEN, REDIS_DB, REDIS_HOST, REDIS_PORT
from handlers import (
    user_handlers,
    model_handlers,
    voice_handlers,
    video_handlers,
    admin_handlers,
    flux_handlers,
    message_handlers,
    leonardo_handlers,
    gpt_handlers,
    replicate_handlers
)

from model_cache import periodic_cache_update
from voice_cache import periodic_voice_cache_update
from performance_metrics import save_performance_data
from database import cleanup_old_generations
from datetime import timedelta, time
from dramatiq_handlers import generate_image_dramatiq, analyze_image_dramatiq, fluxnew_command, suno_generate_instrumental_dramatiq, suno_generate_music_dramatiq, setup_cust_mus_gen_handler
import redis

def create_application():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers from user_handlers first
    application.add_handler(user_handlers.conv_handler)
    application.add_handler(CommandHandler("help", user_handlers.help_menu))
    application.add_handler(CommandHandler("history", user_handlers.get_history))
    application.add_handler(CommandHandler("set_system_message", user_handlers.set_system_message))
    application.add_handler(CommandHandler("get_system_message", user_handlers.get_system_message))
    application.add_handler(CommandHandler("delete_session", user_handlers.delete_session_command))

    # Add GPT handlers early (to catch voice_select callbacks)
    gpt_handlers.setup_gpt_handlers(application)

    # Add handlers from model_handlers
    application.add_handler(CommandHandler("list_models", model_handlers.list_models))
    application.add_handler(CommandHandler("set_model", model_handlers.set_model))
    application.add_handler(CommandHandler("current_model", model_handlers.current_model))
    application.add_handler(CallbackQueryHandler(model_handlers.button_callback))

    # Add handlers from voice_handlers
    application.add_handler(CommandHandler("tts", voice_handlers.tts_command))
    application.add_handler(CommandHandler("list_voices", voice_handlers.list_voices))
    application.add_handler(CommandHandler("set_voice", voice_handlers.set_voice))
    application.add_handler(CommandHandler("current_voice", voice_handlers.current_voice))
    application.add_handler(voice_handlers.voice_addition_handler)
    application.add_handler(CommandHandler("delete_custom_voice", voice_handlers.delete_custom_voice))

    # Add dramatiq handlers
    application.add_handler(CommandHandler("generate_image", generate_image_dramatiq))
    application.add_handler(CommandHandler("analyze_image", analyze_image_dramatiq))
    application.add_handler(CommandHandler("generate_music", suno_generate_music_dramatiq))
    application.add_handler(CommandHandler("generate_instrumental", suno_generate_instrumental_dramatiq))
    application.add_handler(CommandHandler('flux', fluxnew_command))
    setup_cust_mus_gen_handler(application)

    # Add video handlers
    application.add_handler(CommandHandler("video", video_handlers.generate_text_to_video))
    application.add_handler(CommandHandler("img2video", video_handlers.img2video_command))

    # Add admin handlers
    application.add_handler(CommandHandler("admin_broadcast", admin_handlers.admin_broadcast))
    application.add_handler(CommandHandler("admin_user_stats", admin_handlers.admin_user_stats))
    application.add_handler(CommandHandler("admin_ban", admin_handlers.admin_ban_user))
    application.add_handler(CommandHandler("admin_unban", admin_handlers.admin_unban_user))
    application.add_handler(CommandHandler("admin_set_global_system", admin_handlers.admin_set_global_system_message))
    application.add_handler(CommandHandler("admin_logs", admin_handlers.admin_view_logs))
    application.add_handler(CommandHandler("admin_restart", admin_handlers.admin_restart_bot))
    application.add_handler(CommandHandler("admin_update_models", admin_handlers.admin_update_model_cache))
    application.add_handler(CommandHandler("admin_performance", admin_handlers.admin_performance))

    # Add flux and leonardo handlers
    flux_handlers.setup_flux_handlers(application)
    application.add_handler(CommandHandler("list_leonardo_models", leonardo_handlers.list_leonardo_models))
    application.add_handler(CommandHandler("set_leonardo_model", leonardo_handlers.set_leonardo_model))
    application.add_handler(CommandHandler("current_leonardo_model", leonardo_handlers.current_leonardo_model))
    application.add_handler(CommandHandler("leo", leonardo_handlers.leonardo_generate_image))

    # Add replicate handlers
    replicate_handlers.setup_replicate_handlers(application)

    # Add message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.PRIVATE | filters.Entity("mention")),
        message_handlers.handle_message
    ))

    # Set up error handler
    application.add_error_handler(message_handlers.error_handler)

    # Add remaining callback query handlers
    application.add_handler(CallbackQueryHandler(voice_handlers.voice_button_callback, pattern=r"^voice_"))
    application.add_handler(CallbackQueryHandler(flux_handlers.flux_model_callback, pattern=r"^set_flux_model:"))
    application.add_handler(CallbackQueryHandler(leonardo_handlers.leonardo_model_callback, pattern="^leo_model:"))
    
    # Add bug command
    application.add_handler(CommandHandler("bug", user_handlers.bug_command))

    return application

async def initialize_bot():
    """Initialize and return the bot application."""
    application = create_application()

    # Schedule periodic tasks
    application.job_queue.run_repeating(periodic_cache_update, interval=timedelta(days=1), first=10)
    application.job_queue.run_repeating(periodic_voice_cache_update, interval=timedelta(days=1), first=10)
    application.job_queue.run_repeating(save_performance_data, interval=timedelta(hours=1), first=10)
    application.job_queue.run_once(leonardo_handlers.update_leonardo_model_cache, when=0)
    application.job_queue.run_repeating(leonardo_handlers.update_leonardo_model_cache, interval=timedelta(days=1), first=timedelta(days=1))
    application.job_queue.run_daily(lambda _: cleanup_old_generations(), time=time(hour=0, minute=0))

    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    audio_id_pattern = "user:*:audio_id"

    deleted_count = 0
    for key in redis_client.scan_iter(audio_id_pattern):
        redis_client.delete(key)
        deleted_count += 1

    if deleted_count > 0:
        print(f"Flushed {deleted_count} audio IDs from Redis at bot startup.")
    else:
        print(f"No audio IDs found to flush on bot startup.")

    return application
