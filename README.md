# Multi-Functional Telegram Bot

This project implements a feature-rich Telegram bot powered by Anthropic's language models, OpenAI's image generation and analysis capabilities, Eleven Labs' text-to-speech technology, and Fal.ai's image and video generation. The bot can engage in conversations, answer questions, generate and analyze images, convert text to speech, create short video clips, and generate realistic images.

## Features

- Chat functionality using Anthropic's Claude 3.5 Sonnet model
- Customizable system message for AI behavior (per user)
- Image generation using OpenAI's DALL-E 3
- Realistic image generation using Fal.ai's Flux models
- Image analysis using OpenAI's GPT-4 Vision
- Text-to-speech functionality using Eleven Labs API
- Video generation using Fal.ai's fast-animatediff model
- Dynamic model selection for Anthropic models
- Voice selection for text-to-speech responses
- Custom voice upload
- Conversation history tracking
- Automatic caching and updating of available models and voices
- Performance tracking and metrics
- Admin commands for bot management and monitoring
- Concurrent task processing with separate queues for long-running and quick tasks
- Leonardo.ai integration for additional image generation capabilities
- Image-to-video conversion

## Prerequisites

- Python 3.7 or higher
- PostgreSQL database
- A Telegram Bot Token (obtainable from BotFather on Telegram)
- An Anthropic API key
- An OpenAI API key
- An Eleven Labs API key
- A Fal.ai API key
- A Leonardo.ai API key

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

3. Create a `.env` file in the project root and add your API keys and database configuration:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ANTHROPIC_API_KEY=your_anthropic_api_key
   OPENAI_API_KEY=your_openai_api_key
   ELEVENLABS_API_KEY=your_elevenlabs_api_key
   FAL_KEY=your_fal_ai_api_key
   LEONARDO_AI_KEY=your_leonardo_ai_key
   POSTGRES_DB=your_database_name
   POSTGRES_USER=your_database_user
   POSTGRES_PASSWORD=your_database_password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   ```

## Database Setup

1. Ensure PostgreSQL is installed and running on your system.

2. Create a PostgreSQL superuser if you haven't already:
   ```
   sudo -u postgres createuser --superuser your_superuser_name
   ```

3. Set a password for the superuser:
   ```
   sudo -u postgres psql
   ALTER USER your_superuser_name WITH PASSWORD 'your_secure_password';
   \q
   ```

4. Update the `POSTGRES_PASSWORD` in your `.env` file with the superuser password.

5. Run the database initialization script:
   ```
   python initdb.py
   ```

   This script will create the database, user, and necessary tables for the application.

## Usage

To start the bot, run:

```
python main.py
```

Once the bot is running, you can interact with it on Telegram using the following commands:

[List of commands remains the same as in the original README]

## Project Structure

- `main.py`: The entry point of the application
- `bot.py`: Contains the main bot logic and command handlers
- `config.py`: Manages configuration and environment variables
- `handlers/`: Directory containing various command and functionality handlers
- `database.py`: Handles conversation history storage and retrieval, user management
- `performance_metrics.py`: Manages performance tracking and metrics
- `model_cache.py`: Handles caching and retrieval of Anthropic models
- `voice_cache.py`: Manages caching and retrieval of Eleven Labs voices
- `image_processing.py`: Handles image generation and analysis
- `utils.py`: Contains utility functions and periodic tasks
- `queue_system.py`: Implements the concurrent task queue system
- `initdb.py`: Database initialization script

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
- `/set_flux_model` - Set the Flux AI model to use
- `/current_flux_model` - Show the currently selected Flux AI model
- `/listvoices` - List available voices for text-to-speech
- `/setvoice` - Choose a voice for text-to-speech
- `/currentvoice` - Show the currently selected voice
- `/add_voice` - Add a custom voice for text-to-speech (one per user)
- `/delete_custom_voice` - Delete your custom voice
- `/history` - Show your recent conversations
- `/generate_image <prompt>` - Generate an image based on a text prompt using DALL-E 3
- `/analyze_image` - Analyze an image (send this command as a caption with an image)
- `/set_system_message <message>` - Set a custom system message for the AI (specific to your user)
- `/get_system_message` - Show your current system message
- `/queue_status` - Check the current status of task queues
- `/leo <prompt>` - Generate an image using Leonardo.ai
- `/list_leonardo_models` - List available Leonardo.ai models
- `/set_leonardo_model` - Set the Leonardo.ai model to use
- `/current_leonardo_model` - Show the currently selected Leonardo.ai model
- `/unzoom` - Unzoom a Leonardo.ai generated image
- `/img2video` - Convert an image to a short video clip
- `/gpt <message>` - Send a message to the current GPT model
- `/list_gpt_models` - View all available GPT models
- `/set_gpt_model` - Choose a specific GPT model to use
- `/current_gpt_model` - Check which GPT model is currently active
- `/delete_session` - Clear your current session data
- `/bug` - Report a bug or issue with the bot

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

## Project Structure

- `main.py`: The entry point of the application
- `bot.py`: Contains the main bot logic and command handlers
- `config.py`: Manages configuration and environment variables
- `handlers/`: Directory containing various command and functionality handlers
  - `__init__.py`: Initializes the handlers package
  - `user_handlers.py`: Handles user-related commands
  - `model_handlers.py`: Manages model-related commands
  - `voice_handlers.py`: Handles voice-related commands
  - `image_handlers.py`: Manages image generation and analysis commands
  - `video_handlers.py`: Handles video generation commands
  - `admin_handlers.py`: Manages admin-specific commands
  - `flux_handlers.py`: Handles Flux AI-related commands
  - `message_handlers.py`: Manages general message handling
  - `leonardo_handlers.py`: Handles Leonardo.ai image generation functionality
  - `gpt_handlers.py`: Manages GPT-related commands
- `database.py`: Handles conversation history storage and retrieval, user management
- `performance_metrics.py`: Manages performance tracking and metrics
- `model_cache.py`: Handles caching and retrieval of Anthropic models
- `voice_cache.py`: Manages caching and retrieval of Eleven Labs voices
- `image_processing.py`: Handles image generation and analysis
- `utils.py`: Contains utility functions and periodic tasks
- `queue_system.py`: Implements the concurrent task queue system
- `initdb.py`: Database initialization script

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Anthropic for their powerful language models
- OpenAI for their image generation and analysis capabilities
- Eleven Labs for their text-to-speech API
- Fal.ai for their image and video generation capabilities
- Leonardo.ai for additional image generation features
- python-telegram-bot for the Telegram bot framework

