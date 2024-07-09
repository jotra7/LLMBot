import logging
import anthropic
from openai import OpenAI
from config import ANTHROPIC_API_KEY, OPENAI_API_KEY
from model_cache import update_model_cache
from voice_cache import update_voice_cache

logger = logging.getLogger(__name__)

# Initialize clients
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

async def periodic_cache_update(context):
    logger.info("Performing periodic model cache update")
    await update_model_cache()

async def periodic_voice_cache_update(context):
    logger.info("Performing periodic voice cache update")
    await update_voice_cache()