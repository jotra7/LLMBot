import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from config import OPENAI_API_KEY
from utils import openai_client
from performance_metrics import record_command_usage, record_response_time, record_model_usage, record_error
from queue_system import queue_task
from database import save_conversation, get_user_conversations

logger = logging.getLogger(__name__)

gpt_models = []
DEFAULT_GPT_MODEL = None

async def fetch_gpt_models():
    global gpt_models, DEFAULT_GPT_MODEL
    try:
        models = await openai_client.models.list()
        gpt_models = [model.id for model in models.data if model.id.startswith('gpt')]
        gpt_models.sort(reverse=True)  # Sort models in descending order
        DEFAULT_GPT_MODEL = gpt_models[0] if gpt_models else "gpt-3.5-turbo"
        logger.info(f"Fetched GPT models: {gpt_models}")
        logger.info(f"Set default GPT model to: {DEFAULT_GPT_MODEL}")
    except Exception as e:
        logger.error(f"Error fetching GPT models: {e}")
        gpt_models = ["gpt-4", "gpt-3.5-turbo"]
        DEFAULT_GPT_MODEL = "gpt-3.5-turbo"

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
        model = context.user_data.get('gpt_model', DEFAULT_GPT_MODEL)

        # Get or initialize GPT conversation history from user context
        gpt_conversation = context.user_data.get('gpt_conversation', [])
        
        # Prepare messages for API call
        messages = gpt_conversation + [{"role": "user", "content": user_message}]

        # Send typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        response = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=1000,
        )

        assistant_response = response.choices[0].message.content

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

    except Exception as e:
        logger.error(f"Error processing GPT message for user {user_id}: {e}")
        await update.message.reply_text(f"An error occurred: {e}")
        record_error("gpt_message_processing_error")

    except Exception as e:
        logger.error(f"Error processing GPT message for user {user_id}: {e}")
        await update.message.reply_text(f"An error occurred: {e}")
        record_error("gpt_message_processing_error")

async def list_gpt_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_gpt_models")
    if not gpt_models:
        await fetch_gpt_models()
    
    models_text = "Available GPT models:\n" + "\n".join([f"• {model}" for model in gpt_models])
    await update.message.reply_text(models_text)

async def set_gpt_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("set_gpt_model")
    if not gpt_models:
        await fetch_gpt_models()
    
    keyboard = []
    for model in gpt_models:
        keyboard.append([InlineKeyboardButton(model, callback_data=f"set_gpt_model:{model}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a GPT model:", reply_markup=reply_markup)

async def gpt_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    model = query.data.split(':')[1]
    context.user_data['gpt_model'] = model
    await query.edit_message_text(f"GPT model set to {model}")
    logger.info(f"User {update.effective_user.id} set GPT model to {model}")



async def current_gpt_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_gpt_model")
    model = context.user_data.get('gpt_model', DEFAULT_GPT_MODEL)
    await update.message.reply_text(f"Current GPT model: {model}")
    logger.info(f"User {update.effective_user.id} checked current GPT model: {model}")

def setup_gpt_handlers(application):
    application.add_handler(CommandHandler("gpt", gpt_command))
    application.add_handler(CommandHandler("list_gpt_models", list_gpt_models))
    application.add_handler(CommandHandler("set_gpt_model", set_gpt_model))
    application.add_handler(CommandHandler("current_gpt_model", current_gpt_model))
    application.add_handler(CallbackQueryHandler(gpt_model_callback, pattern="^set_gpt_model:"))
    
    # Fetch GPT models on startup
    application.job_queue.run_once(lambda _: fetch_gpt_models(), when=1)