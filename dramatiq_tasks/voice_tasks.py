import dramatiq
import logging
import base64
import io
from pydub import AudioSegment
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN
import asyncio
from utils import openai_client

logger = logging.getLogger(__name__)

@dramatiq.actor
def process_voice_message_task(voice_data_base64: str, user_id: int, chat_id: int, message_id: int):
    try:
        # Initialize bot
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Decode voice data
        voice_data = base64.b64decode(voice_data_base64)
        
        # Send processing update
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

        # Update status
        loop.run_until_complete(
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="🧠 Processing your message with AI..."
            )
        )

        # Process with OpenAI
        completion = loop.run_until_complete(
            openai_client.chat.completions.create(
                model="gpt-4o-audio-preview",
                modalities=["text", "audio"],
                audio={"voice": "alloy", "format": "wav"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "This is an audio message from the user. Please respond to it."},
                            {"type": "input_audio", "input_audio": {"data": encoded_voice, "format": "wav"}}
                        ]
                    }
                ]
            )
        )

        # Update status
        loop.run_until_complete(
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="🎨 Generating response..."
            )
        )

        # Process response
        assistant_message = completion.choices[0].message
        wav_bytes = base64.b64decode(assistant_message.audio.data)
        transcript = assistant_message.audio.transcript

        # Delete the progress message
        loop.run_until_complete(
            bot.delete_message(chat_id=chat_id, message_id=message_id)
        )

        # Send the final response
        loop.run_until_complete(
            bot.send_voice(
                chat_id=chat_id,
                voice=io.BytesIO(wav_bytes),
                caption=f"🎯 Transcript: {transcript[:1000]}..."
            )
        )

        logger.info(f"Voice message processed successfully for user {user_id}")

    except Exception as e:
        logger.error(f"Error processing voice message for user {user_id}: {str(e)}")
        try:
            loop.run_until_complete(
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"❌ Sorry, there was an error processing your voice message: {str(e)}"
                )
            )
        except:
            # If we can't edit the message, try to send a new one
            loop.run_until_complete(
                bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Sorry, there was an error processing your voice message: {str(e)}"
                )
            )
    finally:
        loop.close()