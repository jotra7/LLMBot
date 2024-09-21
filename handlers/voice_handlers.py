import logging
import asyncio
import time
import requests
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from voice_cache import get_voices, get_default_voice
from performance_metrics import record_command_usage, record_error, record_response_time
from queue_system import queue_task
from config import ELEVENLABS_API_KEY, ELEVENLABS_SOUND_GENERATION_API_URL

logger = logging.getLogger(__name__)

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
    record_command_usage("set_voice")
    logger.info(f"User {update.effective_user.id} initiated voice selection")
    voices = await get_voices()
    
    # Create a list of voices, sorted alphabetically by name
    sorted_voices = sorted(voices.items(), key=lambda x: x[1])
    
    # Create buttons for each voice, with 2 buttons per row
    keyboard = []
    row = []
    for voice_id, name in sorted_voices:
        row.append(InlineKeyboardButton(name, callback_data=f"voice_{voice_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:  # Add any remaining buttons
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Start", callback_data="start")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Please choose a voice:", reply_markup=reply_markup)
    
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

async def voice_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("voice_"):
        voice_id = query.data.split("_")[1]
        context.user_data['voice_id'] = voice_id
        voices = await get_voices()
        voice_name = voices.get(voice_id, "Unknown")
        logger.info(f"User {update.effective_user.id} set voice to {voice_name} (ID: {voice_id})")
        await query.edit_message_text(f"Voice set to {voice_name}")

# Ensure these functions are exported
__all__ = ['list_voices', 'set_voice', 'current_voice', 'tts_command', 'generate_sound', 'voice_button_callback']