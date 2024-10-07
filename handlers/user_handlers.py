import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler, CallbackQueryHandler, ContextTypes, 
    MessageHandler, filters
)
from config import DEFAULT_MODEL, DEFAULT_SYSTEM_MESSAGE, ADMIN_USER_IDS, SUPPORT_CHAT_ID
from model_cache import get_models
from voice_cache import get_voices, get_default_voice
from database import get_user_conversations, save_conversation
from utils import anthropic_client
from performance_metrics import record_command_usage, record_response_time, record_model_usage, record_error
from queue_system import queue_task
from database import get_user_conversations, save_conversation, clear_user_conversations, delete_user_session


logger = logging.getLogger(__name__)
CHOOSING, GUIDED_TOUR, BUG_REPORT, BUG_SCREENSHOT = range(4)

# Define help categories
help_categories = {
    'chat': "💬 Chatting with the Bot",
    'session': "🔄 Session Management",
    'gpt': "🤖 GPT Commands",
    'suno':"🎵 Music Generation",
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
        "🎨 I can generate and analyze images, convert text to speech, and even create short video clips!\n"
        "🤖 I now support GPT models for additional AI capabilities!\n\n"
        "💬 To chat with me, simply type your message and send it. Our conversation will be contextual within a session.\n"
        "   You can also use /gpt followed by your message to interact with GPT models.\n\n"
        "🔄 Your session starts now and lasts until you end it or after a period of inactivity. Use /delete_session to end it manually.\n\n"
        "🔧 You can customize my behavior using a system message. "
        f"The current system message is:\n\n\"{context.user_data.get('system_message', DEFAULT_SYSTEM_MESSAGE)}\"\n\n"
        "Use /set_system_message to change it.\n\n"
        "What would you like to do?"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 Guided Tour", callback_data="guided_tour"),
         InlineKeyboardButton("📚 Help Menu", callback_data="help_menu")],
        [InlineKeyboardButton("🎨 Generate Image", callback_data="generate_image"),
         InlineKeyboardButton("🗣️ Text to Speech", callback_data="text_to_speech")],
        [InlineKeyboardButton("💬 Chat Info", callback_data="help_chat"),
         InlineKeyboardButton("🤖 GPT Info", callback_data="help_gpt")],
        [InlineKeyboardButton("🔄 Session Info", callback_data="help_session")]
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_html(welcome_message, reply_markup=reply_markup)
    
    logger.info(f"User {user.id} at start menu")
    return CHOOSING


async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    is_admin = user_id in ADMIN_USER_IDS

    help_text = "📚 Help Menu\n\nChoose a category to learn more:"

    keyboard = []
    for cat, name in help_categories.items():
        if cat != 'admin' or (cat == 'admin' and is_admin):
            keyboard.append([InlineKeyboardButton(name, callback_data=f"help_{cat}")])

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

    category = query.data.split('_', 1)[1]

    logger.info(f"User requested help for category: {category}")

    help_text = get_help_text(category)

    keyboard = [[InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if help_text != "Category not found.":
        await query.edit_message_text(help_text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(f"Category '{category}' not found.", reply_markup=reply_markup)

    return CHOOSING

def get_help_text(category):
    help_texts = {
        'chat': (
            "💬 Chatting with the Bot\n\n"
            "Chatting with me is easy and interactive:\n"
            "• Simply type your message and send it.\n"
            "• Ask questions, seek advice, or chat casually on various topics.\n"
            "• In group chats, mention me (@bot_username) to get my attention.\n"
            "• Our conversation is contextual within the current session.\n"
            "• Use commands during our chat for specific tasks.\n"
            "• Use /gpt followed by your message to chat with GPT models.\n\n"
            "Start chatting to explore my capabilities!"
        ),
         'session': (
            "🔄 Session Management\n\n"
            "Understanding sessions enhances our interaction:\n"
            "• A session starts when you begin chatting and maintains context.\n"
            "• Sessions are user-specific and private.\n"
            "• They typically last for a few hours of inactivity.\n"
            "• Use /delete_session to manually end a session and clear context.\n"
            "• Starting a new session gives you a fresh start.\n\n"
            "Effective session management ensures more relevant interactions!"
        ),
        'conversation': (
            "🗨️ Conversation Customization\n\n"
            "Tailor our interactions to your preferences:\n"
            "• /set_system_message - Customize my behavior and personality.\n"
            "• /get_system_message - View the current system message.\n\n"
            "A custom system message can significantly influence my responses!"
        ),
                
        'suno': (
            "🎵 Music Generation\n\n"
            "Make your own song (Limited to 5 per day):\n"
            "• /generate_music <prompt>  - create a song based on your prompt\n"
            "• /generate_instrumental <prompt>  - create an instrumental song based on your prompt\n"
            "• /custom_generate_music - Start a guided process to create a custom song with lyrics or instrumental music.\n"

        ),
        'ai_models': (
            "🧠 AI Models\n\n"
            "Choose the AI model that suits your needs:\n"
            "• /list_models - View available Claude AI models.\n"
            "• /set_model - Change the active Claude AI model.\n"
            "• /current_model - Check the current Claude model in use.\n"
            "• /list_gpt_models - View available GPT models.\n"
            "• /set_gpt_model - Choose a GPT model to use.\n"
            "• /current_gpt_model - Check the current GPT model in use.\n\n"
            "Experiment with different models for varied interactions!"
        ),
        'gpt': (
            "🤖 GPT Commands\n\n"
            "Interact with OpenAI's GPT models:\n"
            "• /gpt <message> - Send a message to the current GPT model.\n"
            "• /list_gpt_models - View all available GPT models.\n"
            "• /set_gpt_model - Choose a specific GPT model to use.\n"
            "• /current_gpt_model - Check which GPT model is currently active.\n\n"
            "GPT models offer powerful language understanding and generation capabilities!"
        ),
        'tts': (
            "🎙️ Text-to-Speech\n\n"
            "Convert text to spoken words:\n"
            "• /tts <text> - Generate speech from text.\n"
            "• /list_voices - View available voice options.\n"
            "• /set_voice - Choose a preferred voice.\n"
            "• /current_voice - Check the active voice setting.\n"
            "• /generate_sound <description> - Create custom sound effects.\n"
            "• /add_voice - Add a custom voice (one per user).\n"
            "• /delete_custom_voice - Delete your custom voice.\n\n"
            "Bring text to life with various voices and sounds!"
        ),
        'image_gen': (
            "🎨 Image Generation\n\n"
            "Create visual content with various AI models:\n"
            "• /generate_image <prompt> - Create images with DALL-E 3.\n"
            "• /flux <prompt> - Generate realistic images using Flux AI.\n"
            "• /leo <prompt> - Create images with Leonardo.ai.\n"
            "• /photomaker - Create personalized images based on your photos.\n"
            "• /photomaker_style - Transform your photos with creative styles and prompts.\n"
            "• /become_image - Transform your photo to mimic the style of another image or artwork.\n"
            "• /san_andreas - Make images in the style of GTA.\n"
            "• /list_flux_models or /list_leonardo_models - View model options.\n"
            "• /set_flux_model or /set_leonardo_model - Select a specific model.\n"
            "• /current_flux_model or /current_leonardo_model - Check active models.\n"
            "• /remove_bg - Reply to any image with the command to remove the background.\n"
            "\n"
            "🌟 New Features:\n"
            "- photomaker_style: Upload up to 4 images and add a creative prompt to generate unique artwork.\n"
            "- upscale: Upscale an image uup to 5x.\n"
            "- become_image: Transform your photo to match the style of any artwork or image.\n"
            "\n"
            "Let your imagination run wild with our expanded AI-powered image creation tools!"
        ),
        'video_gen': (
            "🎥 Video Generation\n\n"
            "Create short video clips:\n"
            "• /video <prompt> - Generate a video from a text description.\n"
            "• /img2video - Convert a static image into a short video.\n\n"
            "Bring your ideas to life with AI-generated videos!"
        ),
        'image_analysis': (
            "🔍 Image Analysis\n\n"
            "Get detailed descriptions of images:\n"
            "• Upload or send an image.\n"
            "• Reply to the image with /analyze_image.\n"
            "I'll provide a comprehensive description, including detected objects and features.\n\n"
            "Gain insights into visual content with AI-powered analysis!"
        ),
        'user_data': (
            "📊 User Data Management\n\n"
            "Manage your interaction data:\n"
            "• /history - View your recent chat history.\n"
            "• /delete_session - Clear your current session data.\n\n"
            "Stay in control of your data and interaction history!"
        ),
        'other': (
            "ℹ️ Other Commands\n\n"
            "Additional useful commands:\n"
            "• /start - Display the welcome message and main menu.\n"
            "• /help - Access this help menu.\n"
            "• /queue_status - Check the current task queue status.\n"
            "• /bug - Report a bug or issue with the bot.\n\n"
            "These commands help you navigate and utilize all my features efficiently!"
        ),
        'admin': (
            "🛠️ Admin Commands\n\n"
            "Manage the bot (admin access required):\n"
            "• /admin_broadcast - Send a message to all users.\n"
            "• /admin_user_stats - View user statistics.\n"
            "• /admin_ban or /admin_unban - Manage user access.\n"
            "• /admin_set_global_system - Set the default system message.\n"
            "• /admin_logs - View recent bot logs.\n"
            "• /admin_restart - Reboot the bot.\n"
            "• /admin_update_models - Refresh the model cache.\n"
            "• /admin_performance - View performance metrics.\n\n"
            "Efficiently manage and monitor bot operations!"
        )
    }
    return help_texts.get(category, "Category not found. Use /help to see available categories.")

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
    elif query.data == "generate_image":
        help_text = get_help_text('image_gen')
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        return CHOOSING
    elif query.data == "text_to_speech":
        help_text = get_help_text('tts')
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        return CHOOSING
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
            await query.edit_message_text(admin_panel_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        else:
            await query.edit_message_text("You don't have permission to access the admin panel.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        return CHOOSING
    elif query.data == "start":
        return await start(update, context)
    else:
        await query.edit_message_text("I'm not sure how to handle that request. Please try using a command from the /help list.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        return CHOOSING

async def delete_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("delete_session")
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested session deletion")

    delete_user_session(user_id)
    clear_user_conversations(user_id)

    # Clear the conversation history in the context
    if 'conversation' in context.user_data:
        del context.user_data['conversation']
    
    # Clear GPT-specific conversation history
    if 'gpt_conversation' in context.user_data:
        del context.user_data['gpt_conversation']

    # Reset model to default
    context.user_data['model'] = DEFAULT_MODEL

    # Reset system message to default
    context.user_data['system_message'] = DEFAULT_SYSTEM_MESSAGE

    await update.message.reply_text("Your session history has been deleted for both Claude and GPT. Your next message will start a new conversation.")

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
    # Check if we're in the middle of a bug report
    if context.user_data.get('expecting_bug_report'):
        return await receive_bug_report(update, context)
    user_name = update.effective_user.username      
    user_message = update.message.text
    user_id = update.effective_user.id
    model = context.user_data.get('model', DEFAULT_MODEL)
    system_message = context.user_data.get('system_message', DEFAULT_SYSTEM_MESSAGE)

    # Check if the message is in a group chat and mentions the bot
    if update.message.chat.type != 'private':
        bot = await context.bot.get_me()
        bot_username = bot.username
        if f"@{bot_username}" not in user_message:
            return
        user_message = user_message.replace(f"@{bot_username}", "").strip()

    logger.info(f"User {user_name}({user_id}) sent message: '{user_message[:50]}...'")
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
        logger.error(f"Error processing message for user {user_id}: {e}")
        await update.message.reply_text(f"An error occurred: {e}")
        record_error("message_processing_error")

async def bug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Please describe the bug you've encountered. If you want to include a screenshot, you can send it after your description.")
    context.user_data['expecting_bug_report'] = True
    return BUG_REPORT

async def receive_bug_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['bug_report'] = update.message.text
    context.user_data['expecting_bug_report'] = False
    await update.message.reply_text("Thank you for your report. You can now send a screenshot if you have one, or use /skip if you don't.")
    return BUG_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.document:
        file = await update.message.document.get_file()
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
    else:
        await update.message.reply_text("Please send an image file or use /skip if you don't have a screenshot.")
        return BUG_SCREENSHOT

    context.user_data['screenshot'] = file
    return await send_bug_report(update, context)

async def skip_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_bug_report(update, context)

async def send_bug_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    bug_report = context.user_data['bug_report']
    screenshot = context.user_data.get('screenshot')

    report_message = f"Bug Report from {user.mention_html()}:\n\n{bug_report}"

    try:
        if screenshot:
            await context.bot.send_photo(
                chat_id=SUPPORT_CHAT_ID,
                photo=screenshot.file_id,
                caption=report_message,
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=SUPPORT_CHAT_ID,
                text=report_message,
                parse_mode='HTML'
            )
        logger.info(f"Bug report from user {user.id} sent to support channel")
    except Exception as e:
        logger.error(f"Failed to send bug report to support channel: {str(e)}")
        await update.message.reply_text("An error occurred while sending your bug report. Please try again later.")
        return ConversationHandler.END

    await update.message.reply_text("Thank you for your bug report. It has been sent to our support team.")
    return ConversationHandler.END

async def cancel_bug_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['expecting_bug_report'] = False
    await update.message.reply_text("Bug report cancelled.")
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        CommandHandler("help", help_menu),
        CommandHandler("bug", bug_command),
    ],
    states={
        CHOOSING: [
            CallbackQueryHandler(button_callback),
        ],
        GUIDED_TOUR: [
            CallbackQueryHandler(guided_tour, pattern="^tour_"),
        ],
        BUG_REPORT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bug_report),
        ],
        BUG_SCREENSHOT: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_screenshot),
            CommandHandler("skip", skip_screenshot),
        ],
    },
    fallbacks=[
        CommandHandler("start", start),
        CommandHandler("help", help_menu),
        CommandHandler("cancel", cancel_bug_report),
    ]
)

__all__ = [
    'start',
    'help_menu',
    'show_help_category',
    'get_help_text',
    'guided_tour',
    'button_callback',
    'delete_session_command',
    'get_history',
    'set_system_message',
    'get_system_message',
    'handle_message',
    'bug_command',
    'receive_bug_report',
    'receive_screenshot',
    'skip_screenshot',
    'send_bug_report',
    'cancel_bug_report',
    'conv_handler',
]