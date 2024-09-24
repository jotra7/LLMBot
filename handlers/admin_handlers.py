import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_USER_IDS, DEFAULT_SYSTEM_MESSAGE
from database import get_all_users, get_user_count, ban_user, unban_user
from performance_metrics import record_command_usage, get_performance_metrics, save_performance_data
from model_cache import update_model_cache

logger = logging.getLogger(__name__)


async def on_startup(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Bot has fully started. Notifying admins...")
    for admin_id in ADMIN_USER_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text="🚀 Bot has successfully started! You are registered as an admin."
            )
            logger.info(f"Sent startup notification to admin {admin_id}")
        except Exception as e:
            logger.error(f"Failed to send startup notification to admin {admin_id}: {e}")

async def notify_admins(context: ContextTypes.DEFAULT_TYPE):
    for admin_id in ADMIN_USER_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
#                text="🚀 Bot has started! You are registered as an admin."
            )
            logger.info(f"Sent startup notification to admin {admin_id}")
        except Exception as e:
            logger.error(f"Failed to send startup notification to admin {admin_id}: {e}")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_broadcast")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if not context.args:
        await update.message.reply_text("Please provide a message to broadcast.")
        return
    
    message = ' '.join(context.args)
    users = get_all_users()
    success_count = 0
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id}: {str(e)}")
    
    await update.message.reply_text(f"Broadcast sent to {success_count}/{len(users)} users.")

async def admin_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_user_stats")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    total_users = get_user_count()
    await update.message.reply_text(f"Total users: {total_users}")

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_ban_user")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Please provide a valid user ID to ban.")
        return
    
    user_id = int(context.args[0])
    if ban_user(user_id):
        await update.message.reply_text(f"User {user_id} has been banned.")
    else:
        await update.message.reply_text(f"Failed to ban user {user_id}.")

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_unban_user")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Please provide a valid user ID to unban.")
        return
    
    user_id = int(context.args[0])
    if unban_user(user_id):
        await update.message.reply_text(f"User {user_id} has been unbanned.")
    else:
        await update.message.reply_text(f"Failed to unban user {user_id}.")

async def admin_set_global_system_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_set_global_system_message")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if not context.args:
        await update.message.reply_text("Please provide a new global system message.")
        return
    
    new_message = ' '.join(context.args)
    global DEFAULT_SYSTEM_MESSAGE
    DEFAULT_SYSTEM_MESSAGE = new_message
    await update.message.reply_text(f"Global system message updated to: {new_message}")

async def admin_view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_view_logs")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    try:
        with open('bot.log', 'r') as log_file:
            logs = log_file.read()[-4000:]  # Get last 4000 characters
        await update.message.reply_text(f"Recent logs:\n\n{logs}")
    except Exception as e:
        await update.message.reply_text(f"Failed to read logs: {str(e)}")

async def admin_restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_restart_bot")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    await update.message.reply_text("Restarting the bot...")
    # You'll need to implement the actual restart logic elsewhere
    # This might involve exiting the script and having a separate process manager restart it

async def admin_update_model_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_update_model_cache")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    await update.message.reply_text("Updating model cache...")
    try:
        await update_model_cache()
        await update.message.reply_text("Model cache updated successfully.")
    except Exception as e:
        await update.message.reply_text(f"Failed to update model cache: {str(e)}")

async def admin_performance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_performance")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    try:
        # Force a save of current performance data
        save_performance_data()
        
        metrics = get_performance_metrics()
        if not metrics.strip():
            logger.warning("No performance metrics retrieved")
            await update.message.reply_text("No performance metrics available at this time.")
        else:
            await update.message.reply_text(f"Performance metrics:\n\n{metrics}")
    except Exception as e:
        logger.error(f"Error retrieving performance metrics: {str(e)}")
        await update.message.reply_text(f"An error occurred while retrieving performance metrics: {str(e)}")