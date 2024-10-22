import dramatiq
import logging
import base64
import io
import time
from pydub import AudioSegment
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN
import asyncio
from utils import openai_client
from dramatiq.middleware import CurrentMessage
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
import httpx
import openai
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Enhanced retry exceptions
RETRY_EXCEPTIONS = (
    openai.APIError,
    openai.APIConnectionError,
    openai.RateLimitError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.NetworkError,
    httpx.ProtocolError,
    ConnectionError,
    TimeoutError
)

@retry(
    retry=retry_if_exception_type(RETRY_EXCEPTIONS),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=1, max=30),
    before_sleep=before_sleep_log(logger, logging.INFO),
    after=after_log(logger, logging.INFO),
    reraise=True
)
async def make_openai_request_with_retry(messages, bot, chat_id, message_id, attempt_number=0):
    """Make OpenAI API request with enhanced retry logic"""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"🔄 Connecting to AI service... (Attempt {attempt_number + 1}/5)"
        )

        return await openai_client.chat.completions.create(
            model="gpt-4o-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": "alloy", "format": "wav"},
            messages=messages
        )
    except RETRY_EXCEPTIONS as e:
        logger.warning(f"Connection attempt {attempt_number + 1} failed: {str(e)}")
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"🔄 Connection interrupted, retrying... (Attempt {attempt_number + 1}/5)"
        )
        raise

@dramatiq.actor(max_retries=3, min_backoff=10000, max_backoff=60000)
def process_voice_message_task(voice_data_base64: str, user_id: int, chat_id: int, message_id: int, task_context: dict):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Extract conversation history
        conversation_history = task_context.get('conversation_history', [])
        if not isinstance(conversation_history, list):
            conversation_history = []
        
        logger.info(f"Processing voice message with conversation history length: {len(conversation_history)}")

        try:
            # Decode voice data
            voice_data = base64.b64decode(voice_data_base64)
            
            loop.run_until_complete(
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="🎵 Converting audio format..."
                )
            )

            # Convert OGG to WAV
            audio = AudioSegment.from_ogg(io.BytesIO(voice_data))
            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_data = wav_io.getvalue()
            encoded_voice = base64.b64encode(wav_data).decode('utf-8')

            # Process messages for the API call
            messages = []
            
            # Add previous messages with proper audio references
            for msg in conversation_history:
                if msg['role'] == 'assistant' and 'audio_id' in msg:
                    messages.append({
                        "role": "assistant",
                        "audio": {"id": msg['audio_id']}
                    })
                elif msg['role'] == 'user' or msg['role'] == 'assistant':
                    messages.append(msg)

            # Add the current voice message
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": encoded_voice,
                            "format": "wav"
                        }
                    }
                ]
            })

            logger.info(f"Sending request to OpenAI with {len(messages)} messages")

            # Make API request with retries
            completion = loop.run_until_complete(
                make_openai_request_with_retry(messages, bot, chat_id, message_id)
            )

            # Process response
            assistant_message = completion.choices[0].message
            wav_bytes = base64.b64decode(assistant_message.audio.data)
            transcript = assistant_message.audio.transcript
            audio_id = assistant_message.audio.id

            # Store response in conversation history
            conversation_history.append({
                "role": "assistant",
                "content": transcript,
                "audio_id": audio_id
            })

            # Keep only last 10 messages
            if len(conversation_history) > 10:
                conversation_history = conversation_history[-10:]

            # Clean up progress message and send response
            loop.run_until_complete(
                bot.delete_message(chat_id=chat_id, message_id=message_id)
            )

            loop.run_until_complete(
                bot.send_voice(
                    chat_id=chat_id,
                    voice=io.BytesIO(wav_bytes),
                    caption=f"🎯 Transcript: {transcript[:1000]}..."
                )
            )

            # Update conversation in database
            from database import save_gpt_conversation
            save_gpt_conversation(user_id, conversation_history)

            logger.info(f"Voice message processed successfully for user {user_id}")
            
            # Return updated conversation history for the bot to update its context
            return {
                "success": True,
                "conversation_history": conversation_history
            }

        except Exception as e:
            logger.error(f"Inner process error: {str(e)}")
            raise

    except Exception as e:
        logger.error(f"Error processing voice message for user {user_id}: {str(e)}")
        try:
            current_message = CurrentMessage.get_current_message()
            if current_message and current_message.options.get("retries", 0) >= current_message.actor.options["max_retries"]:
                error_text = "❌ Sorry, we're having trouble connecting to our AI service. Please try again in a few moments."
            else:
                error_text = "🔄 Processing interrupted. Retrying..."

            loop.run_until_complete(
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_text
                )
            )
        except Exception as msg_error:
            logger.error(f"Error sending error message: {str(msg_error)}")
            loop.run_until_complete(
                bot.send_message(
                    chat_id=chat_id,
                    text="❌ An error occurred while processing your voice message."
                )
            )
        raise  # Re-raise to trigger Dramatiq retry
    finally:
        loop.close()