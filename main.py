import asyncio
from bot import create_application
from model_cache import update_model_cache

async def main():
    # Ensure the model cache is populated before starting the bot
    await update_model_cache()
    
    # Create the application (now synchronous)
    application = create_application()
    
    try:
        print("Starting bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        print("Bot is running. Press Ctrl+C to stop.")
        # Keep the bot running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Stopping bot...")
    finally:
        # Stop the bot gracefully
        await application.stop()
        await application.shutdown()
        print("Bot stopped.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()