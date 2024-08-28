# Multi-Functional Telegram Bot

This project implements a feature-rich Telegram bot powered by Anthropic's language models, OpenAI's image generation and analysis capabilities, Eleven Labs' text-to-speech technology, and Fal.ai's image and video generation. The bot can engage in conversations, answer questions, generate and analyze images, convert text to speech, create short video clips, and generate realistic images.

## Features

- Chat functionality using Anthropic's language models
- Customizable system message for AI behavior (per user)
- Image generation using OpenAI's DALL-E 3
- Realistic image generation using Fal.ai's Flux models
- Image analysis using OpenAI's GPT-4 Vision
- Text-to-speech functionality using Eleven Labs API
- Video generation using Fal.ai's fast-animatediff model
- Dynamic model selection for Anthropic models
- Voice selection for text-to-speech responses
- Conversation history tracking
- Automatic caching and updating of available models and voices
- Performance tracking and metrics
- Admin commands for bot management and monitoring
- Concurrent task processing with separate queues for long-running and quick tasks

## Prerequisites

- Python 3.7 or higher
- A Telegram Bot Token (obtainable from BotFather on Telegram)
- An Anthropic API key
- An OpenAI API key
- An Eleven Labs API key
- A Fal.ai API key

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/multi-functional-telegram-bot.git
   cd multi-functional-telegram-bot
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root and add your API keys:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ANTHROPIC_API_KEY=your_anthropic_api_key
   OPENAI_API_KEY=your_openai_api_key
   ELEVENLABS_API_KEY=your_elevenlabs_api_key
   FAL_KEY=your_fal_ai_api_key
   ```

## Usage

To start the bot, run:

```
python main.py
```

Once the bot is running, you can interact with it on Telegram using the following commands:

### User Commands

- `/start` - Start the bot and get a welcome message
- `/help` - Show available commands
- `/listmodels` - List available Anthropic models
- `/setmodel` - Set the Anthropic model to use
- `/currentmodel` - Show the currently selected model
- `/tts <text>` - Convert specific text to speech
- `/video <prompt>` - Generate a short video clip based on a text prompt
- `/flux <prompt>` - Generate a realistic image using Fal.ai's Flux model
- `/list_flux_models` - List available Flux AI models
- `/set_flux_model <model_name>` - Set the Flux AI model to use
- `/current_flux_model` - Show the currently selected Flux AI model
- `/listvoices` - List available voices for text-to-speech
- `/setvoice` - Choose a voice for text-to-speech
- `/currentvoice` - Show the currently selected voice
- `/history` - Show your recent conversations
- `/generate_image <prompt>` - Generate an image based on a text prompt using DALL-E 3
- `/analyze_image` - Analyze an image (send this command as a caption with an image)
- `/set_system_message <message>` - Set a custom system message for the AI (specific to your user)
- `/get_system_message` - Show your current system message
- `/queue_status` - Check the current status of task queues

### Admin Commands

- `/admin_broadcast <message>` - Send a message to all users
- `/admin_user_stats` - View user statistics
- `/admin_ban <user_id>` - Ban a user
- `/admin_unban <user_id>` - Unban a user
- `/admin_set_global_system <message>` - Set the global default system message
- `/admin_logs` - View recent logs
- `/admin_restart` - Restart the bot
- `/admin_update_models` - Update the model cache
- `/admin_performance` - View performance metrics

## Task Queue System

The bot uses a sophisticated task queue system that allows for concurrent processing of different types of tasks:

- Long-running tasks (e.g., video generation, Flux image generation) are processed in a separate queue from quick tasks (e.g., regular message handling).
- This allows the bot to remain responsive to user messages even while processing resource-intensive tasks.
- The queue system is implemented in `queue_system.py` and integrated throughout the bot's functionality.

## Performance Tracking

The bot includes a comprehensive performance tracking system that monitors:

- Response times
- Model usage
- Command usage
- Errors

Performance data is stored in-memory for quick access and periodically saved to an SQLite database for long-term storage and analysis. Admins can view performance metrics using the `/admin_performance` command.

## Project Structure

- `main.py`: The entry point of the application
- `bot.py`: Contains the main bot logic and command handlers
- `config.py`: Manages configuration and environment variables
- `handlers.py`: Implements command and message handlers
- `database.py`: Handles conversation history storage and retrieval, user management
- `performance_metrics.py`: Manages performance tracking and metrics
- `model_cache.py`: Handles caching and retrieval of Anthropic models
- `voice_cache.py`: Manages caching and retrieval of Eleven Labs voices
- `image_processing.py`: Handles image generation and analysis
- `tts.py`: Manages text-to-speech functionality
- `utils.py`: Contains utility functions and periodic tasks
- `queue_system.py`: Implements the concurrent task queue system
- `requirements.txt`: Lists all Python dependencies

## System Messages

The bot allows each user to set their own system message, which influences how the AI responds to their queries. The system message is stored per user and persists across conversations until changed.

## Customization

You can customize the bot's behavior by modifying the following:

- The default model in `config.py`
- The default system message in `config.py`
- The text-to-speech parameters in the `generate_speech` function
- The video generation parameters in the `generate_text_to_video` function
- The Flux image generation parameters in the `flux_command` function
- The periodic update intervals for model and voice caches
- The performance data save interval in `bot.py`
- The number of conversations to retrieve in the history command

## Running as a Service on Ubuntu

To run the bot as a background service on Ubuntu, follow these steps:

1. Ensure your .env file is in place and properly configured:

   ```bash
   nano /path/to/your/bot/.env
   ```

   Make sure it contains all necessary API keys and configurations:

   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ANTHROPIC_API_KEY=your_anthropic_api_key
   OPENAI_API_KEY=your_openai_api_key
   ELEVENLABS_API_KEY=your_elevenlabs_api_key
   FAL_KEY=your_fal_ai_api_key
   ```

2. Create a service file:

   ```bash
   sudo nano /etc/systemd/system/telegram-bot.service
   ```

3. Add the following content to the file (adjust paths as necessary):

   ```ini
   [Unit]
   Description=Telegram Bot Service
   After=network.target

   [Service]
   ExecStart=/path/to/your/venv/bin/python /path/to/your/bot/main.py
   WorkingDirectory=/path/to/your/bot
   StandardOutput=inherit
   StandardError=inherit
   Restart=always
   User=your_username
   Environment="PATH=/path/to/your/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
   EnvironmentFile=/path/to/your/bot/.env

   [Install]
   WantedBy=multi-user.target
   ```

   Make sure to replace:
   - `/path/to/your/venv/bin/python` with the actual path to the Python executable in your virtual environment
   - `/path/to/your/bot/main.py` with the actual path to your `main.py` file
   - `/path/to/your/bot` with the actual path to your bot's directory
   - `your_username` with the username under which the bot should run
   - `/path/to/your/venv/bin` in the PATH with the actual path to your virtual environment's bin directory
   - `/path/to/your/bot/.env` with the actual path to your .env file

4. Save the file and exit the editor (in nano, press `Ctrl+X`, then `Y`, then `Enter`).

5. Set the correct permissions for the .env file:

   ```bash
   sudo chown root:root /path/to/your/bot/.env
   sudo chmod 600 /path/to/your/bot/.env
   ```

   This ensures that only the root user can read the .env file, which contains sensitive information.

6. Reload the systemd manager to recognize the new service:

   ```bash
   sudo systemctl daemon-reload
   ```

7. Start the service:

   ```bash
   sudo systemctl start telegram-bot
   ```

8. Enable the service to start automatically on boot:

   ```bash
   sudo systemctl enable telegram-bot
   ```

9. Check the status of the service:

   ```bash
   sudo systemctl status telegram-bot
   ```

   This should show that the service is active and running.

### Additional Service Management Commands

- To stop the service:

  ```bash
  sudo systemctl stop telegram-bot
  ```

- To restart the service:

  ```bash
  sudo systemctl restart telegram-bot
  ```

- To view the service logs:

  ```bash
  sudo journalctl -u telegram-bot
  ```

  Add `-f` to follow the logs in real-time:

  ```bash
  sudo journalctl -u telegram-bot -f
  ```

By setting up your Telegram bot as a service with proper .env file handling, it will run continuously in the background, automatically restart if the system reboots or if the bot crashes, and have access to all necessary environment variables and API keys.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Anthropic for their powerful language models
- OpenAI for their image generation and analysis capabilities
- Eleven Labs for their text-to-speech API
- Fal.ai for their image and video generation capabilities
- python-telegram-bot for the Telegram bot framework

