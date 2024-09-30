import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_USER_IDS, DEFAULT_SYSTEM_MESSAGE
from database import get_all_users, get_user_stats, ban_user, unban_user, get_postgres_connection, get_active_users
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


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("admin_broadcast")
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    # Get the full message text after removing the /admin_broadcast command
    message = update.message.text.partition(' ')[2]
    
    if not message:
        await update.message.reply_text("Please provide a message to broadcast.")
        return
    
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
    
    try:
        stats = get_user_stats()
        active_users = get_active_users(7)  # Get users active in the last 7 days

        logger.info(f"Retrieved user stats: {stats}")
        logger.info(f"Retrieved {len(active_users)} active users in the last 7 days")

        stats_message = (
            f"📊 User Statistics:\n\n"
            f"Total Users: {stats['total_users']}\n"
            f"Total Messages: {stats['total_messages']}\n"
            f"Claude Messages: {stats['total_claude_messages']}\n"
            f"GPT Messages: {stats['total_gpt_messages']}\n"
            f"Active Users (24h): {stats['active_users_24h']}\n"
            f"Active Users (7d): {len(active_users)}\n\n"
            f"👥 Top 10 Active Users (Last 7 Days):\n"
        )

        for user in sorted(active_users, key=lambda x: x['total_messages'], reverse=True)[:10]:
            stats_message += (
                f"User ID: {user['id']}\n"
                f"Messages: {user['total_messages']} "
                f"(Claude: {user['total_claude_messages']}, GPT: {user['total_gpt_messages']})\n"
                f"Last Active: {user['last_interaction'].strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )

        # Get top 10 most used commands
        conn = get_postgres_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT command, SUM(count) as total
        FROM command_usage
        GROUP BY command
        ORDER BY total DESC
        LIMIT 10
        ''')
        top_commands = cursor.fetchall()
        conn.close()

        stats_message += "🔝 Top 10 Commands:\n"
        for command, count in top_commands:
            stats_message += f"{command}: {count} times\n"

        # Send the message in chunks if it's too long
        if len(stats_message) > 4096:
            for i in range(0, len(stats_message), 4096):
                await update.message.reply_text(stats_message[i:i+4096])
        else:
            await update.message.reply_text(stats_message)
    except Exception as e:
        logger.error(f"Error in admin_user_stats: {e}")
        await update.message.reply_text(f"An error occurred while retrieving user stats: {e}")
        
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
        with open('./logs/bot.log', 'r') as log_file:
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
        # Save performance data before retrieving metrics
        await save_performance_data()
        
        metrics = get_performance_metrics()
        
        # Extract and format different parts of the metrics
        parts = metrics.split('\n\n')
        response_time = parts[0]
        model_usage = parts[1]
        command_usage = parts[2]
        errors = parts[3]

        # Format the message
        performance_message = (
            f"🚀 Performance Metrics:\n\n"
            f"{response_time}\n\n"
            f"📊 Model Usage:\n{model_usage}\n\n"
            f"🔍 Command Usage:\n{command_usage}\n\n"
            f"❗ Errors:\n{errors}"
        )

        # Send the message in chunks if it's too long
        if len(performance_message) > 4096:
            for i in range(0, len(performance_message), 4096):
                await update.message.reply_text(performance_message[i:i+4096])
        else:
            await update.message.reply_text(performance_message)

    except Exception as e:
        logger.error(f"Error retrieving performance metrics: {str(e)}")
        await update.message.reply_text(f"An error occurred while retrieving performance metrics: {str(e)}")
        
        metrics = get_performance_metrics()
        if not metrics.strip():
            logger.warning("No performance metrics retrieved")
            await update.message.reply_text("No performance metrics available at this time.")
        else:
            await update.message.reply_text(f"Performance metrics:\n\n{metrics}")
    except Exception as e:
        logger.error(f"Error retrieving performance metrics: {str(e)}")
        await update.message.reply_text(f"An error occurred while retrieving performance metrics: {str(e)}")