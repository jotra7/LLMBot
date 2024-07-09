import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import anthropic
import openai
import requests
import io
from datetime import timedelta
from config import TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, DEFAULT_MODEL, OPENAI_API_KEY
from model_cache import get_models, update_model_cache
from voice_cache import get_voices, update_voice_cache, periodic_voice_cache_update, get_default_voice
from database import init_db, save_conversation, get_user_conversations

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = openai(api_key=OPENAI_API_KEY)

# Initialize the database
init_db()

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
        "/analyze_image - Analyze an image (send this command as a caption with an image)"
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

def generate_speech(text, voice_id):
    if not voice_id:
        raise ValueError("No voice ID set. Please set a voice using /setvoice command.")
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return io.BytesIO(response.content)

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

    logger.info(f"User {user_id} sent message: '{user_message[:50]}...'")
    try:
        response = client.messages.create(
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

    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        await update.message.reply_photo(photo=image_url, caption=f"Generated image for: {prompt}")
    except Exception as e:
        logger.error(f"Image generation error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while generating the image: {str(e)}")

async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.photo:
        await update.message.reply_text("Please send an image with this command as the caption.")
        return

    logger.info(f"User {update.effective_user.id} requested image analysis")

    try:
        # Get the largest available photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_bytes = await file.download_as_bytearray()

        response = openai_client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{file_bytes.decode('utf-8')}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=300,
        )
        analysis = response.choices[0].message.content
        await update.message.reply_text(f"Image analysis:\n\n{analysis}")
    except Exception as e:
        logger.error(f"Image analysis error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while analyzing the image: {str(e)}")

async def periodic_cache_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Performing periodic cache update")
    await update_model_cache()

def create_application():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("listmodels", list_models))
    application.add_handler(CommandHandler("setmodel", set_model))
    application.add_handler(CommandHandler("currentmodel", current_model))
    application.add_handler(CommandHandler("tts", tts_command))
    application.add_handler(CommandHandler("listvoices", list_voices))
    application.add_handler(CommandHandler("setvoice", set_voice))
    application.add_handler(CommandHandler("currentvoice", current_voice))
    application.add_handler(CommandHandler("history", get_history))
    application.add_handler(CommandHandler("generate_image", generate_image))
    application.add_handler(MessageHandler(filters.CAPTION & filters.PHOTO & filters.Regex(r'^/analyze_image'), analyze_image))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule the periodic cache updates
    application.job_queue.run_repeating(periodic_cache_update, interval=timedelta(days=1), first=10)
    application.job_queue.run_repeating(periodic_voice_cache_update, interval=timedelta(days=1), first=10)

    return application