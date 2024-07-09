import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from config import DEFAULT_MODEL
from model_cache import get_models
from voice_cache import get_voices, get_default_voice
from database import save_conversation, get_user_conversations
from image_processing import generate_image_openai, analyze_image_openai
from tts import generate_speech
from utils import anthropic_client

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    logger.info(f"User {update.effective_user.id} requested help")
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
        "/analyze_image - Analyze an image (use this command when sending an image or reply to an image with this command)"
    )
    await update.message.reply_text(help_text)

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested model list")
    models = await get_models()
    models_text = "Available models:\n" + "\n".join([f"• {name}" for name in models.values()])
    await update.message.reply_text(models_text)

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} initiated model selection")
    models = await get_models()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=model_id)]
        for model_id, name in models.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a model:", reply_markup=reply_markup)

async def current_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = context.user_data.get('model', DEFAULT_MODEL)
    models = await get_models()
    logger.info(f"User {update.effective_user.id} checked current model: {models.get(current, 'Unknown')}")
    await update.message.reply_text(f"Current model: {models.get(current, 'Unknown')}")

async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

async def list_voices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested voice list")
    voices = await get_voices()
    voices_text = "Available voices:\n" + "\n".join([f"• {name}" for name in voices.values()])
    await update.message.reply_text(voices_text)

async def set_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} initiated voice selection")
    voices = await get_voices()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"voice_{voice_id}")]
        for voice_id, name in voices.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a voice:", reply_markup=reply_markup)

async def current_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    # Check if the message is in a group chat and mentions the bot
    if update.message.chat.type != 'private':
        # Get the bot's username
        bot = await context.bot.get_me()
        bot_username = bot.username

        # Check if the message mentions the bot
        if not f"@{bot_username}" in user_message:
            return  # Don't respond if the bot isn't mentioned in a group chat

        # Remove the mention from the message
        user_message = user_message.replace(f"@{bot_username}", "").strip()

    logger.info(f"User {user_id} sent message: '{user_message[:50]}...'")
    try:
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=1000,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        assistant_response = response.content[0].text
        await update.message.reply_text(assistant_response)

        # Save the conversation
        save_conversation(user_id, user_message, assistant_response)

    except Exception as e:
        logger.error(f"Error processing message for user {user_id}: {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}")

    logger.info(f"User {user_id} sent message: '{user_message[:50]}...'")
    try:
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=1000,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        assistant_response = response.content[0].text
        await update.message.reply_text(assistant_response)

        # Save the conversation
        save_conversation(user_id, user_message, assistant_response)

    except Exception as e:
        logger.error(f"Error processing message for user {user_id}: {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}")


async def get_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /generate_image command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {update.effective_user.id} requested image generation: '{prompt[:50]}...'")

    # Send a "upload_photo" action to indicate the bot is processing
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)

    try:
        # Start a background task to keep sending the "upload_photo" action
        async def keep_typing():
            while True:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
                await asyncio.sleep(5)  # Refresh every 5 seconds

        # Start the keep_typing task
        typing_task = asyncio.create_task(keep_typing())

        try:
            image_url = await generate_image_openai(prompt)
            await update.message.reply_photo(photo=image_url, caption=f"Generated image for: {prompt}")
        finally:
            # Ensure the typing indicator is cancelled
            typing_task.cancel()

    except Exception as e:
        logger.error(f"Image generation error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while generating the image: {str(e)}")

async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Check if there's an image in the message or in the reply
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
    else:
        await update.message.reply_text("Please send an image or reply to an image with the /analyze_image command.")
        return

    logger.info(f"User {update.effective_user.id} requested image analysis")

    # Send a "typing" action to indicate the bot is processing
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # Start a background task to keep sending the "typing" action
        async def keep_typing():
            while True:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
                await asyncio.sleep(5)  # Refresh every 5 seconds

        # Start the keep_typing task
        typing_task = asyncio.create_task(keep_typing())

        try:
            file = await context.bot.get_file(photo.file_id)
            file_bytes = await file.download_as_bytearray()
            analysis = await analyze_image_openai(file_bytes)
            await update.message.reply_text(f"Image analysis:\n\n{analysis}")
        finally:
            # Ensure the typing indicator is cancelled
            typing_task.cancel()

    except Exception as e:
        logger.error(f"Image analysis error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while analyzing the image: {str(e)}")
