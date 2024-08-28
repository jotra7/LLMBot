import asyncio
import logging
import time
import requests
from queue_system import queue_task, check_queue_status as _check_queue_status
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from config import ADMIN_USER_IDS, DEFAULT_MODEL, DEFAULT_SYSTEM_MESSAGE, ELEVENLABS_API_KEY, ELEVENLABS_SOUND_GENERATION_API_URL,FLUX_MODELS, DEFAULT_FLUX_MODEL
from model_cache import get_models
from voice_cache import get_voices, get_default_voice
from database import save_conversation, get_user_conversations, get_all_users, ban_user, unban_user
from image_processing import generate_image_openai, analyze_image_openai
from tts import generate_speech
from utils import anthropic_client
from performance_metrics import record_response_time, record_model_usage, record_command_usage, record_error, get_performance_metrics, save_performance_data
import fal_client


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
        "/video <text> - Make a short video clip (Takes a long time)\n"
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

@queue_task('long_run')
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

@queue_task('long_run')
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
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image generated in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Image generation error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while generating the image: {str(e)}")
        record_error("image_generation_error")
        
@queue_task('long_run')
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
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Image analyzed in {response_time:.2f} seconds")

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

async def list_flux_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_flux_models")
    models_text = "Available Flux models:\n" + "\n".join([f"• {name}" for name in FLUX_MODELS.keys()])
    await update.message.reply_text(models_text)

async def set_flux_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_flux_model")
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"set_flux_model:{model_id}")]
        for name, model_id in FLUX_MODELS.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a Flux model:", reply_markup=reply_markup)

async def flux_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    model_id = query.data.split(':')[1]
    model_name = next((name for name, id in FLUX_MODELS.items() if id == model_id), None)
    
    if model_name:
        context.user_data['flux_model'] = model_name
        await query.edit_message_text(f"Flux model set to {model_name}")
    else:
        await query.edit_message_text("Invalid model selection. Please try again.")

async def current_flux_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_flux_model")
    current = context.user_data.get('flux_model', DEFAULT_FLUX_MODEL)
    await update.message.reply_text(f"Current Flux model: {current}")

@queue_task('long_run')
async def flux_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("flux")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /flux command.")
        return

    prompt = ' '.join(context.args)
    logger.info(f"User {update.effective_user.id} requested Flux image generation: '{prompt[:50]}...'")

    # Send an initial message
    progress_message = await update.message.reply_text("🎨 Initializing image generation...")

    start_time = time.time()
    try:
        logger.info("Starting Flux image generation process")
        
        model_name = context.user_data.get('flux_model', DEFAULT_FLUX_MODEL)
        model_id = FLUX_MODELS[model_name]

        # Create a progress updater
        async def update_progress():
            steps = [
                "Analyzing prompt", "Preparing canvas", "Sketching outlines", 
                "Adding details", "Applying colors", "Refining image", 
                "Enhancing details", "Adjusting lighting", "Finalizing composition"
            ]
            step_index = 0
            dots = 0
            while True:
                step = steps[step_index % len(steps)]
                await progress_message.edit_text(f"🎨 {step}{'.' * dots}")
                dots = (dots + 1) % 4
                step_index += 1
                await asyncio.sleep(2)  # Update every 2 seconds

        # Start the progress updater
        progress_task = asyncio.create_task(update_progress())

        try:
            logger.info(f"Submitting Flux image generation request with model: {model_name}")
            handler = fal_client.submit(
                model_id,
                arguments={
                    "prompt": prompt,
                    "image_size": "landscape_4_3",
                    "num_inference_steps": 28,
                    "guidance_scale": 3.5,
                    "num_images": 1,
                    "safety_tolerance": "2" if model_name == "flux-pro" else None,
                },
            )

            logger.info("Waiting for Flux image generation result")
            result = handler.get()
            logger.info("Flux image generation result received")
            
            # Cancel the progress task
            progress_task.cancel()
            
            # Update the progress message
            await progress_message.edit_text("✅ Image generated! Uploading...")
            
            if result and result.get('images') and len(result['images']) > 0:
                image_url = result['images'][0]['url']
                logger.info(f"Image URL received: {image_url}")
                await update.message.reply_photo(photo=image_url, caption=f"Generated image using {model_name} for: {prompt}")
                
                # Delete the progress message
                await progress_message.delete()
            else:
                logger.error("No image URL in the result")
                await progress_message.edit_text("Sorry, I couldn't generate an image. Please try again.")
        except Exception as e:
            logger.error(f"Error during Flux image generation: {str(e)}")
            await progress_message.edit_text(f"An error occurred while generating the image: {str(e)}")
        finally:
            if not progress_task.cancelled():
                progress_task.cancel()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Flux image generated using {model_name} in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Flux image generation error for user {update.effective_user.id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while setting up image generation: {str(e)}")
        record_error("flux_image_generation_error")
    finally:
        logger.info(f"Flux command execution completed for user {update.effective_user.id}")

@queue_task('long_run')
async def generate_sound(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_sound")
    if not context.args:
        await update.message.reply_text("Please provide a text description for the sound you want to generate.")
        return

    text = ' '.join(context.args)
    
    logger.info(f"User {update.effective_user.id} requested sound generation: '{text[:50]}...'")
    
    # Send an initial message
    progress_message = await update.message.reply_text("🎵 Generating sound... This may take a minute or two.")

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "duration_seconds": None,  # Let the API determine the optimal duration
        "prompt_influence": 0.3  # Default value
    }

    start_time = time.time()
    try:
        async def update_progress():
            dots = 1
            while True:
                await progress_message.edit_text(f"🎵 Generating sound{'.' * dots}")
                dots = (dots % 3) + 1  # Cycle through 1, 2, 3 dots
                await asyncio.sleep(1)

        progress_task = asyncio.create_task(update_progress())

        try:
            response = requests.post(ELEVENLABS_SOUND_GENERATION_API_URL, headers=headers, json=data)
            response.raise_for_status()
            
            # Cancel the progress task
            progress_task.cancel()
            
            # Update the progress message
            await progress_message.edit_text("✅ Sound generated! Uploading...")
            
            # Send the audio file
            await update.message.reply_audio(response.content, filename="generated_sound.mp3")
            
            # Delete the progress message
            await progress_message.delete()
        finally:
            if not progress_task.cancelled():
                progress_task.cancel()

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Sound generated in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Sound generation error for user {update.effective_user.id}: {str(e)}")
        await progress_message.edit_text(f"❌ An error occurred while generating the sound: {str(e)}")
        record_error("sound_generation_error")
 


@queue_task('long_run')
async def generate_text_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("generate_text_to_video")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /video command.")
        return

    prompt = ' '.join(context.args)
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested text-to-video generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text("🎬 Generating video... This may take 20-30 seconds or more.")

    try:
        handler = fal_client.submit(
            "fal-ai/fast-animatediff/text-to-video",
            arguments={
                "prompt": prompt,
                "num_frames": 150,
                "num_inference_steps": 25,
                "guidance_scale": 7.5,
                "fps": 30,
                "video_size": "square"
            }
        )

        result = handler.get()
        video_url = result['video']['url']
        
        await progress_message.edit_text("✅ Video generated! Uploading...")
        
        video_content = requests.get(video_url).content
        
        await update.message.reply_video(video_content, caption=f"Generated video for: {prompt}")
        
        await progress_message.delete()

        logger.info(f"Video generated successfully for user {user_id}")

    except Exception as e:
        logger.error(f"Video generation error for user {user_id}: {str(e)}")
        try:
            await progress_message.edit_text(f"❌ An error occurred while generating the video: {str(e)}")
        except Exception as edit_error:
            logger.error(f"Error updating progress message: {str(edit_error)}")
        record_error("video_generation_error")
    
    finally:
        logger.info(f"Video generation process completed for user {user_id}")


async def queue_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _check_queue_status(update, context)
    