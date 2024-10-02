# Remove individual imports and use module-level imports instead
from . import user_handlers
from . import model_handlers
from . import voice_handlers
from . import image_handlers
from . import video_handlers
from . import admin_handlers
from . import flux_handlers
from . import message_handlers
from . import leonardo_handlers
from . import gpt_handlers
from . import suno_handlers
from . import replicate_handlers

# Export all the handlers
__all__ = [
    'user_handlers',
    'model_handlers',
    'voice_handlers',
    'image_handlers',
    'video_handlers',
    'admin_handlers',
    'flux_handlers',
    'message_handlers',
    'leonardo_handlers',
    'gpt_handlers',
    'suno_handlers',
    'replicate_handlers'
]