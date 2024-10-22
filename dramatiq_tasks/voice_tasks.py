import dramatiq
import logging
import base64
import io
import json
import tenacity
from pydub import AudioSegment
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN
import asyncio
from utils import openai_client
from dramatiq.middleware import CurrentMessage
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log, after_log
import httpx
import openai
from openai import AsyncOpenAI
import redis
from config import (REDIS_HOST, REDIS_PORT, REDIS_DB)

# Set up Redis
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

logger = logging.getLogger(__name__)

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
    TimeoutError,
)

class ConversationState:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.redis_key = f"user:{user_id}:conversation"
        
    def load(self) -> list:
        """Load conversation history from Redis"""
        data = redis_client.get(self.redis_key)
        if data:
            return json.loads(data.decode('utf-8'))
        return []
    
    def save(self, messages: list):
        """Save conversation history to Redis"""
        redis_client.setex(self.redis_key, 24*60*60, json.dumps(messages))
    
    def add_message(self, role: str, **content):
        """Add a message to the conversation history"""
        messages = self.load()
        messages.append({"role": role, **content})
        self.save(messages)
        return messages

async def make_openai_request_with_retry(messages, bot, chat_id, message_id, attempt_number=0):
    """Make OpenAI API request with enhanced retry logic"""
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=2, min=1, max=30),
            retry=retry_if_exception_type(RETRY_EXCEPTIONS),
            before_sleep=before_sleep_log(logger, logging.INFO),
            after=after_log(logger, logging.INFO),
            reraise=True
        ):
            with attempt:
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

    except tenacity.RetryError as e:
        logger.error(f"Retry limit reached: {str(e)}")
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="❌ Failed to connect to the AI service after multiple attempts. Please try again later."
        )
        raise
    except Exception as e:
        logger.error(f"Unexpected error occurred during retry: {str(e)}")
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="❌ An unexpected error occurred. Please try again."
        )
        raise

@dramatiq.actor(max_retries=3, min_backoff=10000, max_backoff=60000)
def process_voice_message_task(voice_data_base64: str, user_id: int, chat_id: int, message_id: int, task_context: dict):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        conversation = ConversationState(user_id)

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

            # Get conversation history
            messages = conversation.load()
            
            # Add current user message
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

            logger.info(f"[User {user_id}] Sending request with {len(messages)} messages")

            # Make API request
            completion = loop.run_until_complete(
                make_openai_request_with_retry(messages, bot, chat_id, message_id)
            )

            # Process response
            assistant_message = completion.choices[0].message
            wav_bytes = base64.b64decode(assistant_message.audio.data)
            transcript = assistant_message.audio.transcript
            audio_id = assistant_message.audio.id

            # Save assistant's response to conversation history
            messages.append({
                "role": "assistant",
                "content": transcript,
                "audio": {
                    "id": audio_id
                }
            })
            
            # Update conversation history
            conversation.save(messages[-10:])  # Keep last 10 messages
            
            logger.info(f"[User {user_id}] Updated conversation history with audio_id: {audio_id}")

            # Clean up progress message
            loop.run_until_complete(
                bot.delete_message(chat_id=chat_id, message_id=message_id)
            )

            # Send response
            loop.run_until_complete(
                bot.send_voice(
                    chat_id=chat_id,
                    voice=io.BytesIO(wav_bytes),
                    caption=f"🎯 Transcript: {transcript[:1000]}..."
                )
            )

            logger.info(f"[User {user_id}] Voice message processed successfully")
            
        except Exception as e:
            logger.error(f"[User {user_id}] Inner process error: {str(e)}")
            raise

    except Exception as e:
        logger.error(f"[User {user_id}] Error processing voice message: {str(e)}")
        try:
            current_message = CurrentMessage.get_current_message()
            if current_message and current_message.options.get("retries", 0) >= current_message.actor.options["max_retries"]:
                error_text = "❌ Sorry, we're having trouble processing your voice message. Please try again in a few moments."
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
            logger.error(f"[User {user_id}] Error sending error message: {str(msg_error)}")
            loop.run_until_complete(
                bot.send_message(
                    chat_id=chat_id,
                    text="❌ An error occurred while processing your voice message."
                )
            )
        raise
    finally:
        loop.close()

@dramatiq.actor
def clear_conversation(user_id: int):
    """Clear a user's conversation history"""
    conversation = ConversationState(user_id)
    redis_client.delete(conversation.redis_key)
    logger.info(f"[User {user_id}] Conversation history cleared")