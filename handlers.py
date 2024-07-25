import asyncio
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from config import ADMIN_USER_IDS, DEFAULT_MODEL, DEFAULT_SYSTEM_MESSAGE
from model_cache import get_models
from voice_cache import get_voices, get_default_voice
from database import save_conversation, get_user_conversations, get_all_users, ban_user, unban_user
from image_processing import generate_image_openai, analyze_image_openai
from tts import generate_speech
from utils import anthropic_client
from performance_metrics import record_response_time, record_model_usage, record_command_usage, record_error, get_performance_metrics

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("help")
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested help")
    
    is_admin = user_id in ADMIN_USER_IDS
    
    help_text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/listmodels - List available Anthropic models\n"
        "/setmodel - Set the Anthropic model to use\n"
        "/currentmodel - Show the currently selected model\n"
        "/tts <text> - Convert specific text to speech\n"
        "/listvoices - List available voices\n"
        "/setvoice - Choose a voice for text-to-speech\n"
        "/currentvoice - Show the currently selected voice\n"
        "/history - Show your recent conversations\n"
        "/generate_image <prompt> - Generate an image based on a text prompt\n"
        "/analyze_image - Analyze an image (use this command when sending an image or reply to an image with this command)\n"
        "/set_system_message <message> - Set a custom system message for the AI\n"
        "/get_system_message - Show the current system message"
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

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_models")
    logger.info(f"User {update.effective_user.id} requested model list")
    models = await get_models()
    models_text = "Available models:\n" + "\n".join([f"• {name}" for name in models.values()])
    await update.message.reply_text(models_text)

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_model")
    logger.info(f"User {update.effective_user.id} initiated model selection")
    models = await get_models()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=model_id)]
        for model_id, name in models.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a model:", reply_markup=reply_markup)

async def current_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_model")
    current = context.user_data.get('model', DEFAULT_MODEL)
    models = await get_models()
    logger.info(f"User {update.effective_user.id} checked current model: {models.get(current, 'Unknown')}")
    await update.message.reply_text(f"Current model: {models.get(current, 'Unknown')}")

async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("tts")
    if not context.args:
        await update.message.reply_text("Please provide some text after the /tts command.")
        return

    text = ' '.join(context.args)
    voice_id = context.user_data.get('voice_id')

    if not voice_id:
        await update.message.reply_text("No voice is set for text-to-speech. Please use the /setvoice command first.")
        return

    logger.info(f"User {update.effective_user.id} requested TTS: '{text[:50]}...'")
    try:
        audio_content = generate_speech(text, voice_id)
        await update.message.reply_voice(audio_content)
    except Exception as e:
        logger.error(f"TTS error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while generating speech: {str(e)}")
        record_error("tts_error")

async def list_voices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_voices")
    logger.info(f"User {update.effective_user.id} requested voice list")
    voices = await get_voices()
    voices_text = "Available voices:\n" + "\n".join([f"• {name}" for name in voices.values()])
    await update.message.reply_text(voices_text)

async def set_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_voice")
    logger.info(f"User {update.effective_user.id} initiated voice selection")
    voices = await get_voices()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"voice_{voice_id}")]
        for voice_id, name in voices.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a voice:", reply_markup=reply_markup)

async def current_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_voice")
    current = context.user_data.get('voice_id', get_default_voice())
    voices = await get_voices()
    logger.info(f"User {update.effective_user.id} checked current voice: {voices.get(current, 'Unknown')}")
    await update.message.reply_text(f"Current voice: {voices.get(current, 'Unknown')}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("voice_"):
        voice_id = query.data.split("_")[1]
        context.user_data['voice_id'] = voice_id
        voices = await get_voices()
        logger.info(f"User {update.effective_user.id} set voice to {voices.get(voice_id, 'Unknown')}")
        await query.edit_message_text(f"Voice set to {voices.get(voice_id, 'Unknown')}")
    else:
        # Handle model selection
        chosen_model = query.data
        context.user_data['model'] = chosen_model
        models = await get_models()
        logger.info(f"User {update.effective_user.id} set model to {models.get(chosen_model, 'Unknown')}")
        await query.edit_message_text(f"Model set to {models.get(chosen_model, 'Unknown')}")

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

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_image")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /generate_image command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {update.effective_user.id} requested image generation: '{prompt[:50]}...'")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)

    start_time = time.time()
    try:
        async def keep_typing():
            while True:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
                await asyncio.sleep(5)

        typing_task = asyncio.create_task(keep_typing())

        try:
            image_url = await generate_image_openai(prompt)
            await update.message.reply_photo(photo=image_url, caption=f"Generated image for: {prompt}")
        finally:
            typing_task.cancel()

        end_time = time.time()
        record_response_time(end_time - start_time)

    except Exception as e:
        logger.error(f"Image generation error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while generating the image: {str(e)}")
        record_error("image_generation_error")

async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("analyze_image")
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
    else:
        await update.message.reply_text("Please send an image or reply to an image with the /analyze_image command.")
        return

    logger.info(f"User {update.effective_user.id} requested image analysis")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    start_time = time.time()
    try:
        async def keep_typing():
            while True:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
                await asyncio.sleep(5)

        typing_task = asyncio.create_task(keep_typing())

        try:
            file = await context.bot.get_file(photo.file_id)
            file_bytes = await file.download_as_bytearray()
            analysis = await analyze_image_openai(file_bytes)
            await update.message.reply_text(f"Image analysis:\n\n{analysis}")
        finally:
            typing_task.cancel()

        end_time = time.time()
        record_response_time(end_time - start_time)

    except Exception as e:
        logger.error(f"Image analysis error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while analyzing the image: {str(e)}")
        record_error("image_analysis_error")

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

# Admin commands

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
    
    users = get_all_users()
    total_users = len(users)
    # You might want to add more detailed statistics here
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
    
    metrics = get_performance_metrics()
    await update.message.reply_text(f"Performance metrics:\n\n{metrics}")

# You might want to add a function to handle messages when the bot is in a group
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # This function would be similar to handle_message, but with group-specific logic
    pass

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")
    record_error(str(context.error))

    # Send message to developer
    developer_chat_id = ADMIN_USER_IDS[0]  # Assuming the first admin ID is the developer
    await context.bot.send_message(
        chat_id=developer_chat_id,
        text=f"An error occurred: {context.error}"
    )

    # Inform user
    if update.effective_message:
        await update.effective_message.reply_text("An error occurred while processing your request. The developer has been notified.")
    
    