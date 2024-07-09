import anthropic
from datetime import datetime, timedelta
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

model_cache = {}
last_cache_update = None

async def update_model_cache():
    global model_cache, last_cache_update
    try:
        # Updated list of models based on the provided information
        model_cache = {
            "claude-3-5-sonnet-20240620": "Claude 3.5 Sonnet",
            "claude-3-opus-20240229": "Claude 3 Opus",
            "claude-3-sonnet-20240229": "Claude 3 Sonnet",
            "claude-3-haiku-20240307": "Claude 3 Haiku"
        }
        last_cache_update = datetime.now()
    except Exception as e:
        print(f"Error updating model cache: {str(e)}")

async def get_models():
    global last_cache_update
    if not last_cache_update or (datetime.now() - last_cache_update) > timedelta(days=1):
        await update_model_cache()
    return model_cache

async def periodic_cache_update(context):
    await update_model_cache()