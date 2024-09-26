import logging
import asyncio
import time
import requests
import io
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from config import ELEVENLABS_API_KEY, ELEVENLABS_SOUND_GENERATION_API_URL
from voice_cache import get_voices, get_default_voice, update_voice_cache
from performance_metrics import record_command_usage, record_error, record_response_time
from queue_system import queue_task
from database import get_user_session, update_user_session

logger = logging.getLogger(__name__)

NAME, AUDIO = range(2)

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
    record_command_usage("list_voices")
    logger.info(f"User {update.effective_user.id} requested voice list")
    voices = await get_voices()
    voices_text = "Available voices:\n" + "\n".join([f"• {name}" for name in voices.values()])
    await update.message.reply_text(voices_text)

async def set_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    record_command_usage("set_voice")
    logger.info(f"User {user_id} initiated voice selection")
    
    try:
        voices = await get_voices()
        logger.info(f"Retrieved {len(voices)} voices for user {user_id}")
        
        if not voices:
            logger.warning(f"No voices available for user {user_id}")
            await update.message.reply_text("No voices are currently available. Please try again later.")
            return
        
        sorted_voices = sorted(voices.items(), key=lambda x: x[1])
        logger.info(f"Sorted {len(sorted_voices)} voices for user {user_id}")
        
        keyboard = []
        row = []
        for voice_id, name in sorted_voices:
            truncated_id = voice_id[:8]
            row.append(InlineKeyboardButton(name, callback_data=f"voice_{truncated_id}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        logger.info(f"Created keyboard with {len(keyboard)} rows for user {user_id}")
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose a voice:", reply_markup=reply_markup)
        logger.info(f"Sent voice selection message to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error in set_voice for user {user_id}: {str(e)}")
        await update.message.reply_text("An error occurred while setting up voice selection. Please try again later.")

async def voice_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Add logging to track the callback data
    logger.info(f"Received callback query: {query.data}")

    if query.data.startswith("voice_"):
        truncated_id = query.data.split("_")[1]
        voices = await get_voices()

        # Log available voices and truncated_id for debugging
        logger.info(f"Available voices: {voices.keys()}")
        logger.info(f"Looking for voice ID starting with: {truncated_id}")

        # Find the full voice_id that starts with the truncated_id
        voice_id = next((vid for vid in voices.keys() if vid.startswith(truncated_id)), None)

        if voice_id:
            context.user_data['voice_id'] = voice_id
            voice_name = voices.get(voice_id, "Unknown")
            logger.info(f"User {update.effective_user.id} set voice to {voice_name} (ID: {voice_id})")
            await query.edit_message_text(f"Voice set to {voice_name}")
        else:
            logger.error(f"Voice ID not found for truncated ID: {truncated_id}")
            await query.edit_message_text("Error setting voice. Please try again.")
    else:
        logger.error(f"Unexpected callback query data: {query.data}")
        await query.edit_message_text("I'm not sure how to handle that request. Please try again.")

async def current_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_voice")
    voice_id = context.user_data.get('voice_id', get_default_voice())
    voices = await get_voices()
    voice_name = voices.get(voice_id, "Unknown")
    logger.info(f"User {update.effective_user.id} checked current voice: {voice_name} (ID: {voice_id})")
    await update.message.reply_text(f"Current voice: {voice_name}")

@queue_task('long_run')
async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("tts")
    if not context.args:
        await update.message.reply_text("Please provide some text after the /tts command.")
        return

    text = ' '.join(context.args)
    voice_id = context.user_data.get('voice_id')

    if not voice_id:
        # Automatically set a default voice
        voices = await get_voices()
        if voices:
            voice_id = next(iter(voices))  # Get the first available voice
            context.user_data['voice_id'] = voice_id
            await update.message.reply_text(f"No voice was set. I've automatically selected a default voice for you. You can change it later with /setvoice.")
        else:
            await update.message.reply_text("No voices are available. Please try again later.")
            return

    logger.info(f"User {update.effective_user.id} requested TTS: '{text[:50]}...'")
    try:
        audio_content = generate_speech(text, voice_id)
        await update.message.reply_voice(audio_content)
    except Exception as e:
        logger.error(f"TTS error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while generating speech: {str(e)}")
        record_error("tts_error")

async def start_voice_addition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_session = get_user_session(user_id)
    
    if 'custom_voice_id' in user_session:
        await update.message.reply_text("You already have a custom voice. You can only have one custom voice at a time. "
                                        "If you want to create a new one, please delete your existing custom voice first.")
        return ConversationHandler.END
    
    await update.message.reply_text("Let's add a new voice! Please send me the name for your new voice.")
    return NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['voice_name'] = update.message.text
    logger.info(f"Voice name set for user {update.effective_user.id}: {context.user_data['voice_name']}")
    await update.message.reply_text("Great! Now, please send me an audio file of the voice. It should be a clear recording of about 30 seconds or more.")
    return AUDIO

async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if update.message.voice or update.message.audio:
        logger.info(f"Received audio file from user {user_id}")
        try:
            await update.message.reply_text("Processing your audio file. This may take a moment...")
            file = await context.bot.get_file(update.message.voice.file_id if update.message.voice else update.message.audio.file_id)
            logger.info(f"File ID received for user {user_id}: {file.file_id}")
            file_path = await file.download_to_drive()
            
            logger.info(f"Audio file downloaded to {file_path} for user {user_id}")
            
            voice_name = f"{context.user_data['voice_name']} (User {user_id})"
            voice_id = await add_voice_to_elevenlabs(voice_name, file_path, user_id)
            
            if voice_id:
                logger.info(f"Voice added successfully for user {user_id} with ID: {voice_id}")
                await update_voice_cache()
                logger.info(f"Voice cache updated for user {user_id}")
                
                # Update user session with custom voice ID
                user_session = get_user_session(user_id)
                user_session['custom_voice_id'] = voice_id
                update_user_session(user_id, user_session)
                
                await update.message.reply_text(f"Your custom voice '{context.user_data['voice_name']}' has been added successfully! You can now use it for text-to-speech.")
            else:
                logger.error(f"Failed to add voice to ElevenLabs for user {user_id}")
                await update.message.reply_text("There was an error adding your voice. Please try again later.")
            
            os.remove(file_path)
            logger.info(f"Temporary audio file removed for user {user_id}")
        except Exception as e:
            logger.exception(f"Error in voice addition process for user {user_id}: {str(e)}")
            await update.message.reply_text(f"An error occurred while processing your voice: {str(e)}")
        return ConversationHandler.END
    else:
        await update.message.reply_text("Please send an audio file of the voice.")
        return AUDIO

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Voice addition cancelled.")
    return ConversationHandler.END

async def add_voice_to_elevenlabs(name, file_path, user_id):
    logger.info(f"Attempting to add voice to ElevenLabs: {name}")
    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {
        "Accept": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    data = {
        "name": name,
        "labels": f'{{"user_id": "{user_id}", "custom": "true"}}'
    }
    
    try:
        with open(file_path, "rb") as file:
            files = [("files", (os.path.basename(file_path), file, "audio/mpeg"))]
            logger.info(f"Sending request to ElevenLabs API for voice: {name}")
            response = requests.post(url, headers=headers, data=data, files=files)
        response.raise_for_status()
        voice_id = response.json()['voice_id']
        logger.info(f"Voice added successfully to ElevenLabs with ID: {voice_id}")
        return voice_id
    except Exception as e:
        logger.exception(f"Error adding voice to ElevenLabs: {str(e)}")
        return None

async def delete_custom_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_session = get_user_session(user_id)
    
    if 'custom_voice_id' not in user_session:
        await update.message.reply_text("You don't have a custom voice to delete.")
        return
    
    voice_id = user_session['custom_voice_id']
    
    # Delete voice from ElevenLabs
    if await delete_voice_from_elevenlabs(voice_id):
        del user_session['custom_voice_id']
        update_user_session(user_id, user_session)
        await update_voice_cache()
        await update.message.reply_text("Your custom voice has been deleted successfully.")
    else:
        await update.message.reply_text("There was an error deleting your custom voice. Please try again later.")

async def delete_voice_from_elevenlabs(voice_id):
    url = f"https://api.elevenlabs.io/v1/voices/{voice_id}"
    headers = {
        "Accept": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.exception(f"Error deleting voice from ElevenLabs: {str(e)}")
        return False

voice_addition_handler = ConversationHandler(
    entry_points=[CommandHandler("add_voice", start_voice_addition)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        AUDIO: [MessageHandler(filters.AUDIO | filters.VOICE, receive_audio)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

__all__ = [
    'list_voices',
    'set_voice',
    'current_voice',
    'tts_command',
    'start_voice_addition',
    'delete_custom_voice',
    'voice_addition_handler'
]