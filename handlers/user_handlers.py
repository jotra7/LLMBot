import logging
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import DEFAULT_MODEL, DEFAULT_SYSTEM_MESSAGE, ADMIN_USER_IDS
from model_cache import get_models
from voice_cache import get_voices, get_default_voice
from database import get_user_conversations, save_conversation
from utils import anthropic_client
from performance_metrics import record_command_usage, record_response_time, record_model_usage, record_error
from queue_system import queue_task
from storage import delete_user_session

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("start")
    user = update.effective_user
    context.user_data['model'] = DEFAULT_MODEL
    models = await get_models()
    voices = await get_voices()
    default_voice = get_default_voice()
    if default_voice:
        context.user_data['voice_id'] = default_voice
    else:
        logger.warning(f"No default voice available for user {user.id}")
        context.user_data['voice_id'] = None
    logger.info(f"User {user.id} started the bot")
    await update.message.reply_html(
        f"Hello {user.mention_html()}! I'm a bot powered by Anthropic and OpenAI.\n"
        f"Your current model is set to {models.get(context.user_data['model'], 'Unknown')}.\n"
        f"Your current voice is set to {voices.get(context.user_data['voice_id'], 'Not set')}.\n"
        "Use /help to see available commands."
    )

async def delete_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("delete_session")
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested session deletion")
    
    delete_user_session(user_id)
    
    # Clear the conversation history in the context
    if 'conversation' in context.user_data:
        del context.user_data['conversation']
    
    await update.message.reply_text("Your session history has been deleted. Your next message will start a new conversation.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("help")
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested help")
    
    is_admin = user_id in ADMIN_USER_IDS
    
    help_text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/delete_session - Delete your current chat session history\n"
        "/listmodels - List available Anthropic models\n"
        "/setmodel - Set the Anthropic model to use\n"
        "/currentmodel - Show the currently selected model\n"
        "/tts <text> - Convert specific text to speech\n"        
        "/video <text> - Make a short video clip (Takes a long time)\n"
        "/img2video - Convert an image to a short video (reply to an image with this command)\n"
        "/listvoices - List available voices\n"
        "/setvoice - Choose a voice for text-to-speech\n"
        "/currentvoice - Show the currently selected voice\n"
        "/history - Show your recent conversations\n"
        "/generate_image <prompt> - Generate an image based on a text prompt\n"
        "/analyze_image - Analyze an image (use this command when sending an image or reply to an image with this command)\n"
        "/set_system_message <message> - Set a custom system message for the AI\n"
        "/get_system_message - Show the current system message\n"
        "/generatesound <description> - Generate a sound based on the provided text description\n"
        "/flux <prompt> - Generate a realistic image using the Flux AI model\n"
        "/list_flux_models - List available Flux AI models\n"
        "/set_flux_model <model_name> - Set the Flux AI model to use\n"
        "/current_flux_model - Show the currently selected Flux AI model\n"

    )
    
    if is_admin:
        admin_help_text = (
            "\n\nAdmin commands:\n"
            "/admin_broadcast <message> - Send a message to all users\n"
            "/admin_user_stats - View user statistics\n"
            "/admin_ban <user_id> - Ban a user\n"
            "/admin_unban <user_id> - Unban a user\n"
            "/admin_set_global_system <message> - Set the global default system message\n"
            "/admin_logs - View recent logs\n"
            "/admin_restart - Restart the bot\n"
            "/admin_update_models - Update the model cache\n"
            "/admin_performance - View performance metrics"
        )
        help_text += admin_help_text
    
    await update.message.reply_text(help_text)

async def get_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("history")
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested conversation history")
    conversations = get_user_conversations(user_id)
    if conversations:
        history = "Your recent conversations:\n\n"
        for conv in conversations:
            history += f"You: {conv['user_message'][:50]}...\n"
            history += f"Bot: {conv['bot_response'][:50]}...\n\n"
        await update.message.reply_text(history)
    else:
        await update.message.reply_text("You don't have any conversation history yet.")

async def set_system_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_system_message")
    if not context.args:
        await update.message.reply_text("Please provide a system message after the /set_system_message command.")
        return

    new_system_message = ' '.join(context.args)
    context.user_data['system_message'] = new_system_message
    logger.info(f"User {update.effective_user.id} set new system message: '{new_system_message[:50]}...'")
    await update.message.reply_text(f"System message updated to: {new_system_message}")

async def get_system_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("get_system_message")
    system_message = context.user_data.get('system_message', DEFAULT_SYSTEM_MESSAGE)
    logger.info(f"User {update.effective_user.id} requested current system message")
    await update.message.reply_text(f"Current system message: {system_message}")

@queue_task('quick')
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user_id = update.effective_user.id
    model = context.user_data.get('model', DEFAULT_MODEL)
    system_message = context.user_data.get('system_message', DEFAULT_SYSTEM_MESSAGE)

    # Check if the message is in a group chat and mentions the bot
    if update.message.chat.type != 'private':
        bot = await context.bot.get_me()
        bot_username = bot.username
        if not f"@{bot_username}" in user_message:
            return
        user_message = user_message.replace(f"@{bot_username}", "").strip()

    logger.info(f"User {user_id} sent message: '{user_message[:50]}...'")
    start_time = time.time()
    
    try:
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=1000,
            system=system_message,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        assistant_response = response.content[0].text
        await update.message.reply_text(assistant_response)

        # Save the conversation
        save_conversation(user_id, user_message, assistant_response)

        # Record performance metrics
        end_time = time.time()
        record_response_time(end_time - start_time)
        record_model_usage(model)

    except Exception as e:
        logger.error(f"Error processing message for user {user_id}: {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}")
        record_error("message_processing_error")