import logging
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import DEFAULT_MODEL, DEFAULT_SYSTEM_MESSAGE, ADMIN_USER_IDS
from utils import anthropic_client
from database import save_conversation, get_user_session, update_user_session
from performance_metrics import record_response_time, record_model_usage, record_error, record_command_usage
from queue_system import queue_task

logger = logging.getLogger(__name__)

@queue_task('quick')
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.username
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

    logger.info(f"User {user_name}({user_id}) sent message: '{user_message[:50]}...'")
    start_time = time.time()

    try:
        # Get user session and conversation history
        session = get_user_session(user_id)
        conversation_history = session.get('conversation', [])

        # Prepare messages for API call
        messages = conversation_history + [{"role": "user", "content": user_message}]

        # Send typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        response = anthropic_client.messages.create(
            model=model,
            max_tokens=1000,
            system=system_message,
            messages=messages
        )
        assistant_response = response.content[0].text

        # Update conversation history
        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": assistant_response})
        update_user_session(user_id, {'conversation': conversation_history[-10:]})  # Keep last 10 messages

        await update.message.reply_text(assistant_response)

        # Save the conversation
        save_conversation(user_id, user_message, assistant_response)

        # Record performance metrics
        end_time = time.time()
        record_response_time(end_time - start_time)
        record_model_usage(model)

    except Exception as e:
        logger.error(f"Error processing message for user {user_name} ({user_id}): {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}")
        record_error("message_processing_error")

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
    if update and update.effective_message:
        await update.effective_message.reply_text("An error occurred while processing your request. The developer has been notified.")