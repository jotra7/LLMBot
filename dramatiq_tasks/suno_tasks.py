# suno_tasks.py

import dramatiq
import logging
from performance_metrics import record_response_time, record_error
from database import save_conversation, save_user_generation, get_user_generations_today
from config import SUNO_BASE_URL, TELEGRAM_BOT_TOKEN, MAX_GENERATIONS_PER_DAY
import time
import asyncio
import aiohttp
from telegram import Bot
import os
from utils import openai_client

logger = logging.getLogger(__name__)

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
                    return await response.json()
            elif method == 'GET':
                async with session.get(url, params=data, headers=headers) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"API request failed: {str(e)}")
            raise

async def wait_for_generation(generation_ids):
    MAX_WAIT_TIME = 180
    start_time = time.time()
    pending_ids = set(generation_ids)
    completed_generations = []

    while time.time() - start_time < MAX_WAIT_TIME and pending_ids:
        data = {"ids": ','.join(pending_ids)}
        result = await suno_api_request("get", data=data, method='GET')

        if result and isinstance(result, list):
            for song_data in result:
                gen_id = song_data['id']
                status = song_data['status']
                if status == 'complete':
                    if gen_id in pending_ids:
                        completed_generations.append(song_data)
                        pending_ids.remove(gen_id)
                elif status == 'failed':
                    pending_ids.remove(gen_id)

        if pending_ids:
            await asyncio.sleep(10)

    return completed_generations

async def generate_lyrics_summary(lyrics):
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes song lyrics. You do not provide all of the lyrics, just a nice summary."},
                {"role": "user", "content": f"Please provide a brief summary of these lyrics:\n\n{lyrics}"}
            ],
            max_tokens=100,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating lyrics summary: {e}")
        return "Unable to generate lyrics summary."

async def download_mp3(audio_url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as response:
            if response.status == 200:
                with open(file_name, 'wb') as f:
                    f.write(await response.read())
                logger.info(f"MP3 file downloaded: {file_name}")
            else:
                logger.error(f"Failed to download MP3 from {audio_url}, status code: {response.status}")

async def download_image(image_url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            if response.status == 200:
                with open(file_name, 'wb') as f:
                    f.write(await response.read())
                logger.info(f"Image file downloaded: {file_name}")
            else:
                logger.error(f"Failed to download image from {image_url}, status code: {response.status}")

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

@dramatiq.actor
def generate_music_task(prompt: str, user_id: int, chat_id: int, make_instrumental: bool = False):
    start_time = time.time()
    try:
        logger.info(f"Starting {'instrumental ' if make_instrumental else ''}music generation for user {user_id} with prompt: '{prompt}'")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        data = {
            "prompt": prompt,
            "make_instrumental": make_instrumental,
            "model": "chirp-v3-5",
            "wait_audio": False
        }

        response = loop.run_until_complete(suno_api_request('generate', data=data))
        
        if response and isinstance(response, list) and len(response) > 0:
            generation_ids = [song_data['id'] for song_data in response]
            completed_generations = loop.run_until_complete(wait_for_generation(generation_ids))
            
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            
            for index, completed_generation in enumerate(completed_generations, 1):
                generation_id = completed_generation['id']
                if completed_generation.get('audio_url'):
                    title = completed_generation.get('title', f'Untitled Track {index}')
                    tags = completed_generation.get('tags', 'N/A')
                    description = completed_generation.get('gpt_description_prompt', 'No description available')
                    audio_url = completed_generation['audio_url']
                    
                    lyrics = completed_generation.get('lyric', '')
                    lyrics_summary = loop.run_until_complete(generate_lyrics_summary(lyrics)) if lyrics else "No lyrics available"

                    caption = (
                        f"🎵 {'Instrumental ' if make_instrumental else ''}Music Generation Complete! 🎵\n\n"
                        f"Track {index} of {len(completed_generations)}\n"
                        f"Title: {title}\n"
                        f"Tags: {tags}\n\n"
                        f"Description: {description}\n\n"
                        f"{'Instrumental' if make_instrumental else 'Lyrics'} Summary: {lyrics_summary if not make_instrumental else 'Instrumental track'}\n\n"
                        f"Audio Download Link: {audio_url}\n\n"
                        "Enjoy your generated music and video!"
                    )

                    safe_title = ''.join(c for c in title if c.isalnum() or c in (' ', '_')).rstrip()
                    safe_title = safe_title.replace(' ', '_')
                    
                    audio_file_name = f"{safe_title}.mp3"
                    video_file_name = f"{safe_title}.mp4"
                    thumb_file_name = f"{safe_title}_artwork.jpg"

                    try:
                        loop.run_until_complete(download_mp3(audio_url, audio_file_name))
                        
                        if completed_generation.get('image_url'):
                            loop.run_until_complete(download_image(completed_generation['image_url'], thumb_file_name))

                        MAX_CAPTION_LENGTH = 1024
                        if len(caption) > MAX_CAPTION_LENGTH:
                            truncated_caption = caption[:MAX_CAPTION_LENGTH-3] + "..."
                            full_description = caption
                            caption = truncated_caption

                        with open(audio_file_name, 'rb') as audio_file:
                            audio_message = loop.run_until_complete(bot.send_audio(
                                chat_id=chat_id,
                                audio=audio_file,
                                caption=caption,
                                title=title,
                                thumbnail=open(thumb_file_name, 'rb') if os.path.exists(thumb_file_name) else None,
                            ))

                        if len(caption) > MAX_CAPTION_LENGTH:
                            loop.run_until_complete(bot.send_message(
                                chat_id=chat_id,
                                text=full_description,
                                reply_to_message_id=audio_message.message_id
                            ))

                        if completed_generation.get('video_url'):
                            video_url = completed_generation['video_url']
                            max_video_wait = 300
                            video_wait_interval = 10
                            video_start_time = time.time()
                            video_downloaded = False

                            while time.time() - video_start_time < max_video_wait and not video_downloaded:
                                try:
                                    loop.run_until_complete(download_video(video_url, video_file_name))
                                    video_downloaded = True
                                except Exception as e:
                                    if "403" in str(e):
                                        logger.warning(f"Video not ready yet (403 error) for ID {generation_id}. Retrying in {video_wait_interval} seconds...")
                                        loop.run_until_complete(asyncio.sleep(video_wait_interval))
                                    else:
                                        raise

                            if video_downloaded and os.path.exists(video_file_name):
                                with open(video_file_name, 'rb') as video_file:
                                    loop.run_until_complete(bot.send_video(
                                        chat_id=chat_id,
                                        video=video_file,
                                        caption=f"Video for {title} (Track {index} of {len(completed_generations)})\n\nVideo Download Link: {video_url}",
                                        reply_to_message_id=audio_message.message_id
                                    ))
                            else:
                                loop.run_until_complete(bot.send_message(
                                    chat_id=chat_id,
                                    text=f"The video for {title} is not available yet. You can try downloading it later using this link: {video_url}",
                                    reply_to_message_id=audio_message.message_id
                                ))

                    except Exception as e:
                        logger.error(f"{'Instrumental ' if make_instrumental else ''}Music generation error for user {user_id}: {str(e)}")
                        record_error("suno_music_generation_error")
                        send_error_message.send(chat_id, str(e))
                    finally:
                        for file in [audio_file_name, video_file_name, thumb_file_name]:
                            if os.path.exists(file):
                                os.remove(file)

            save_user_generation(user_id, prompt, "suno")
        
        end_time = time.time()
        record_response_time(end_time - start_time)
        logger.info(f"Music generated in {end_time - start_time:.2f} seconds for user {user_id}")
    
    except Exception as e:
        logger.error(f"Music generation error for user {user_id}: {str(e)}")
        record_error("suno_music_generation_error")
        send_error_message.send(chat_id, str(e))

@dramatiq.actor
def send_error_message(chat_id: int, error: str):
    logger.info(f"Sending error message to chat {chat_id}")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred during music generation: {error}"))
        logger.info(f"Error message sent successfully to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending error message to chat {chat_id}: {str(e)}")
    finally:
        loop.close()
@dramatiq.actor
def send_error_message(chat_id: int, error: str):
    logger.info(f"Sending error message to chat {chat_id}")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=f"An error occurred during music generation: {error}"))
        logger.info(f"Error message sent successfully to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending error message to chat {chat_id}: {str(e)}")
    finally:
        loop.close()

@dramatiq.actor
def generate_custom_music_task(title: str, make_instrumental: bool, lyrics: str, tags: str, user_id: int, chat_id: int):
    start_time = time.time()
    try:
        logger.info(f"Starting custom music generation for user {user_id}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        data = {
            "title": title,
            "prompt": lyrics if not make_instrumental else "",
            "tags": tags,
            "make_instrumental": make_instrumental,
            "model": "chirp-v3-5|chirp-v3-0",
            "wait_audio": False
        }

        response = loop.run_until_complete(suno_api_request('custom_generate', data=data))
        
        if response and isinstance(response, list) and len(response) > 0:
            generation_ids = [song_data['id'] for song_data in response]
            completed_generations = loop.run_until_complete(wait_for_generation(generation_ids))
            
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            
            for index, completed_generation in enumerate(completed_generations, 1):
                # Process each generated track
                generation_id = completed_generation['id']
                if completed_generation.get('audio_url'):
                    title = completed_generation.get('title', f'Untitled Custom Track {index}')
                    tags = completed_generation.get('tags', 'N/A')
                    description = completed_generation.get('gpt_description_prompt', 'No description available')
                    audio_url = completed_generation['audio_url']
                    
                    lyrics = completed_generation.get('lyric', '')
                    lyrics_summary = loop.run_until_complete(generate_lyrics_summary(lyrics)) if lyrics else "No lyrics available"

                    caption = (
                        f"🎵 Custom Music Generation Complete! 🎵\n\n"
                        f"Track {index} of {len(completed_generations)}\n"
                        f"Title: {title}\n"
                        f"Tags: {tags}\n\n"
                        f"Description: {description}\n\n"
                        f"Lyrics Summary: {lyrics_summary}\n\n"
                        f"Audio Download Link: {audio_url}\n\n"
                        "Enjoy your generated music and video!"
                    )

                    safe_title = ''.join(c for c in title if c.isalnum() or c in (' ', '_')).rstrip()
                    safe_title = safe_title.replace(' ', '_')
                    
                    audio_file_name = f"{safe_title}.mp3"
                    video_file_name = f"{safe_title}.mp4"
                    thumb_file_name = f"{safe_title}_artwork.jpg"

                    try:
                        loop.run_until_complete(download_mp3(audio_url, audio_file_name))
                        
                        if completed_generation.get('image_url'):
                            loop.run_until_complete(download_image(completed_generation['image_url'], thumb_file_name))

                        MAX_CAPTION_LENGTH = 1024
                        if len(caption) > MAX_CAPTION_LENGTH:
                            truncated_caption = caption[:MAX_CAPTION_LENGTH-3] + "..."
                            full_description = caption
                            caption = truncated_caption

                        with open(audio_file_name, 'rb') as audio_file:
                            audio_message = loop.run_until_complete(bot.send_audio(
                                chat_id=chat_id,
                                audio=audio_file,
                                caption=caption,
                                title=title,
                                thumbnail=open(thumb_file_name, 'rb') if os.path.exists(thumb_file_name) else None,
                            ))

                        if len(caption) > MAX_CAPTION_LENGTH:
                            loop.run_until_complete(bot.send_message(
                                chat_id=chat_id,
                                text=full_description,
                                reply_to_message_id=audio_message.message_id
                            ))

                        # Process video if available
                        if completed_generation.get('video_url'):
                            video_url = completed_generation['video_url']
                            max_video_wait = 300
                            video_wait_interval = 10
                            video_start_time = time.time()
                            video_downloaded = False

                            while time.time() - video_start_time < max_video_wait and not video_downloaded:
                                try:
                                    loop.run_until_complete(download_video(video_url, video_file_name))
                                    video_downloaded = True
                                except Exception as e:
                                    if "403" in str(e):
                                        logger.warning(f"Video not ready yet (403 error) for custom track ID {generation_id}. Retrying in {video_wait_interval} seconds...")
                                        loop.run_until_complete(asyncio.sleep(video_wait_interval))
                                    else:
                                        raise

                            if video_downloaded and os.path.exists(video_file_name):
                                with open(video_file_name, 'rb') as video_file:
                                    loop.run_until_complete(bot.send_video(
                                        chat_id=chat_id,
                                        video=video_file,
                                        caption=f"Video for {title} (Custom Track {index} of {len(completed_generations)})\n\nVideo Download Link: {video_url}",
                                        reply_to_message_id=audio_message.message_id
                                    ))
                            else:
                                loop.run_until_complete(bot.send_message(
                                    chat_id=chat_id,
                                    text=f"The video for custom track {title} is not available yet. You can try downloading it later using this link: {video_url}",
                                    reply_to_message_id=audio_message.message_id
                                ))

                    except Exception as e:
                        logger.error(f"Error processing generated custom content for track: {title} (ID: {generation_id}): {str(e)}")
                        loop.run_until_complete(bot.send_message(
                            chat_id=chat_id,
                            text=f"Sorry, there was an issue processing custom track: {title}. Please use the download links:\n\nAudio: {audio_url}\nVideo: {completed_generation.get('video_url', 'Not available')}"
                        ))
                    finally:
                        for file in [audio_file_name, video_file_name, thumb_file_name]:
                            if os.path.exists(file):
                                os.remove(file)

            save_user_generation(user_id, data['prompt'], "suno")
            
            user_generations_today = get_user_generations_today(user_id, "suno")
            remaining_generations = max(0, MAX_GENERATIONS_PER_DAY - user_generations_today)
            loop.run_until_complete(bot.send_message(
                chat_id=chat_id,
                text=f"You have used {len(completed_generations)} custom generations. You have {remaining_generations} music generations left for today."
            ))
        else:
            logger.error(f"Suno custom music generation failed for user {user_id}. Response: {response}")
            loop.run_until_complete(bot.send_message(
                chat_id=chat_id,
                text="Failed to generate custom music. Please try again later."
            ))
        
        end_time = time.time()
        record_response_time(end_time - start_time)
        logger.info(f"Custom music generated in {end_time - start_time:.2f} seconds for user {user_id}")
    
    except Exception as e:
        logger.error(f"Custom music generation error for user {user_id}: {str(e)}")
        record_error("suno_custom_music_generation_error")
        send_error_message.send(chat_id, str(e))