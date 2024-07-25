# Multi-Functional Telegram Bot

This project implements a feature-rich Telegram bot powered by Anthropic's language models, OpenAI's image generation and analysis capabilities, and Eleven Labs' text-to-speech technology. The bot can engage in conversations, answer questions, generate and analyze images, and convert text responses to speech.

## Features

- Chat functionality using Anthropic's language models
- Customizable system message for AI behavior (per user)
- Image generation using OpenAI's DALL-E 3
- Image analysis using OpenAI's GPT-4 Vision
- Text-to-speech functionality using Eleven Labs API
- Dynamic model selection for Anthropic models
- Voice selection for text-to-speech responses
- Conversation history tracking
- Automatic caching and updating of available models and voices
- Performance tracking and metrics
- Admin commands for bot management and monitoring

## Prerequisites

- Python 3.7 or higher
- A Telegram Bot Token (obtainable from BotFather on Telegram)
- An Anthropic API key
- An OpenAI API key
- An Eleven Labs API key

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
- `/listvoices` - List available voices for text-to-speech
- `/setvoice` - Choose a voice for text-to-speech
- `/currentvoice` - Show the currently selected voice
- `/history` - Show your recent conversations
- `/generate_image <prompt>` - Generate an image based on a text prompt
- `/analyze_image` - Analyze an image (send this command as a caption with an image)
- `/set_system_message <message>` - Set a custom system message for the AI (specific to your user)
- `/get_system_message` - Show your current system message

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

## Performance Tracking

The bot now includes a comprehensive performance tracking system that monitors:
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
- `requirements.txt`: Lists all Python dependencies

## System Messages
The bot allows each user to set their own system message, which influences how the AI responds to their queries. Here's how it works:

Each user can set their own custom system message using the /set_system_message command.
If a user hasn't set a custom message, the bot uses the default system message defined in config.py.
The system message is stored per user and persists across conversations until changed.
Users can view their current system message with the /get_system_message command.

## Customization

You can customize the bot's behavior by modifying the following:

- The default model in `config.py`
- The default system message in `config.py`
- The text-to-speech parameters in the `generate_speech` function
- The periodic update intervals for model and voice caches
- The performance data save interval in `bot.py`
- The number of conversations to retrieve in the history command

## Running as a Service on Ubuntu

To run the bot as a background service on Ubuntu, follow the instructions in the original README.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Anthropic](https://www.anthropic.com/) for their powerful language models
- [OpenAI](https://openai.com/) for their image generation and analysis capabilities
- [Eleven Labs](https://elevenlabs.io/) for their text-to-speech API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for the Telegram bot framework

