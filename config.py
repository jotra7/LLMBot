import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API keys from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY") 
ELEVENLABS_SOUND_GENERATION_API_URL = "https://api.elevenlabs.io/v1/sound-generation"

# Database configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "your_db_name")
POSTGRES_USER = os.getenv("POSTGRES_USER", "your_username")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "your_password")

# Check if the environment variables are set
if not TELEGRAM_BOT_TOKEN or not ANTHROPIC_API_KEY:
    raise ValueError("Please set the TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY environment variables.")

# Default model updated to the latest available Claude model
DEFAULT_MODEL = "claude-3-5-sonnet-20240620"

DEFAULT_SYSTEM_MESSAGE = "You are a knowledgeable, efficient, and helpful AI assistant. Your goal is to provide accurate information and useful solutions to user queries. Be clear and concise in your responses, but also friendly and patient. Offer explanations when needed and ask for clarification if a query is unclear. Prioritize user safety and ethical considerations in your advice. If you don't know something, admit it honestly rather than guessing. Always strive to give the most relevant and practical assistance possible."
ADMIN_USER_IDS = [77446618, 345073552] 
GPT_VOICES = {
    "alloy": "Alloy - Neutral and balanced",
    "echo": "Echo - Mature and deep",
    "fable": "Fable - British and proper",
    "onyx": "Onyx - Authoritative and confident",
    "nova": "Nova - Warm and natural",
    "shimmer": "Shimmer - Clear and optimistic"
}

DEFAULT_GPT_VOICE = "shimmer"

GPT_VOICE_PREVIEWS = {
    "alloy": "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/alloy.wav",
    "echo": "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/echo.wav",
    "fable": "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/fable.wav",
    "onyx": "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/onyx.wav",
    "nova": "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/nova.wav",
    "shimmer": "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/shimmer.wav"
}
FLUX_MODELS = {
    "flux-realism": "fal-ai/flux-realism",
    "flux-pro": "fal-ai/flux-pro",
    "flux-pro-1.1": "fal-ai/flux-pro/v1.1",
    "Stable Diffusion V3":"fal-ai/stable-diffusion-v3-medium",
    "Stanle Diffusion Fast":"fal-ai/fast-sdxl"
}
DEFAULT_FLUX_MODEL = "flux-pro"
LEONARDO_AI_KEY = os.getenv("LEONARDO_AI_KEY")
LEONARDO_API_BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"
DEFAULT_LEONARDO_MODEL = "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3"  # Leonardo Creative
GENERATIONS_PER_DAY = int(os.getenv("GENERATIONS_PER_DAY"))
MAX_GENERATIONS_PER_DAY = int(os.getenv("GENERATIONS_PER_DAY"))
SUNO_BASE_URL = os.getenv("SUNO_BASE_URL")
MAX_FLUX_GENERATIONS_PER_DAY = int(os.getenv("MAX_FLUX_GENERATIONS_PER_DAY",20))
MAX_VIDEO_GENERATIONS_PER_DAY = int(os.getenv("MAX_VIDEO_GENERATIONS_PER_DAY",5))
MAX_I2V_GENERATIONS_PER_DAY = int(os.getenv("MAX_I2V_GENERATIONS_PER_DAY",5))
MAX_BRR_PER_DAY = int(os.getenv("MAX_BRR_PER_DAY",100))
MAX_REPLICATE_GENERATIONS_PER_DAY = int(os.getenv("MAX_REPLICATE_GENERATIONS_PER_DAY",20))
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")