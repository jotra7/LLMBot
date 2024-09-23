import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import DEFAULT_MODEL
from model_cache import get_models
from performance_metrics import record_command_usage
from voice_cache import get_voices

logger = logging.getLogger(__name__)

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("list_models")
    logger.info(f"User {update.effective_user.id} requested model list")
    models = await get_models()
    models_text = "Available models:\n" + "\n".join([f"• {name}" for name in models.values()])
    await update.message.reply_text(models_text)

# model_handlers.py
async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    
    # Log when this function is called
    logger.info(f"set_model called by user {user.id}")

    # Check if context.args is empty, and avoid setting the model to "Unknown"
    if not context.args:
        logger.warning(f"Model set attempt with no arguments by user {user.id}")
        await update.message.reply_text("Please provide a valid model name.")
        return

    # Set the model only if a valid argument is provided
    model = context.args[0]
    context.user_data['model'] = model

    logger.info(f"User {user.id} successfully set model to {model}")
    await update.message.reply_text(f"Model set to: {model}")

async def current_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("current_model")
    current = context.user_data.get('model', DEFAULT_MODEL)
    models = await get_models()
    logger.info(f"User {update.effective_user.id} checked current model: {models.get(current, 'Unknown')}")
    await update.message.reply_text(f"Current model: {models.get(current, 'Unknown')}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data in await get_models():  # Only handle model-related callbacks
        chosen_model = query.data
        context.user_data['model'] = chosen_model
        models = await get_models()
        logger.info(f"User {update.effective_user.id} set model to {models.get(chosen_model, 'Unknown')}")
        await query.edit_message_text(f"Model set to {models.get(chosen_model, 'Unknown')}")
    else:
        logger.warning(f"Unhandled callback query: {query.data}")
