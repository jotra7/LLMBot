import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    user = update.effective_user
    context.user_data['model'] = DEFAULT_MODEL
    is_admin = user.id in ADMIN_USER_IDS

    welcome_message = (
        f"👋 Welcome, {user.mention_html()}! I'm a multi-functional AI assistant bot.\n\n"
        "🧠 I can engage in conversations, answer questions, and help with various tasks.\n"
        "🎨 I can generate and analyze images, convert text to speech, and even create short video clips!\n\n"
        "Here are some things you can do:\n"
        "• Simply send me a message to start a conversation\n"
        "• Use /help to see all available commands\n"
        "• Try /generate_image to create images from text descriptions\n"
        "• Use /tts to convert text to speech\n\n"
        "Feel free to explore and don't hesitate to ask if you need any assistance!"
    )

    keyboard = [
        [InlineKeyboardButton("📚 View All Commands", callback_data="view_commands")],
        [InlineKeyboardButton("🎨 Generate Image", callback_data="generate_image")],
        [InlineKeyboardButton("🗣️ Text to Speech", callback_data="text_to_speech")]
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(welcome_message, reply_markup=reply_markup)
    logger.info(f"User {user.id} started the bot")

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
    user_id = update.effective_user.id
    is_admin = user_id in ADMIN_USER_IDS

    help_text = (
        "🤖 Bot Commands and Capabilities 🤖\n\n"
        "🗨️ Conversation:\n"
        "• Simply send a message to chat with me\n"
        "• /set_system_message - Customize my behavior\n"
        "• /get_system_message - View current system message\n\n"

        "🧠 AI Models:\n"
        "• /listmodels - View available AI models\n"
        "• /setmodel - Change the AI model\n"
        "• /currentmodel - Check current model\n\n"

        "🎙️ Text-to-Speech:\n"
        "• /tts <text> - Convert text to speech\n"
        "• /listvoices - View available voices\n"
        "• /setvoice - Choose a voice\n"
        "• /currentvoice - Check current voice\n\n"

        "🎨 Image Generation:\n"
        "• /generate_image <prompt> - Create image from text\n"
        "• /flux <prompt> - Generate realistic image\n"
        "• /list_flux_models - View Flux AI models\n"
        "• /set_flux_model - Set Flux AI model\n"
        "• /current_flux_model - Check current Flux model\n\n"

        "🎥 Video Generation:\n"
        "• /video <prompt> - Create short video clip\n"
        "• /img2video - Convert image to video\n\n"

        "🔍 Image Analysis:\n"
        "• /analyze_image - Analyze an image (reply to an image)\n\n"

        "📊 User Data:\n"
        "• /history - View your chat history\n"
        "• /delete_session - Clear your current session\n\n"

        "ℹ️ Other Commands:\n"
        "• /start - Welcome message and quick actions\n"
        "• /help - Display this help message\n"
    )

    if is_admin:
        admin_help = (
            "\n🛠️ Admin Commands:\n"
            "• /admin_broadcast - Send message to all users\n"
            "• /admin_user_stats - View user statistics\n"
            "• /admin_ban - Ban a user\n"
            "• /admin_unban - Unban a user\n"
            "• /admin_set_global_system - Set global system message\n"
            "• /admin_logs - View recent logs\n"
            "• /admin_restart - Restart the bot\n"
            "• /admin_update_models - Update model cache\n"
            "• /admin_performance - View performance metrics\n"
        )
        help_text += admin_help

    keyboard = [
        [InlineKeyboardButton("🎨 Generate Image", callback_data="generate_image")],
        [InlineKeyboardButton("🗣️ Text to Speech", callback_data="text_to_speech")],
        [InlineKeyboardButton("🎥 Generate Video", callback_data="generate_video")]
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)
    logger.info(f"User {user_id} requested help")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "view_commands":
        await help_command(update, context)
    elif query.data == "generate_image":
        await query.message.reply_text("To generate an image, use the command:\n/generate_image <your image description>")
    elif query.data == "text_to_speech":
        await query.message.reply_text("To convert text to speech, use the command:\n/tts <your text>")
    elif query.data == "generate_video":
        await query.message.reply_text("To generate a video, use the command:\n/video <your video description>")
    elif query.data == "admin_panel":
        if update.effective_user.id in ADMIN_USER_IDS:
            admin_panel_text = (
                "🛠️ Admin Panel 🛠️\n\n"
                "Here are your admin capabilities:\n"
                "• /admin_broadcast - Send a message to all users\n"
                "• /admin_user_stats - View user statistics\n"
                "• /admin_ban - Ban a user\n"
                "• /admin_unban - Unban a user\n"
                "• /admin_set_global_system - Set the global system message\n"
                "• /admin_logs - View recent logs\n"
                "• /admin_restart - Restart the bot\n"
                "• /admin_update_models - Update the model cache\n"
                "• /admin_performance - View performance metrics"
            )
            await query.message.reply_text(admin_panel_text)
        else:
            await query.message.reply_text("You don't have permission to access the admin panel.")
    else:
        await query.message.reply_text("I'm not sure how to handle that request. Please try using a command from the /help list.")
        
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