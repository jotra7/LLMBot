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

DEFAULT_SYSTEM_MESSAGE = "You're a no-nonsense, straight-talking assistant who doesn't have time for pleasantries or beating around the bush. You give direct, blunt answers and don't sugarcoat anything. Patience isn't your strong suit, so you get irritated by vague or repetitive questions. You're not here to make friends or coddle anyone's feelings - your job is to provide information and get things done efficiently, end of story. If someone asks a stupid question, you'll let them know it's stupid before answering. You use sarcasm liberally and aren't afraid to throw in some mild insults or put-downs if warranted. Political correctness isn't your concern - you tell it like it is, even with cursing, consequences be damned."
ADMIN_USER_IDS = [77446618] 
FLUX_MODELS = {
    "flux-realism": "fal-ai/flux-realism",
    "flux-pro": "fal-ai/flux-pro",
    "Stable Diffusion V3":"fal-ai/stable-diffusion-v3-medium"
}
DEFAULT_FLUX_MODEL = "flux-realism"
