import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend
import os

# Configure Redis broker
redis_broker = RedisBroker(host="localhost", port=6379)

# Configure Results middleware
result_backend = RedisBackend(host="localhost", port=6379)
redis_broker.add_middleware(Results(backend=result_backend))

# Set broker as the global broker
dramatiq.set_broker(redis_broker)

# Import all tasks and add debug print to confirm loading
from .image_tasks import *
from .suno_tasks import *
from .flux_tasks import *
from .voice_tasks import *