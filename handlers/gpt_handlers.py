import logging
import time
import base64
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import OPENAI_API_KEY
from utils import openai_client
from performance_metrics import record_command_usage, record_response_time, record_model_usage, record_error
from queue_system import queue_task
from database import save_conversation, get_user_conversations
import openai
from pydub import AudioSegment
import subprocess


logger = logging.getLogger(__name__)

gpt_models = []
DEFAULT_GPT_MODEL = None

def check_ffmpeg() -> bool:
    """
    Check if ffmpeg is installed and available in the system PATH.
    
    Returns:
        bool: True if ffmpeg is available, False otherwise
    """
    try:
        # Check ffmpeg
        subprocess.run(
            ["ffmpeg", "-version"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            check=True
        )
        # Check ffprobe (required by pydub)
        subprocess.run(
            ["ffprobe", "-version"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


async def fetch_gpt_models():
    try:
        models = await openai_client.models.list()
        gpt_models = [
            model.id for model in models.data 
            if model.id.startswith('gpt') and 'realtime' not in model.id.lower()
        ]
        gpt_models.sort(reverse=True)  # Sort models in descending order
        return gpt_models
    except Exception as e:
        logger.error(f"Error fetching GPT models: {e}")
        return []

@queue_task('quick')
async def gpt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("gpt")
    if not context.args:
        await update.message.reply_text("Please provide a message after the /gpt command.")
        return

    user_message = ' '.join(context.args)
    user_id = update.effective_user.id
    
    logger.info(f"User {user_id} sent GPT message: '{user_message[:50]}...'")
    start_time = time.time()

    try:
        # Get the user's preferred model or use the default
        model = context.user_data.get('gpt_model') or DEFAULT_GPT_MODEL

        if not model or 'realtime' in model.lower():
            available_models = await fetch_gpt_models()
            model = available_models[0] if available_models else None
            if not model:
                await update.message.reply_text("No suitable GPT model is available. Please try again later.")
                return
            context.user_data['gpt_model'] = model

        logger.info(f"Using model: {model} for user {user_id}")

        # Get or initialize GPT conversation history from user context
        gpt_conversation = context.user_data.get('gpt_conversation', [])
        
        # Prepare messages for API call
        messages = gpt_conversation + [{"role": "user", "content": user_message}]

        # Send typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        try:
            # Attempt to use chat completions API first
            response = await openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1000,
            )
            assistant_response = response.choices[0].message.content
        except openai.BadRequestError as e:
            if "This is not a chat model" in str(e):
                # If it's not a chat model, fall back to completions API
                prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
                response = await openai_client.completions.create(
                    model=model,
                    prompt=prompt,
                    max_tokens=1000,
                )
                assistant_response = response.choices[0].text.strip()
            else:
                raise  # Re-raise if it's a different kind of BadRequestError

        # Update conversation history
        gpt_conversation.append({"role": "user", "content": user_message})
        gpt_conversation.append({"role": "assistant", "content": assistant_response})
        
        # Keep only the last 10 messages to manage context length
        context.user_data['gpt_conversation'] = gpt_conversation[-10:]

        await update.message.reply_text(assistant_response)

        # Save the conversation
        save_conversation(user_id, user_message, assistant_response, model_type='gpt')

        # Record performance metrics
        end_time = time.time()
        record_response_time(end_time - start_time)
        record_model_usage(model)

    except openai.AuthenticationError:
        logger.error(f"Authentication error for user {user_id}")
        await update.message.reply_text("There was an authentication error. Please contact the administrator.")
        record_error("gpt_authentication_error")
    except openai.APIError as e:
        logger.error(f"OpenAI API error for user {user_id}: {str(e)}")
        await update.message.reply_text(f"An error occurred with the OpenAI API: {str(e)}")
        record_error("gpt_openai_api_error")
    except Exception as e:
        logger.error(f"Error processing GPT message for user {user_id}: {str(e)}")
        await update.message.reply_text(f"An unexpected error occurred: {str(e)}")
        record_error("gpt_message_processing_error")

async def list_gpt_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_gpt_models")
    models = await fetch_gpt_models()
    
    models_text = "Available GPT models:\n" + "\n".join([f"• {model}" for model in models])
    await update.message.reply_text(models_text)

async def set_gpt_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_gpt_model")
    try:
        models = await fetch_gpt_models()
        
        if not models:
            await update.message.reply_text("No suitable GPT models are available at the moment. Please try again later.")
            return

        keyboard = []
        for model in models:
            keyboard.append([InlineKeyboardButton(model, callback_data=f"set_gpt_model:{model}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose a GPT model:", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in set_gpt_model: {e}")
        await update.message.reply_text("An error occurred while fetching the models. Please try again later.")

async def gpt_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    model = query.data.split(':')[1]
    if 'realtime' not in model.lower():
        context.user_data['gpt_model'] = model
        await query.edit_message_text(f"GPT model set to {model}")
        logger.info(f"User {update.effective_user.id} set GPT model to {model}")
    else:
        await query.edit_message_text("Invalid model selection. Please choose a non-realtime model.")
        logger.warning(f"User {update.effective_user.id} attempted to select realtime model: {model}")

async def current_gpt_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_gpt_model")
    model = context.user_data.get('gpt_model', DEFAULT_GPT_MODEL)
    await update.message.reply_text(f"Current GPT model: {model}")
    logger.info(f"User {update.effective_user.id} checked current GPT model: {model}")

async def process_audio_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE, input_content) -> None:
    user_id = update.effective_user.id
    
    try:
        start_time = time.time()
        
        # Retrieve the conversation history
        conversation = context.user_data.get('audio_conversation', [])
        
        # Add the new message to the conversation
        conversation.append({"role": "user", "content": input_content})
        
        completion = await openai_client.chat.completions.create(
            model="gpt-4o-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": "alloy", "format": "wav"},
            messages=conversation
        )

        assistant_message = completion.choices[0].message
        wav_bytes = base64.b64decode(assistant_message.audio.data)
        transcript = assistant_message.audio.transcript

        # Add the assistant's response to the conversation
        conversation.append({"role": "assistant", "content": transcript})
        
        # Save the updated conversation
        context.user_data['audio_conversation'] = conversation

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        record_model_usage("gpt-4o-audio-preview")

        # Send the audio file and transcript
        await update.message.reply_voice(io.BytesIO(wav_bytes), caption=f"Transcript: {transcript[:1000]}...")

        logger.info(f"Audio response sent for user {user_id}")

    except Exception as e:
        logger.error(f"Error in audio interaction for user {user_id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while processing your request: {str(e)}")
        record_error("audio_interaction_error")

@queue_task('long_run')
async def speak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("speak")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /speak command.")
        return

    prompt = ' '.join(context.args)
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested speak command: '{prompt[:50]}...'")

    await process_audio_interaction(update, context, prompt)

@queue_task('long_run')
async def voice_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("voice_query")
    user_id = update.effective_user.id
    
    if not update.message.voice:
        logger.warning(f"User {user_id} triggered voice query handler without a voice message")
        return

    if not check_ffmpeg():
        error_message = ("FFmpeg is not installed or not in the system PATH. "
                        "Voice message processing is currently unavailable. "
                        "Please contact the bot administrator.")
        logger.error(f"FFmpeg not found for processing voice message from user {user_id}")
        await update.message.reply_text(error_message)
        return

    try:
        # Send initial status message
        status_message = await update.message.reply_text(
            "🎤 Voice message received! Starting processing..."
        )

        # Download the voice message
        file = await context.bot.get_file(update.message.voice.file_id)
        voice_data = await file.download_as_bytearray()
        
        # Convert to base64 for sending to dramatiq
        voice_data_base64 = base64.b64encode(voice_data).decode('utf-8')

        logger.info(f"User {user_id} voice message queued for processing")

        # Send to dramatiq task
        from dramatiq_tasks.voice_tasks import process_voice_message_task
        process_voice_message_task.send(
            voice_data_base64,
            user_id,
            update.effective_chat.id,
            status_message.message_id
        )

    except Exception as e:
        logger.error(f"Error queueing voice message for user {user_id}: {str(e)}")
        await update.message.reply_text(
            "❌ Sorry, there was an error processing your voice message. Please try again later."
        )
        record_error("voice_processing_error")
        
async def clear_audio_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if 'audio_conversation' in context.user_data:
        del context.user_data['audio_conversation']
        await update.message.reply_text("Audio conversation history has been cleared.")
    else:
        await update.message.reply_text("No audio conversation history to clear.")
    logger.info(f"Audio conversation cleared for user {user_id}")

def setup_gpt_handlers(application):
    application.add_handler(CommandHandler("gpt", gpt_command))
    application.add_handler(CommandHandler("list_gpt_models", list_gpt_models))
    application.add_handler(CommandHandler("set_gpt_model", set_gpt_model))
    application.add_handler(CommandHandler("current_gpt_model", current_gpt_model))
    application.add_handler(CallbackQueryHandler(gpt_model_callback, pattern="^set_gpt_model:"))
    application.add_handler(CommandHandler("speak", speak_command))
    application.add_handler(MessageHandler(filters.VOICE, voice_query_handler))
    application.add_handler(CommandHandler("clear_audio_chat", clear_audio_conversation))

    # Fetch GPT models on startup
    application.job_queue.run_once(lambda _: fetch_gpt_models(), when=1)