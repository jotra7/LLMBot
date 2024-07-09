# Anthropic-Powered Telegram Bot with Text-to-Speech

This project implements a Telegram bot powered by Anthropic's language models and Eleven Labs' text-to-speech technology. The bot can engage in conversations, answer questions, and convert text responses to speech.

## Features

- Interact with Anthropic's language models through Telegram
- Text-to-speech functionality using Eleven Labs API
- Dynamic model selection for Anthropic models
- Voice selection for text-to-speech responses
- Automatic caching and updating of available models and voices

## Prerequisites

- Python 3.7 or higher
- A Telegram Bot Token (obtainable from BotFather on Telegram)
- An Anthropic API key
- An Eleven Labs API key

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/anthropic-telegram-bot.git
   cd anthropic-telegram-bot
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root and add your API keys:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ANTHROPIC_API_KEY=your_anthropic_api_key
   ELEVENLABS_API_KEY=your_elevenlabs_api_key
   ```

## Usage

To start the bot, run:

```
python main.py
```

Once the bot is running, you can interact with it on Telegram using the following commands:

- `/start` - Start the bot and get a welcome message
- `/help` - Show available commands
- `/listmodels` - List available Anthropic models
- `/setmodel` - Set the Anthropic model to use
- `/currentmodel` - Show the currently selected model
- `/tts <text>` - Convert text to speech
- `/listvoices` - List available voices for text-to-speech
- `/setvoice` - Choose a voice for text-to-speech
- `/currentvoice` - Show the currently selected voice

## Project Structure

- `main.py`: The entry point of the application
- `bot.py`: Contains the main bot logic and command handlers
- `config.py`: Manages configuration and environment variables
- `model_cache.py`: Handles caching and retrieval of Anthropic models
- `voice_cache.py`: Manages caching and retrieval of Eleven Labs voices
- `requirements.txt`: Lists all Python dependencies

## Customization

You can customize the bot's behavior by modifying the `bot.py` file. Some areas you might want to customize include:

- The default model in `config.py`
- The text-to-speech parameters in the `generate_speech` function
- The periodic update intervals for model and voice caches

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Anthropic](https://www.anthropic.com/) for their powerful language models
- [Eleven Labs](https://elevenlabs.io/) for their text-to-speech API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for the Telegram bot framework