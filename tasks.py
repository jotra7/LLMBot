from celery import Celery
import config
import logging
import fal_client
import requests
from database import save_user_generation
import time
import asyncio
app = Celery('tasks', broker=config.CELERY_BROKER_URL, backend=config.CELERY_RESULT_BACKEND)
logger = logging.getLogger(__name__)

@app.task(bind=True, max_retries=3)
def generate_video_task(self, user_id, prompt):
    try:
        logger.info(f"Generating video for prompt: {prompt}")

        # Step 1: Submit the video generation request
        handler = fal_client.submit(
            "fal-ai/fast-animatediff/text-to-video",
            arguments={
                "prompt": prompt,
                "num_frames": 32,
                "num_inference_steps": 25,
                "guidance_scale": 7.5,
                "fps": 8,
                "video_size": "square"
            }
        )
        
        # Step 2: Debugging: Inspect the handler to understand its attributes
        logger.info(f"Handler type: {type(handler)}")
        logger.info(f"Handler attributes: {dir(handler)}")
        logger.info(f"Handler contents: {handler}")

        # Step 3: Correctly handle the response
        # If `handler` is an object, you will need to access its properties or methods.
        # Assuming it contains a `.result` method or similar to access the actual data:
        
        # Assuming `handler` has a property called 'result' or an equivalent way to access data
        if hasattr(handler, 'result'):
            # Direct attribute or method to get the data
            result = handler.result  # This may be a method call or property access based on your findings
        elif isinstance(handler, dict):
            result = handler  # If it's a dict, use it directly
        else:
            logger.error(f"Unexpected handler type. Could not retrieve the video data.")
            return {"status": "failed", "user_id": user_id, "prompt": prompt}
        
        # Step 4: Extract video URL and other details if it's a dictionary
        if isinstance(result, dict) and 'video' in result and 'url' in result['video']:
            video_url = result['video']['url']
            logger.info(f"Video generated successfully: {video_url}")
        else:
            logger.error(f"Video generation failed for prompt: {prompt}. No video URL found in the result.")
            return {"status": "failed", "user_id": user_id, "prompt": prompt}

        # Step 5: Download the video content
        video_content = requests.get(video_url).content

        logger.info(f"Video successfully downloaded for prompt: {prompt}")
        return {"status": "success", "user_id": user_id, "video_content": video_content, "prompt": prompt}

    except Exception as exc:
        logger.error(f"Error generating video for prompt '{prompt}': {exc}")
        self.retry(exc=exc, countdown=60)