import requests
from datetime import datetime, timedelta
from config import ELEVENLABS_API_KEY

voice_cache = {}
last_cache_update = None

async def update_voice_cache():
    global voice_cache, last_cache_update
    try:
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {
            "Accept": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        voices = response.json()["voices"]
        
        voice_cache = {voice["voice_id"]: voice["name"] for voice in voices}
        last_cache_update = datetime.now()
    except Exception as e:
        print(f"Error updating voice cache: {str(e)}")

async def get_voices():
    global last_cache_update
    if not last_cache_update or (datetime.now() - last_cache_update) > timedelta(days=1):
        await update_voice_cache()
    return voice_cache

async def periodic_voice_cache_update(context):
    await update_voice_cache()

def get_default_voice():
    # You can change this logic to select a different default voice if needed
    return next(iter(voice_cache.items()))[0] if voice_cache else None