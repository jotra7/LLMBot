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