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
import aiofiles
from utils import openai_client


logger = logging.getLogger(__name__)

SUNO_API_BASE_URL = ""
MAX_GENERATIONS_PER_DAY = 30
MAX_WAIT_TIME = 180 # Maximum wait time in seconds

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
                async with session.get(url, params=data, headers=headers) as response:
                    logger.info(f"GET request to {url} with params: {data}")
                    response.raise_for_status()
                    json_response = await response.json()
                    logger.info(f"Response: {json_response}")
                    return json_response
        except aiohttp.ClientResponseError as e:
            logger.error(f"API request failed: {e.status} {str(e)}")
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

async def wait_for_generation(generation_ids, chat_id, context):
    start_time = time.time()
    await context.bot.send_message(
        chat_id=chat_id,
        text="🎵 Music generation started. Please wait while your music is being created..."
    )
    
    pending_ids = set(generation_ids)
    completed_generations = []

    while time.time() - start_time < MAX_WAIT_TIME and pending_ids:
        data = {"ids": ','.join(pending_ids)}
        result = await suno_api_request("get", data=data, method='GET')

        if result and isinstance(result, list):
            for song_data in result:
                gen_id = song_data['id']
                status = song_data['status']
                if status == 'complete' or status == 'streaming':
                    if gen_id in pending_ids:
                        completed_generations.append(song_data)
                        pending_ids.remove(gen_id)
                elif status == 'failed':
                    logger.error(f"Generation {gen_id} failed.")
                    pending_ids.remove(gen_id)
        else:
            logger.error(f"Unexpected response format: {result}")
            break  # Exit loop if response is invalid

        await asyncio.sleep(10)  # Wait for 10 seconds before checking again

    return completed_generations

async def generate_lyrics_summary(lyrics):
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes song lyrics.  You do not provide all of  the lyrics, just a nice summary."},
                {"role": "user", "content": f"Please provide a brief summary of these lyrics:\n\n{lyrics}"}
            ],
            max_tokens=100,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating lyrics summary: {e}")
        return "Unable to generate lyrics summary."


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
            generation_ids = [song_data['id'] for song_data in response]
            prompt = data['prompt']
            logger.info(f"Generation IDs for user {user_id}: {', '.join(generation_ids)}")
            
            # Send initial message
            initial_message = await context.bot.send_message(
                chat_id=chat_id,
                text="🎵 Music generation started. Fetching initial details..."
            )
            
            # Wait for the initial generation details
            initial_details = await wait_for_initial_details(generation_ids, chat_id, context, initial_message)
            
            if initial_details:
                for details in initial_details:
                    # Update message with initial details
                    caption = f"Your music is being generated!\n\n"
                    caption += f"Title: {details.get('title', 'Untitled')}\n"
                    caption += f"Tags: {details.get('tags', 'N/A')}\n"
                    if 'gpt_description_prompt' in details:
                        caption += f"\nDescription: {details['gpt_description_prompt']}\n"
                    
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=initial_message.message_id,
                        text=caption + "\nGenerating lyrics summary..."
                    )
                    
                    # Generate lyrics summary if lyrics are available
                    if 'lyric' in details:
                        lyrics_summary = await generate_lyrics_summary(details['lyric'])
                        caption += f"\nLyrics Summary: {lyrics_summary}\n"
                    
                    caption += "\nPreparing audio...\n"
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=initial_message.message_id,
                        text=caption
                    )
                    
                    # Now wait for the audio to be ready
                    completed_generation = await wait_for_audio(details['id'], chat_id, context, initial_message, caption)
                    
                    if completed_generation and completed_generation.get('audio_url'):
                        audio_url = completed_generation['audio_url']
                        title = completed_generation.get('title', 'Untitled')
                        file_name = f"{title}.mp3"
                        
                        # Download the MP3 file
                        try:
                            await download_mp3(audio_url, file_name)
                        except Exception as e:
                            logger.error(f"Error downloading MP3: {str(e)}")
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=initial_message.message_id,
                                text=caption + "Sorry, there was an issue downloading your music. Please try again."
                            )
                            continue
                        
                        # Download artwork if available
                        artwork_url = completed_generation.get('image_url')
                        thumb_file = None
                        if artwork_url:
                            try:
                                thumb_file_name = f"{completed_generation['id']}_artwork.jpg"
                                await download_image(artwork_url, thumb_file_name)
                                thumb_file = thumb_file_name
                            except Exception as e:
                                logger.error(f"Error downloading image: {str(e)}")
                        
                        # Send the MP3 file to the user
                        try:
                            with open(file_name, 'rb') as audio_file:
                                await context.bot.send_audio(
                                    chat_id=chat_id,
                                    audio=audio_file,
                                    title=title,
                                    caption="Here's your generated music!",
                                    thumbnail=thumb_file,
                                    reply_to_message_id=initial_message.message_id
                                )
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=initial_message.message_id,
                                text=caption + "Music generation complete! Enjoy your track above."
                            )
                        except Exception as e:
                            logger.error(f"Error sending audio: {str(e)}")
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=initial_message.message_id,
                                text=caption + "Sorry, there was an issue sending your music. Please try again."
                            )
                        
                        # Clean up the files after sending
                        try:
                            os.remove(file_name)
                            if thumb_file and os.path.exists(thumb_file):
                                os.remove(thumb_file)
                        except Exception as e:
                            logger.error(f"Error cleaning up files: {str(e)}")
                        
                        # Save user generation with prompt and generation_id
                        save_user_generation(user_id, prompt, completed_generation['id'])
                    else:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=initial_message.message_id,
                            text=caption + "Sorry, there was an issue generating your music. Please try again."
                        )
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=initial_message.message_id,
                    text="Sorry, there was an issue generating your music. Please try again."
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

async def wait_for_initial_details(generation_ids, chat_id, context, message):
    start_time = time.time()
    
    while time.time() - start_time < MAX_WAIT_TIME:
        data = {"ids": ','.join(generation_ids)}
        result = await suno_api_request("get", data=data, method='GET')

        if result and isinstance(result, list):
            details = [song for song in result if song.get('title') and song.get('tags')]
            if details:
                return details

        await asyncio.sleep(5)  # Wait for 5 seconds before checking again
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=f"🎵 Music generation started. Fetching initial details...\nElapsed time: {int(time.time() - start_time)}s"
        )
    
    return None

async def wait_for_audio(generation_id, chat_id, context, message, caption):
    start_time = time.time()
    while time.time() - start_time < MAX_WAIT_TIME:
        data = {"ids": generation_id}
        result = await suno_api_request("get", data=data, method='GET')

        if result and isinstance(result, list) and len(result) > 0:
            song_data = result[0]
            if song_data.get('status') == 'complete' and song_data.get('audio_url'):
                return song_data

        await asyncio.sleep(5)  # Wait for 5 seconds before checking again
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=f"{caption}Audio generation in progress... (Elapsed time: {int(time.time() - start_time)}s)"
        )
    
    return None

async def download_mp3(audio_url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as response:
            if response.status == 200:
                async with aiofiles.open(file_name, 'wb') as f:
                    await f.write(await response.read())
                logger.info(f"MP3 file downloaded: {file_name}")
            else:
                logger.error(f"Failed to download MP3 from {audio_url}, status code: {response.status}")

async def download_image(image_url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            if response.status == 200:
                async with aiofiles.open(file_name, 'wb') as f:
                    await f.write(await response.read())
                logger.info(f"Image file downloaded: {file_name}")
            else:
                logger.error(f"Failed to download image from {image_url}, status code: {response.status}")

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

    logger.info(f"User {user_id} requested Suno custom music generation.")

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
        response = await suno_api_request("custom_generate", data)

        if response and isinstance(response, list) and len(response) > 0:
            generation_ids = [song_data['id'] for song_data in response]
            logger.info(f"Generation IDs for user {user_id}: {', '.join(generation_ids)}")

            await progress_message.edit_text("🎵 Custom music generation in progress. This may take up to 2 minutes...")

            # Wait for the generations to complete
            completed_generations = await wait_for_generation(generation_ids, update.effective_chat.id, context)

            if completed_generations:
                for completed_generation in completed_generations:
                    if completed_generation.get('audio_url'):
                        audio_url = completed_generation['audio_url']
                        file_name = f"{completed_generation.get('title', 'Untitled')}.mp3"

                        # Download the MP3 file
                        await download_mp3(audio_url, file_name)

                        # Download artwork if available
                        artwork_url = completed_generation.get('image_url')
                        thumb_file = None
                        if artwork_url:
                            thumb_file_name = f"{completed_generation['title', 'Untitled']}_artwork.jpg"
                            await download_image(artwork_url, thumb_file_name)
                            thumb_file = thumb_file_name

                        # Send the MP3 file to the user
                        with open(file_name, 'rb') as audio_file:
                            await context.bot.send_audio(
                                chat_id=update.effective_chat.id,
                                audio=audio_file,
                                title=completed_generation.get('title', title),
                                caption=f"Here is your custom generated music!\n\nTitle: {completed_generation.get('title')}",
                                thumbnail=thumb_file,
                            )

                        # Clean up the files after sending
                        os.remove(file_name)
                        if thumb_file:
                            os.remove(thumb_file_name)

                        # Save user generation
                        save_user_generation(user_id, prompt, completed_generation['id'])
            else:
                raise TimeoutError("Custom music generation timed out")

            end_time = time.time()
            response_time = end_time - start_time
            record_response_time(response_time)
            logger.info(f"Suno custom music generation process completed in {response_time:.2f} seconds")

        else:
            raise ValueError("Invalid response from Suno API")

    except Exception as e:
        logger.error(f"Suno custom music generation error for user {user_id}: {str(e)}")
        await progress_message.edit_text(f"An error occurred while generating the custom music. Please try again later.")
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