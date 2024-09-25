import logging
import asyncio
import time
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from config import ADMIN_USER_IDS
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
from database import save_user_generation, get_user_generations_today
import aiohttp
import os

logger = logging.getLogger(__name__)

SUNO_API_BASE_URL = ""
MAX_GENERATIONS_PER_DAY = 3
MAX_WAIT_TIME = 120  # Maximum wait time in seconds

async def suno_api_request(endpoint, data=None, method='POST'):
    async with aiohttp.ClientSession() as session:
        url = f"https://suno-api-cyan-five.vercel.app/api/{endpoint}"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        try:
            if method == 'POST':
                async with session.post(url, json=data, headers=headers) as response:
                    logger.info(f"POST request to {url} with data: {data}")
                    response.raise_for_status()
                    json_response = await response.json()
                    logger.info(f"Response: {json_response}")
                    return json_response
            elif method == 'GET':
                async with session.get(url, headers=headers) as response:
                    logger.info(f"GET request to {url}")
                    response.raise_for_status()
                    json_response = await response.json()
                    logger.info(f"Response: {json_response}")
                    return json_response
        except aiohttp.ClientResponseError as e:
            logger.error(f"API request failed: {e.status} {e.message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in API request: {str(e)}")
            raise

async def download_mp3(audio_url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as response:
            if response.status == 200:
                with open(file_name, 'wb') as f:
                    f.write(await response.read())
                logger.info(f"MP3 file downloaded: {file_name}")
            else:
                logger.error(f"Failed to download MP3 from {audio_url}, status code: {response.status}")

async def wait_for_generation(generation_id, chat_id, context):
    start_time = time.time()
    await context.bot.send_message(
        chat_id=chat_id,
        text="🎵 Music generation started. Please wait while your music is being created..."
    )
    
    while time.time() - start_time < MAX_WAIT_TIME:
        result = await suno_api_request(f"get?id={generation_id}", method='GET')
        if result and isinstance(result, list) and len(result) > 0:
            if result[0]['status'] == 'complete':
                return result[0]
        await asyncio.sleep(10)  # Wait for 10 seconds before checking again
    
    return None

async def generate_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username
    chat_id = update.effective_chat.id

    logger.info(f"Suno generation requested by user {user_id} ({user_name})")

    user_generations_today = get_user_generations_today(user_id)
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    if user_generations_today >= MAX_GENERATIONS_PER_DAY:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Sorry {user_name}, you have reached your daily limit of {MAX_GENERATIONS_PER_DAY} generations."
        )
        return

    try:
        # Send the generation request
        data = {
            "prompt": update.message.text,
            "make_instrumental": False,
            "model": "chirp-v3-5",
            "wait_audio": False
        }
        
        response = await suno_api_request('generate', data=data)

        if response and isinstance(response, list) and len(response) > 0:
            generation_id = response[0]['id']
            prompt = data['prompt']
            logger.info(f"Generation ID for user {user_id}: {generation_id}")
            
            # Wait for the generation to complete with progress updates
            completed_generation = await wait_for_generation(generation_id, chat_id, context)
            
            if completed_generation and completed_generation.get('audio_url'):
                audio_url = completed_generation['audio_url']
                file_name = f"{generation_id}.mp3"
                
                # Download the MP3 file
                await download_mp3(audio_url, file_name)
                
                # Send the MP3 file to the user
                with open(file_name, 'rb') as audio_file:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        title="Generated Music",
                        caption="Here is your generated music!"
                    )
                
                # Clean up the file after sending
                os.remove(file_name)
                
                # Save user generation with prompt and generation_id
                save_user_generation(user_id, prompt, generation_id)
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Music generation is still in progress. Please try again later."
                )
        else:
            logger.error(f"Suno music generation failed for user {user_id}. Response: {response}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Failed to generate music. Please try again later."
            )
    except Exception as e:
        logger.error(f"Suno music generation error for user {user_id}: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while generating your music. Please try again later."
        )


@queue_task('long_run')
async def custom_generate_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_custom_generate_music")
    user_id = update.effective_user.id
    
    try:
        generations_today = get_user_generations_today(user_id)
        if generations_today >= MAX_GENERATIONS_PER_DAY:
            await update.message.reply_text(f"You've reached your daily limit of {MAX_GENERATIONS_PER_DAY} generations. Please try again tomorrow.")
            return
    except Exception as e:
        logger.error(f"Error checking user generations: {e}")
        await update.message.reply_text("An error occurred while checking your daily limit. Please try again later.")
        return

    if not context.args or len(context.args) < 4:
        await update.message.reply_text("Please provide title, lyrics, prompt, and music_style after the /custom_generate_music command.")
        return

    title = context.args[0]
    lyrics = context.args[1]
    prompt = context.args[2]
    music_style = context.args[3]

    logger.info(f"User {user_id} requested Suno custom music generation: '{title}'")

    progress_message = await update.message.reply_text("🎵 Initializing custom music generation...")

    start_time = time.time()
    try:
        data = {
            "title": title,
            "lyrics": lyrics,
            "prompt": prompt,
            "music_style": music_style,
            "make_instrumental": False,
            "model": "chirp-v3-5|chirp-v3-0",
            "wait_audio": False
        }
        initial_result = await suno_api_request("custom_generate", data)

        if not initial_result or not isinstance(initial_result, list) or len(initial_result) == 0:
            raise ValueError(f"Unexpected response format from Suno API: {initial_result}")

        generation_id = initial_result[0].get('id')
        if not generation_id:
            raise ValueError(f"No generation ID in the response: {initial_result}")

        await progress_message.edit_text("🎵 Custom music generation in progress. This may take up to 2 minutes...")
        
        # Periodically check for generation status
        check_interval = 10  # seconds
        max_checks = MAX_WAIT_TIME // check_interval
        for _ in range(max_checks):
            await asyncio.sleep(check_interval)
            
            status_result = await suno_api_request(f"get?id={generation_id}", method='GET')
            
            if not status_result or not isinstance(status_result, list) or len(status_result) == 0:
                logger.warning(f"Unexpected status response: {status_result}")
                continue

            status = status_result[0].get('status')
            if status == 'complete':
                audio_url = status_result[0].get('audio_url')
                if not audio_url:
                    raise ValueError(f"No audio URL in complete status: {status_result}")
                
                await update.message.reply_audio(audio=audio_url, caption=f"Generated custom music: {title}")
                await progress_message.delete()
                
                try:
                    save_user_generation(user_id, prompt, generation_id)
                except Exception as e:
                    logger.error(f"Error saving user generation: {e}")

                break
            elif status == 'failed':
                raise ValueError(f"Generation failed: {status_result[0].get('error', 'Unknown error')}")
            else:
                await progress_message.edit_text(f"🎵 Custom music generation in progress. Status: {status}")

        else:
            raise TimeoutError("Custom music generation timed out")

        end_time = time.time()
        response_time = end_time - start_time
        record_response_time(response_time)
        logger.info(f"Suno custom music generation process completed in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Suno custom music generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while generating the custom music: {str(e)}")
        record_error("suno_custom_music_generation_error")
        
async def get_music_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_get_music_info")
    if not context.args:
        await update.message.reply_text("Please provide music ID(s) after the /get_music_info command.")
        return

    music_ids = ','.join(context.args)
    try:
        result = await suno_api_request("get", {"id": music_ids}, method='GET')
        if result:
            info = "\n\n".join([f"ID: {item['id']}\nPrompt: {item['prompt']}\nStatus: {item['status']}" for item in result])
            await update.message.reply_text(f"Music Information:\n\n{info}")
        else:
            await update.message.reply_text("No information found for the provided ID(s).")
    except Exception as e:
        logger.error(f"Error fetching music info: {str(e)}")
        await update.message.reply_text("An error occurred while fetching music information.")
        record_error("suno_get_music_info_error")

async def get_quota_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_get_quota_info")
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("Sorry, this command is only available to administrators.")
        return

    try:
        result = await suno_api_request("get_limit", method='GET')
        if result:
            await update.message.reply_text(f"Quota Information:\nRemaining: {result['remaining']}\nLimit: {result['limit']}")
        else:
            await update.message.reply_text("Unable to fetch quota information.")
    except Exception as e:
        logger.error(f"Error fetching quota info: {str(e)}")
        await update.message.reply_text("An error occurred while fetching quota information.")
        record_error("suno_get_quota_info_error")

@queue_task('long_run')
async def generate_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_generate_lyrics")
    if not context.args:
        await update.message.reply_text("Please provide a prompt after the /generate_lyrics command.")
        return

    prompt = ' '.join(context.args)
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested Suno lyrics generation: '{prompt[:50]}...'")

    progress_message = await update.message.reply_text("✍️ Generating lyrics...")

    try:
        data = {
            "prompt": prompt
        }
        result = await suno_api_request("generate_lyrics", data)

        if result and 'lyrics' in result:
            await update.message.reply_text(f"Generated lyrics:\n\n{result['lyrics']}")
            await progress_message.delete()
        else:
            logger.error(f"Unexpected response from Suno API: {result}")
            await progress_message.edit_text("Sorry, I couldn't generate the lyrics. Please try again.")

    except Exception as e:
        logger.error(f"Suno lyrics generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while generating the lyrics: {str(e)}")
        record_error("suno_lyrics_generation_error")

@queue_task('long_run')
async def extend_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_extend_audio")
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Please provide the music ID and desired length after the /extend_audio command.")
        return

    music_id = context.args[0]
    length = context.args[1]
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested Suno audio extension for music ID: {music_id}")

    progress_message = await update.message.reply_text("🎵 Extending audio...")

    try:
        data = {
            "id": music_id,
            "length": length
        }
        result = await suno_api_request("extend_audio", data)

        if result and 'audio_url' in result:
            await update.message.reply_audio(audio=result['audio_url'], caption=f"Extended audio for music ID: {music_id}")
            await progress_message.delete()
        else:
            logger.error(f"Unexpected response from Suno API: {result}")
            await progress_message.edit_text("Sorry, I couldn't extend the audio. Please try again.")

    except Exception as e:
        logger.error(f"Suno audio extension error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while extending the audio: {str(e)}")
        record_error("suno_audio_extension_error")

@queue_task('long_run')
async def concat_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_command_usage("suno_concat_audio")
    if not context.args:
        await update.message.reply_text("Please provide music IDs after the /concat_audio command.")
        return

    music_ids = context.args
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested Suno audio concatenation for music IDs: {', '.join(music_ids)}")

    progress_message = await update.message.reply_text("🎵 Concatenating audio...")

    try:
        data = {
            "ids": music_ids
        }
        result = await suno_api_request("concat", data)

        if result and 'audio_url' in result:
            await update.message.reply_audio(audio=result['audio_url'], caption=f"Concatenated audio for music IDs: {', '.join(music_ids)}")
            await progress_message.delete()
        else:
            logger.error(f"Unexpected response from Suno API: {result}")
            await progress_message.edit_text("Sorry, I couldn't concatenate the audio. Please try again.")

    except Exception as e:
        logger.error(f"Suno audio concatenation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while concatenating the audio: {str(e)}")
        record_error("suno_audio_concatenation_error")

def setup_suno_handlers(application):
    application.add_handler(CommandHandler("generate_music", generate_music))
    application.add_handler(CommandHandler("custom_generate_music", custom_generate_music))
    application.add_handler(CommandHandler("get_music_info", get_music_info))
    application.add_handler(CommandHandler("get_quota_info", get_quota_info))
    application.add_handler(CommandHandler("generate_lyrics", generate_lyrics))
    application.add_handler(CommandHandler("extend_audio", extend_audio))
    application.add_handler(CommandHandler("concat_audio", concat_audio))