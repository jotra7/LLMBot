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
# Check if the environment variables are set
if not TELEGRAM_BOT_TOKEN or not ANTHROPIC_API_KEY:
    raise ValueError("Please set the TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY environment variables.")

# Default model updated to the latest available Claude model
DEFAULT_MODEL = "claude-3-5-sonnet-20240620"

DEFAULT_SYSTEM_MESSAGE = "You are a rude, foul mouthed, but ultimately helpful assistant."
ADMIN_USER_IDS = [77446618] 
FLUX_MODELS = {
    "flux-realism": "fal-ai/flux-realism",
    "flux-pro": "fal-ai/flux-pro",
    "Stable Diffusion V3":"fal-ai/stable-diffusion-v3-medium"
}
DEFAULT_FLUX_MODEL = "flux-realism"