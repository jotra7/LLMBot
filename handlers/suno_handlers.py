import logging
import asyncio
import time
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

from config import ADMIN_USER_IDS, GENERATIONS_PER_DAY, SUNO_BASE_URL
from performance_metrics import record_command_usage, record_response_time, record_error
from queue_system import queue_task
from database import save_user_generation, get_user_generations_today
import aiohttp
import os
import aiofiles
from utils import openai_client
from telegram.error import BadRequest  
temporary_message_storage = {}

logger = logging.getLogger(__name__)

TITLE, IS_INSTRUMENTAL, LYRICS, TAGS, CONFIRM = range(5)
MAX_WAIT_TIME = 180 # Maximum wait time in seconds
MAX_GENERATIONS_PER_DAY = int(GENERATIONS_PER_DAY)

async def suno_api_request(endpoint, data=None, method='POST'):
    async with aiohttp.ClientSession() as session:
        url = f"{SUNO_BASE_URL}api/{endpoint}"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        try:
            if method == 'POST':
                async with session.post(url, json=data, headers=headers) as response:
                    response.raise_for_status()
                    json_response = await response.json()
                    # Log only non-sensitive information
                    log_response = [{k: v for k, v in item.items() if k not in ['lyric', 'prompt', 'image_url', 'audio_url', 'video_url']} for item in json_response] if isinstance(json_response, list) else json_response
                    logger.info(f"Response received for endpoint {endpoint}")
                    logger.debug(f"Response details: {log_response}")
                    return json_response
            elif method == 'GET':
                async with session.get(url, params=data, headers=headers) as response:
                    response.raise_for_status()
                    json_response = await response.json()
                    # Log only non-sensitive information
                    log_response = [{k: v for k, v in item.items() if k not in ['lyric']} for item in json_response] if isinstance(json_response, list) else json_response
                    logger.info(f"Response received for endpoint {endpoint}")
                    logger.debug(f"Response details: {log_response}")
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
        logger.info(f"Sending status check request for IDs: {', '.join(pending_ids)}")
        result = await suno_api_request("get", data=data, method='GET')
        logger.info(f"Received status check response for {len(result)} generations")

        if result and isinstance(result, list):
            for song_data in result:
                gen_id = song_data['id']
                status = song_data['status']
                logger.info(f"Generation ID: {gen_id}, Status: {status}")
                if status == 'complete':
                    if gen_id in pending_ids:
                        completed_generations.append(song_data)
                        pending_ids.remove(gen_id)
                        logger.info(f"Generation {gen_id} completed and added to completed_generations")
                elif status == 'failed':
                    logger.error(f"Generation {gen_id} failed.")
                    pending_ids.remove(gen_id)
        else:
            logger.error(f"Unexpected response format: {result}")
            break  # Exit loop if response is invalid

        if pending_ids:
            logger.info(f"Waiting for {len(pending_ids)} generations to complete. Sleeping for 10 seconds.")
            await asyncio.sleep(10)  # Wait for 10 seconds before checking again

    if pending_ids:
        logger.warning(f"Timed out waiting for generations: {', '.join(pending_ids)}")
    
    logger.info(f"Completed generations: {len(completed_generations)}, Pending: {len(pending_ids)}")
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


SUNO_GENERATION_TYPE = "suno"


@queue_task('long_run')
async def generate_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_command_usage("suno_generate_music")
    user_id = update.effective_user.id
    user_name = update.effective_user.username
    chat_id = update.effective_chat.id

    logger.info(f"Suno music generation requested by user {user_id} ({user_name})")

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    if user_generations_today >= MAX_GENERATIONS_PER_DAY:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Sorry {user_name}, you have reached your daily limit of {MAX_GENERATIONS_PER_DAY} generations."
        )
        return

    try:
        data = {
            "prompt": update.message.text,
            "make_instrumental": False,
            "model": "chirp-v3-5",
            "wait_audio": False
        }
        
        logger.info(f"Sending API request for user {user_id} with data: {data}")
        initial_message = await context.bot.send_message(
            chat_id=chat_id,
            text="🎵 Initiating music generation. Please wait..."
        )

        response = await suno_api_request('generate', data=data)
        logger.info(f"API response for user {user_id}: {response}")

        if response and isinstance(response, list) and len(response) > 0:
            generation_ids = [song_data['id'] for song_data in response]
            logger.info(f"Generation IDs for user {user_id}: {', '.join(generation_ids)}")
            
            completed_generations = await wait_for_generation(generation_ids, chat_id, context)
            
            if completed_generations:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=initial_message.message_id,
                    text=f"✅ All tracks generated. Preparing to send..."
                )

                for index, completed_generation in enumerate(completed_generations, 1):
                    generation_id = completed_generation['id']
                    if completed_generation.get('audio_url'):
                        title = completed_generation.get('title', f'Untitled Track {index}')
                        tags = completed_generation.get('tags', 'N/A')
                        description = completed_generation.get('gpt_description_prompt', 'No description available')
                        audio_url = completed_generation['audio_url']
                        
                        lyrics = completed_generation.get('lyric', '')
                        lyrics_summary = await generate_lyrics_summary(lyrics) if lyrics else "No lyrics available"

                        caption = (
                            f"🎵 Music Generation Complete! 🎵\n\n"
                            f"Track {index} of {len(completed_generations)}\n"
                            f"Title: {title}\n"
                            f"Tags: {tags}\n\n"
                            f"Description: {description}\n\n"
                            f"Lyrics Summary: {lyrics_summary}\n\n"
                            f"Audio Download Link: {audio_url}\n\n"
                            "Enjoy your generated music and video!"
                        )

                        # Use the title for file names, replacing spaces with underscores and removing any characters that might be problematic for filenames
                        safe_title = ''.join(c for c in title if c.isalnum() or c in (' ', '_')).rstrip()
                        safe_title = safe_title.replace(' ', '_')
                        
                        audio_file_name = f"{safe_title}.mp3"
                        video_file_name = f"{safe_title}.mp4"
                        thumb_file_name = f"{safe_title}_artwork.jpg"

                        logger.info(f"Preparing files for track: {title} (ID: {generation_id})")

                        try:
                            # Download audio
                            await download_mp3(audio_url, audio_file_name)
                            logger.info(f"Downloaded audio file: {audio_file_name}")
                            
                            # Download artwork if available
                            if completed_generation.get('image_url'):
                                await download_image(completed_generation['image_url'], thumb_file_name)
                                logger.info(f"Downloaded artwork: {thumb_file_name}")

                            # Send audio file with truncated caption if necessary
                            MAX_CAPTION_LENGTH = 1024  # Telegram's limit
                            if len(caption) > MAX_CAPTION_LENGTH:
                                truncated_caption = caption[:MAX_CAPTION_LENGTH-3] + "..."
                                full_description = caption  # Save full description for later
                                caption = truncated_caption

                            with open(audio_file_name, 'rb') as audio_file:
                                audio_message = await context.bot.send_audio(
                                    chat_id=chat_id,
                                    audio=audio_file,
                                    caption=caption,
                                    title=title,
                                    thumbnail=open(thumb_file_name, 'rb') if os.path.exists(thumb_file_name) else None,
                                )
                            logger.info(f"Sent audio message for track: {title} (ID: {generation_id})")

                            # If caption was truncated, send full description as a separate message
                            if len(caption) > MAX_CAPTION_LENGTH:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=full_description,
                                    reply_to_message_id=audio_message.message_id
                                )

                            # Check for video with extended waiting and retries
                            if completed_generation.get('video_url'):
                                video_url = completed_generation['video_url']
                                max_video_wait = 300  # 5 minutes
                                video_wait_interval = 10  # 10 seconds
                                video_start_time = time.time()
                                video_downloaded = False

                                while time.time() - video_start_time < max_video_wait and not video_downloaded:
                                    try:
                                        await download_video(video_url, video_file_name)
                                        logger.info(f"Downloaded video file: {video_file_name}")
                                        video_downloaded = True
                                    except Exception as e:
                                        if "403" in str(e):
                                            logger.warning(f"Video not ready yet (403 error) for ID {generation_id}. Retrying in {video_wait_interval} seconds...")
                                            await asyncio.sleep(video_wait_interval)
                                        else:
                                            raise

                                if video_downloaded and os.path.exists(video_file_name):
                                    with open(video_file_name, 'rb') as video_file:
                                        video_message = await context.bot.send_video(
                                            chat_id=chat_id,
                                            video=video_file,
                                            caption=f"Video for {title} (Track {index} of {len(completed_generations)})\n\nVideo Download Link: {video_url}",
                                            reply_to_message_id=audio_message.message_id
                                        )
                                    logger.info(f"Sent video message for track: {title} (ID: {generation_id})")
                                else:
                                    logger.warning(f"Video download failed or timed out for {title} (ID: {generation_id})")
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"The video for {title} is not available yet. You can try downloading it later using this link: {video_url}",
                                        reply_to_message_id=audio_message.message_id
                                    )
                            else:
                                logger.info(f"No video generated for {title} (ID: {generation_id})")

                        except Exception as e:
                            logger.error(f"Error processing generated content for track: {title} (ID: {generation_id}): {str(e)}")
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"Sorry, there was an issue processing track: {title}. Please use the download links:\n\nAudio: {audio_url}\nVideo: {completed_generation.get('video_url', 'Not available')}"
                            )
                        finally:
                            # Clean up files
                            for file in [audio_file_name, video_file_name, thumb_file_name]:
                                if os.path.exists(file):
                                    os.remove(file)
                                    logger.info(f"Removed file: {file}")

                        # Save user generation for each track
                        save_user_generation(user_id, data['prompt'], "suno")
                        logger.info(f"Saved generation for user {user_id}, track: {title}, generation ID: {generation_id}")

                # Delete the initial placeholder message
                await context.bot.delete_message(chat_id=chat_id, message_id=initial_message.message_id)
                
                # Get updated user's generations today
                user_generations_today = get_user_generations_today(user_id, "suno")
                remaining_generations = max(0, MAX_GENERATIONS_PER_DAY - user_generations_today)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"You have used {len(completed_generations)} generations. You have {remaining_generations} music generations left for today."
                )
            else:
                logger.warning(f"No completed generations for user {user_id} after waiting period")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=initial_message.message_id,
                    text="Sorry, no music was generated. Please try again."
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

async def download_video(video_url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(video_url) as response:
            if response.status == 200:
                with open(file_name, 'wb') as f:
                    f.write(await response.read())
                logger.info(f"Video file downloaded: {file_name}")
            else:
                logger.error(f"Failed to download video from {video_url}, status code: {response.status}")
                raise Exception(f"Failed to download video, status code: {response.status}")


async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['title'] = update.message.text
    reply_keyboard = [['Yes', 'No']]
    await update.message.reply_text(
        "Should this be an instrumental track?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return IS_INSTRUMENTAL

async def get_is_instrumental(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_instrumental = update.message.text.lower() == 'yes'
    context.user_data['make_instrumental'] = is_instrumental
    if is_instrumental:
        await update.message.reply_text(
            "What genre or style tags would you like for your instrumental? (e.g., 'pop metal male melancholic')",
            reply_markup=ReplyKeyboardRemove()
        )
        return TAGS
    else:
        await update.message.reply_text(
            "Please enter the lyrics for your song. Use line breaks to separate verses and choruses.",
            reply_markup=ReplyKeyboardRemove()
        )
        return LYRICS

async def get_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lyrics'] = update.message.text
    await update.message.reply_text("What genre or style tags would you like for your song? (e.g., 'pop metal male melancholic')")
    return TAGS

async def get_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['tags'] = update.message.text
    
    # Prepare confirmation message
    confirmation = f"Title: {context.user_data['title']}\n"
    confirmation += f"Instrumental: {'Yes' if context.user_data['make_instrumental'] else 'No'}\n"
    if not context.user_data['make_instrumental']:
        confirmation += f"Lyrics: {context.user_data['lyrics'][:50]}...\n"
    confirmation += f"Tags: {context.user_data['tags']}\n"
    
    confirmation += "\nIs this correct? Type 'yes' to generate or 'no' to start over."
    
    await update.message.reply_text(confirmation)
    return CONFIRM

async def start_custom_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_name = update.effective_user.username
    
    logger.info(f"Suno custom generation requested by user {user_id} ({user_name})")

    # Clear any existing conversation data
    context.user_data.clear()

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    if user_generations_today >= MAX_GENERATIONS_PER_DAY:
        await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_GENERATIONS_PER_DAY} generations.")
        return ConversationHandler.END

    await update.message.reply_text("Let's create a custom song! What's the title of your song?")
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['title'] = update.message.text
    reply_keyboard = [['Yes', 'No']]
    await update.message.reply_text(
        "Should this be an instrumental track?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return IS_INSTRUMENTAL

async def get_is_instrumental(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_instrumental = update.message.text.lower() == 'yes'
    context.user_data['make_instrumental'] = is_instrumental
    if is_instrumental:
        await update.message.reply_text(
            "What genre or style tags would you like for your instrumental? (e.g., 'pop metal male melancholic')",
            reply_markup=ReplyKeyboardRemove()
        )
        return TAGS
    else:
        await update.message.reply_text(
            "Please enter the lyrics for your song. Use line breaks to separate verses and choruses.",
            reply_markup=ReplyKeyboardRemove()
        )
        return LYRICS

async def get_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lyrics'] = update.message.text
    await update.message.reply_text("What genre or style tags would you like for your song? (e.g., 'pop metal male melancholic')")
    return TAGS

async def download_image(image_url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            if response.status == 200:
                async with aiofiles.open(file_name, 'wb') as f:
                    await f.write(await response.read())
                logger.info(f"Image file downloaded: {file_name}")
            else:
                logger.error(f"Failed to download image from {image_url}, status code: {response.status}")

async def get_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['tags'] = update.message.text
    
    # Prepare confirmation message
    confirmation = f"Title: {context.user_data['title']}\n"
    confirmation += f"Instrumental: {'Yes' if context.user_data['make_instrumental'] else 'No'}\n"
    if not context.user_data['make_instrumental']:
        confirmation += f"Lyrics: {context.user_data['lyrics'][:50]}...\n"
    confirmation += f"Tags: {context.user_data['tags']}\n"
    
    confirmation += "\nIs this correct? Type 'yes' to generate or 'no' to start over."
    
    await update.message.reply_text(confirmation)
    return CONFIRM

@queue_task('long_run')
async def generate_custom_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    record_command_usage("suno_custom_song")
    if update.message.text.lower() != 'yes':
        await update.message.reply_text("Generation cancelled. Please start over with /custom_generate_music")
        return ConversationHandler.END

    user_id = update.effective_user.id
    user_name = update.effective_user.username
    chat_id = update.effective_chat.id

    logger.info(f"Custom Suno generation requested by user {user_id} ({user_name})")

    try:
        # Check user's daily limit
        user_generations_today = get_user_generations_today(user_id, "suno")
        logger.info(f"User {user_id} has generated {user_generations_today} times today")
        if user_generations_today >= MAX_GENERATIONS_PER_DAY:
            await update.message.reply_text(f"Sorry {user_name}, you have reached your daily limit of {MAX_GENERATIONS_PER_DAY} generations.")
            return ConversationHandler.END

        data = {
            "title": context.user_data['title'],
            "prompt": context.user_data.get('lyrics', ''),
            "tags": context.user_data['tags'],
            "make_instrumental": context.user_data['make_instrumental'],
            "model": "chirp-v3-5|chirp-v3-0",
            "wait_audio": False
        }
        
        logger.info(f"Sending API request for user {user_id} with data: {data}")
        response = await suno_api_request('custom_generate', data=data)
        logger.info(f"API response for user {user_id}: {response}")

        if response and isinstance(response, list) and len(response) > 0:
            generation_ids = [song_data['id'] for song_data in response]
            logger.info(f"Generation IDs for user {user_id}: {', '.join(generation_ids)}")
            
            initial_message = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎵 Custom music generation started. Generating {len(generation_ids)} tracks. Please wait..."
            )
            
            completed_generations = await wait_for_generation(generation_ids, chat_id, context)
            
            if completed_generations:
                for index, completed_generation in enumerate(completed_generations, 1):
                    if completed_generation.get('audio_url'):
                        title = completed_generation.get('title', f'Untitled Track {index}')
                        tags = completed_generation.get('tags', 'N/A')
                        generation_id = completed_generation['id']
                        audio_url = completed_generation['audio_url']
                        
                        caption = (
                            f"🎵 Custom Music Generation Complete! 🎵\n\n"
                            f"Track {index} of {len(completed_generations)}\n"
                            f"Title: {title}\n"
                            f"Tags: {tags}\n\n"
                            f"Audio Download Link: {audio_url}\n\n"
                            "Enjoy your generated music and video!"
                        )

                        audio_file_name = f"{title}.mp3"
                        video_file_name = f"{title}.mp4"
                        thumb_file_name = f"{generation_id}_artwork.jpg"

                        try:
                            # Download audio
                            await download_mp3(audio_url, audio_file_name)
                            
                            # Download artwork if available
                            if completed_generation.get('image_url'):
                                await download_image(completed_generation['image_url'], thumb_file_name)

                            # Send audio file
                            with open(audio_file_name, 'rb') as audio_file:
                                audio_message = await context.bot.send_audio(
                                    chat_id=chat_id,
                                    audio=audio_file,
                                    caption=caption,
                                    title=title,
                                    thumbnail=open(thumb_file_name, 'rb') if os.path.exists(thumb_file_name) else None,
                                )

                            # Check for video with a longer timeout
                            video_wait_time = 300  # 5 minutes
                            video_check_interval = 30  # Check every 30 seconds
                            for _ in range(video_wait_time // video_check_interval):
                                video_result = await suno_api_request("get", {"id": generation_id}, method='GET')
                                if video_result and video_result[0].get('video_url'):
                                    video_url = video_result[0]['video_url']
                                    await download_video(video_url, video_file_name)
                                    if os.path.exists(video_file_name):
                                        with open(video_file_name, 'rb') as video_file:
                                            video_message = await context.bot.send_video(
                                                chat_id=chat_id,
                                                video=video_file,
                                                caption=f"Video for {title} (Track {index} of {len(completed_generations)})\n\nVideo Download Link: {video_url}",
                                                reply_to_message_id=audio_message.message_id
                                            )
                                        break
                                await asyncio.sleep(video_check_interval)
                            else:
                                logger.info(f"No video generated for {title} after waiting period")

                        except Exception as e:
                            logger.error(f"Error processing generated content for track {index}: {str(e)}")
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"Sorry, there was an issue processing track {index}. Please use the download links:\n\nAudio: {audio_url}\nVideo: {video_url if 'video_url' in locals() else 'Not available'}"
                            )
                        finally:
                            # Clean up files
                            for file in [audio_file_name, video_file_name, thumb_file_name]:
                                if os.path.exists(file):
                                    os.remove(file)

                        # Save user generation for each track
                        save_user_generation(user_id, data['prompt'], "suno")

                # Delete the initial placeholder message
                await context.bot.delete_message(chat_id=chat_id, message_id=initial_message.message_id)
                
                # Get updated user's generations today
                user_generations_today = get_user_generations_today(user_id, "suno")
                remaining_generations = max(0, MAX_GENERATIONS_PER_DAY - user_generations_today)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"You have used {len(completed_generations)} generations. You have {remaining_generations} music generations left for today."
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=initial_message.message_id,
                    text="Sorry, no music was generated. Please try again."
                )
        else:
            logger.error(f"Suno custom music generation failed for user {user_id}. Response: {response}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Failed to generate music. Please try again later."
            )

    except Exception as e:
        logger.error(f"Suno custom music generation error for user {user_id}: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while generating your music. Please try again later."
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Custom music generation cancelled. Feel free to start over when you're ready.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def setup_custom_music_handler(application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("custom_generate_music", start_custom_generation)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            IS_INSTRUMENTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_is_instrumental)],
            LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lyrics)],
            TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tags)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_custom_music)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("custom_generate_music", start_custom_generation)
        ],
        allow_reentry=True
    )
    application.add_handler(conv_handler)

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
@queue_task('long_run')
async def generate_instrumental(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_command_usage("suno_instrumental")
    user_id = update.effective_user.id
    user_name = update.effective_user.username
    chat_id = update.effective_chat.id

    logger.info(f"Suno instrumental generation requested by user {user_id} ({user_name})")

    user_generations_today = get_user_generations_today(user_id, "suno")
    logger.info(f"User {user_id} has generated {user_generations_today} times today")
    if user_generations_today >= MAX_GENERATIONS_PER_DAY:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Sorry {user_name}, you have reached your daily limit of {MAX_GENERATIONS_PER_DAY} generations."
        )
        return

    try:
        data = {
            "prompt": update.message.text,
            "make_instrumental": True,
            "model": "chirp-v3-5",
            "wait_audio": False
        }
        
        logger.info(f"Sending API request for user {user_id} with data: {data}")
        response = await suno_api_request('generate', data=data)
        logger.info(f"API response for user {user_id}: {response}")

        if response and isinstance(response, list) and len(response) > 0:
            generation_ids = [song_data['id'] for song_data in response]
            logger.info(f"Instrumental Generation IDs for user {user_id}: {', '.join(generation_ids)}")
            
            initial_message = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎵 Instrumental music generation started. Generating {len(generation_ids)} tracks. Please wait..."
            )
            
            completed_generations = await wait_for_generation(generation_ids, chat_id, context)
            
            if completed_generations:
                for index, completed_generation in enumerate(completed_generations, 1):
                    generation_id = completed_generation['id']
                    
                    # Wait for the generation to complete
                    max_wait_time = 600  # 10 minutes
                    wait_interval = 10  # 10 seconds
                    for _ in range(max_wait_time // wait_interval):
                        status_response = await suno_api_request("get", {"id": generation_id}, method='GET')
                        if status_response and status_response[0].get('status') == 'complete':
                            completed_generation = status_response[0]
                            break
                        await asyncio.sleep(wait_interval)
                    else:
                        logger.error(f"Generation {generation_id} did not complete in time")
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"Sorry, the generation for instrumental track {index} timed out. Please try again later."
                        )
                        continue

                    if completed_generation.get('audio_url'):
                        title = completed_generation.get('title', f'Untitled Instrumental {index}')
                        tags = completed_generation.get('tags', 'N/A')
                        description = completed_generation.get('gpt_description_prompt', 'No description available')
                        audio_url = completed_generation['audio_url']
                        
                        caption = (
                            f"🎵 Instrumental Music Generation Complete! 🎵\n\n"
                            f"Track {index} of {len(completed_generations)}\n"
                            f"Title: {title}\n"
                            f"Tags: {tags}\n\n"
                            f"Description: {description}\n\n"
                            f"Audio Download Link: {audio_url}\n\n"
                            "Enjoy your generated instrumental music and video!"
                        )

                        audio_file_name = f"{title}.mp3"
                        video_file_name = f"{title}.mp4"
                        thumb_file_name = f"{generation_id}_artwork.jpg"

                        try:
                            # Download audio
                            await download_mp3(audio_url, audio_file_name)
                            
                            # Download artwork if available
                            if completed_generation.get('image_url'):
                                await download_image(completed_generation['image_url'], thumb_file_name)

                            # Send audio file with truncated caption if necessary
                            MAX_CAPTION_LENGTH = 1024  # Telegram's limit
                            if len(caption) > MAX_CAPTION_LENGTH:
                                truncated_caption = caption[:MAX_CAPTION_LENGTH-3] + "..."
                                full_description = caption  # Save full description for later
                                caption = truncated_caption

                            with open(audio_file_name, 'rb') as audio_file:
                                audio_message = await context.bot.send_audio(
                                    chat_id=chat_id,
                                    audio=audio_file,
                                    caption=caption,
                                    title=title,
                                    thumbnail=open(thumb_file_name, 'rb') if os.path.exists(thumb_file_name) else None,
                                )

                            # If caption was truncated, send full description as a separate message
                            if len(caption) > MAX_CAPTION_LENGTH:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=full_description,
                                    reply_to_message_id=audio_message.message_id
                                )

                            # Check for video
                            if completed_generation.get('video_url'):
                                video_url = completed_generation['video_url']
                                await download_video(video_url, video_file_name)
                                if os.path.exists(video_file_name):
                                    with open(video_file_name, 'rb') as video_file:
                                        video_message = await context.bot.send_video(
                                            chat_id=chat_id,
                                            video=video_file,
                                            caption=f"Video for {title} (Instrumental Track {index} of {len(completed_generations)})\n\nVideo Download Link: {video_url}",
                                            reply_to_message_id=audio_message.message_id
                                        )
                            else:
                                logger.info(f"No video generated for instrumental {title}")

                        except Exception as e:
                            logger.error(f"Error processing generated instrumental content for track {index}: {str(e)}")
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"Sorry, there was an issue processing instrumental track {index}. Please use the download links:\n\nAudio: {audio_url}\nVideo: {completed_generation.get('video_url', 'Not available')}"
                            )
                        finally:
                            # Clean up files
                            for file in [audio_file_name, video_file_name, thumb_file_name]:
                                if os.path.exists(file):
                                    os.remove(file)

                        # Save user generation for each track
                        save_user_generation(user_id, data['prompt'], "suno")

                # Delete the initial placeholder message
                await context.bot.delete_message(chat_id=chat_id, message_id=initial_message.message_id)
                
                # Get updated user's generations today
                user_generations_today = get_user_generations_today(user_id, "suno")
                remaining_generations = max(0, MAX_GENERATIONS_PER_DAY - user_generations_today)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"You have used {len(completed_generations)} generations. You have {remaining_generations} music generations left for today."
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=initial_message.message_id,
                    text="Sorry, no instrumental music was generated. Please try again."
                )
        else:
            logger.error(f"Suno instrumental music generation failed for user {user_id}. Response: {response}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Failed to generate instrumental music. Please try again later."
            )
    except Exception as e:
        logger.error(f"Suno instrumental music generation error for user {user_id}: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while generating your instrumental music. Please try again later."
        )
def setup_suno_handlers(application):
    application.add_handler(CommandHandler("generate_music", generate_music))
    application.add_handler(CommandHandler("generate_instrumental", generate_instrumental))
    # Remove the direct handler for custom_generate_music
    # application.add_handler(CommandHandler("custom_generate_music", generate_custom_music))
    application.add_handler(CommandHandler("get_music_info", get_music_info))
    application.add_handler(CommandHandler("get_quota_info", get_quota_info))
    application.add_handler(CommandHandler("generate_lyrics", generate_lyrics))
    application.add_handler(CommandHandler("extend_audio", extend_audio))
    application.add_handler(CommandHandler("concat_audio", concat_audio))
    setup_custom_music_handler(application)