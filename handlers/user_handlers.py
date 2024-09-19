import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, CallbackQueryHandler, ContextTypes
from config import DEFAULT_MODEL, DEFAULT_SYSTEM_MESSAGE, ADMIN_USER_IDS
from model_cache import get_models
from voice_cache import get_voices, get_default_voice
from database import get_user_conversations, save_conversation
from utils import anthropic_client
from performance_metrics import record_command_usage, record_response_time, record_model_usage, record_error
from queue_system import queue_task
from storage import delete_user_session

logger = logging.getLogger(__name__)
CHOOSING, GUIDED_TOUR = range(2)

# Define help categories
help_categories = {
    'conversation': "🗨️ Conversation",
    'ai_models': "🧠 AI Models",
    'tts': "🎙️ Text-to-Speech",
    'image_gen': "🎨 Image Generation",
    'video_gen': "🎥 Video Generation",
    'image_analysis': "🔍 Image Analysis",
    'user_data': "📊 User Data",
    'other': "ℹ️ Other Commands",
    'admin': "🛠️ Admin Commands"
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    context.user_data['model'] = DEFAULT_MODEL
    is_admin = user.id in ADMIN_USER_IDS

    welcome_message = (
        f"👋 Welcome, {user.mention_html()}! I'm a multi-functional AI assistant bot.\n\n"
        "🧠 I can engage in conversations, answer questions, and help with various tasks.\n"
        "🎨 I can generate and analyze images, convert text to speech, and even create short video clips!\n\n"
        "🔧 You can customize my behavior using a system message. "
        f"The current system message is:\n\n\"{context.user_data.get('system_message', DEFAULT_SYSTEM_MESSAGE)}\"\n\n"
        "Use /set_system_message to change it.\n\n"
        "Would you like a guided tour of my features or to see the help menu?"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 Guided Tour", callback_data="guided_tour")],
        [InlineKeyboardButton("📚 Help Menu", callback_data="help_menu")],
        [InlineKeyboardButton("🎨 Generate Image", callback_data="generate_image")],
        [InlineKeyboardButton("🗣️ Text to Speech", callback_data="text_to_speech")]
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(welcome_message, reply_markup=reply_markup)
    logger.info(f"User {user.id} started the bot")
    return CHOOSING

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    is_admin = user_id in ADMIN_USER_IDS

    help_text = "📚 Help Menu\n\nChoose a category to learn more:"

    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"help_{cat}")] 
        for cat, name in help_categories.items() 
        if cat != 'admin' or (cat == 'admin' and is_admin)
    ]
    keyboard.append([InlineKeyboardButton("🔙 Back to Start", callback_data="start")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(help_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(help_text, reply_markup=reply_markup)

    logger.info(f"User {user_id} opened help menu")
    return CHOOSING

async def show_help_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    category = query.data.split('_')[1]
    help_text = get_help_text(category)

    keyboard = [[InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(help_text, reply_markup=reply_markup)
    return CHOOSING

def get_help_text(category):
    help_texts = {
        'conversation': (
            "🗨️ Conversation\n\n"
            "• Simply send a message to chat with me\n"
            "• /set_system_message - Customize my behavior\n"
            "• /get_system_message - View current system message\n\n"
            "The system message helps define my personality and behavior. "
            "You can set it to make me more formal, casual, or even role-play as a specific character!"
        ),
        'ai_models': (
            "🧠 AI Models\n\n"
            "• /listmodels - View available AI models\n"
            "• /setmodel - Change the AI model\n"
            "• /currentmodel - Check current model\n\n"
            "Different models have different capabilities and specialties. "
            "Experiment to find the one that works best for your needs!"
        ),
        'tts': (
            "🎙️ Text-to-Speech\n\n"
            "• /tts <text> - Convert text to speech\n"
            "• /listvoices - View available voices\n"
            "• /setvoice - Choose a voice\n"
            "• /currentvoice - Check current voice\n\n"
            "You can have me speak in different voices. Try them out to find your favorite!"
        ),
        'image_gen': (
            "🎨 Image Generation\n\n"
            "• /generate_image <prompt> - Create image from text\n"
            "• /flux <prompt> - Generate realistic image\n"
            "• /list_flux_models - View Flux AI models\n"
            "• /set_flux_model - Set Flux AI model\n"
            "• /current_flux_model - Check current Flux model\n\n"
            "Let your imagination run wild! Describe any scene or object, and I'll create it for you."
        ),
        'video_gen': (
            "🎥 Video Generation\n\n"
            "• /video <prompt> - Create short video clip\n"
            "• /img2video - Convert image to video\n\n"
            "Bring your ideas to life with short animated clips or turn still images into videos!"
        ),
        'image_analysis': (
            "🔍 Image Analysis\n\n"
            "• /analyze_image - Analyze an image (reply to an image)\n\n"
            "Send me any image, and I'll describe what I see in detail."
        ),
        'user_data': (
            "📊 User Data\n\n"
            "• /history - View your chat history\n"
            "• /delete_session - Clear your current session\n\n"
            "Manage your data and conversation history with these commands."
        ),
        'other': (
            "ℹ️ Other Commands\n\n"
            "• /start - Welcome message and quick actions\n"
            "• /help - Display this help message\n\n"
            "These commands help you navigate the bot's features."
        ),
        'admin': (
            "🛠️ Admin Commands\n\n"
            "• /admin_broadcast - Send message to all users\n"
            "• /admin_user_stats - View user statistics\n"
            "• /admin_ban - Ban a user\n"
            "• /admin_unban - Unban a user\n"
            "• /admin_set_global_system - Set global system message\n"
            "• /admin_logs - View recent logs\n"
            "• /admin_restart - Restart the bot\n"
            "• /admin_update_models - Update model cache\n"
            "• /admin_performance - View performance metrics\n\n"
            "These commands are only available to bot administrators."
        )
    }
    return help_texts.get(category, "Category not found.")

async def guided_tour(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    tour_steps = [
        ("Welcome to the guided tour! Let's explore my main features.", [
            InlineKeyboardButton("▶️ Start Tour", callback_data="tour_1"),
            InlineKeyboardButton("🔙 Back to Start", callback_data="start")
        ]),
        ("1️⃣ Conversation: Just send me a message, and I'll respond! You can also customize my behavior with /set_system_message.", [
            InlineKeyboardButton("◀️ Previous", callback_data="tour_0"),
            InlineKeyboardButton("▶️ Next", callback_data="tour_2")
        ]),
        ("2️⃣ Image Generation: Use /generate_image followed by a description to create unique images.", [
            InlineKeyboardButton("◀️ Previous", callback_data="tour_1"),
            InlineKeyboardButton("▶️ Next", callback_data="tour_3")
        ]),
        ("3️⃣ Text-to-Speech: Convert text to speech with /tts. You can even choose different voices!", [
            InlineKeyboardButton("◀️ Previous", callback_data="tour_2"),
            InlineKeyboardButton("▶️ Next", callback_data="tour_4")
        ]),
        ("4️⃣ Video Generation: Create short video clips with /video followed by a description.", [
            InlineKeyboardButton("◀️ Previous", callback_data="tour_3"),
            InlineKeyboardButton("▶️ Next", callback_data="tour_5")
        ]),
        ("5️⃣ Image Analysis: Send me an image or use /analyze_image to get a detailed description of any picture.", [
            InlineKeyboardButton("◀️ Previous", callback_data="tour_4"),
            InlineKeyboardButton("▶️ Finish Tour", callback_data="tour_end")
        ]),
        ("Tour completed! You now know my main features. Feel free to explore more in the help menu or just start chatting!", [
            InlineKeyboardButton("📚 Help Menu", callback_data="help_menu"),
            InlineKeyboardButton("🔙 Back to Start", callback_data="start")
        ])
    ]

    step = int(query.data.split('_')[1]) if query.data.startswith("tour_") else 0
    text, buttons = tour_steps[step]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([buttons]))
    return GUIDED_TOUR if step < len(tour_steps) - 1 else CHOOSING

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "help_menu":
        return await help_menu(update, context)
    elif query.data.startswith("help_"):
        return await show_help_category(update, context)
    elif query.data == "guided_tour":
        return await guided_tour(update, context)
    elif query.data.startswith("tour_"):
        return await guided_tour(update, context)
    elif query.data == "start":
        return await start(update, context)
    elif query.data == "generate_image":
        await query.edit_message_text("To generate an image, use the command:\n/generate_image <your image description>")
    elif query.data == "text_to_speech":
        await query.edit_message_text("To convert text to speech, use the command:\n/tts <your text>")
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
            await query.edit_message_text(admin_panel_text)
        else:
            await query.edit_message_text("You don't have permission to access the admin panel.")
    else:
        await query.edit_message_text("I'm not sure how to handle that request. Please try using a command from the /help list.")
    
    return CHOOSING

async def delete_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("delete_session")
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested session deletion")
    
    delete_user_session(user_id)
    
    # Clear the conversation history in the context
    if 'conversation' in context.user_data:
        del context.user_data['conversation']
    
    await update.message.reply_text("Your session history has been deleted. Your next message will start a new conversation.")


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

conv_handler = ConversationHandler(per_message=True,
    entry_points=[CommandHandler("start", start), CommandHandler("help", help_menu)],
    states={
        CHOOSING: [
            CallbackQueryHandler(button_callback),
        ],
        GUIDED_TOUR: [
            CallbackQueryHandler(guided_tour, pattern="^tour_"),
            CallbackQueryHandler(button_callback),
        ],
    },
    fallbacks=[CommandHandler("start", start)],
)
