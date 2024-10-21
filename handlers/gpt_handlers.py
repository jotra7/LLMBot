import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from config import OPENAI_API_KEY
from utils import openai_client
from performance_metrics import record_command_usage, record_response_time, record_model_usage, record_error
from queue_system import queue_task
from database import save_conversation, get_user_conversations
import openai
import base64

logger = logging.getLogger(__name__)

gpt_models = []
DEFAULT_GPT_MODEL = None

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
    if not gpt_models:
        await fetch_gpt_models()
    
    models_text = "Available GPT models:\n" + "\n".join([f"• {model}" for model in gpt_models])
    await update.message.reply_text(models_text)

async def set_gpt_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_gpt_model")
    try:
        gpt_models = await fetch_gpt_models()
        
        if not gpt_models:
            await update.message.reply_text("No suitable GPT models are available at the moment. Please try again later.")
            return

        keyboard = []
        for model in gpt_models:
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

@queue_task('long_run')
async def speak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("speak")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /speak command.")
        return

    prompt = ' '.join(context.args)
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested speak command: '{prompt[:50]}...'")

    try:
        start_time = time.time()
        
        # Retrieve the conversation history
        messages = context.user_data.get('audio_conversation', [])
        messages.append({"role": "user", "content": prompt})

        completion = await openai_client.chat.completions.create(
            model="gpt-4o-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": "shimmer", "format": "wav"},
            messages=messages
        )

        assistant_message = completion.choices[0].message
        wav_bytes = base64.b64decode(assistant_message.audio.data)
        audio_id = assistant_message.audio.id
        transcript = assistant_message.audio.transcript

        # Update the conversation history
        messages.append({
            "role": "assistant",
            "audio": {"id": audio_id},
            "content": transcript
        })
        context.user_data['audio_conversation'] = messages

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        record_model_usage("gpt-4o-audio-preview")

        # Send the audio file and transcript
        await update.message.reply_voice(wav_bytes, caption=f"Transcript: {transcript[:1000]}...")

        logger.info(f"Audio response sent for user {user_id}")

    except Exception as e:
        logger.error(f"Error in speak command for user {user_id}: {str(e)}")
        await update.message.reply_text(f"An error occurred while processing your request: {str(e)}")
        record_error("speak_command_error")

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
    application.add_handler(CommandHandler("clear_audio_chat", clear_audio_conversation))


    # Fetch GPT models on startup
    application.job_queue.run_once(lambda _: fetch_gpt_models(), when=1)