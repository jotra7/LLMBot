# Multi-Functional Telegram Bot

This project implements a feature-rich Telegram bot powered by Anthropic's language models, OpenAI's image generation and analysis capabilities, and Eleven Labs' text-to-speech technology. The bot can engage in conversations, answer questions, generate and analyze images, and convert text responses to speech.

## Features

- Chat functionality using Anthropic's language models
- Customizable system message for AI behavior
- Image generation using OpenAI's DALL-E 3
- Image analysis using OpenAI's GPT-4 Vision
- Text-to-speech functionality using Eleven Labs API
- Dynamic model selection for Anthropic models
- Voice selection for text-to-speech responses
- Conversation history tracking
- Automatic caching and updating of available models and voices

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
- `/set_system_message <message>` - Set a custom system message for the AI
- `/get_system_message` - Show the current system message

## Project Structure

- `main.py`: The entry point of the application
- `bot.py`: Contains the main bot logic and command handlers
- `config.py`: Manages configuration and environment variables
- `model_cache.py`: Handles caching and retrieval of Anthropic models
- `voice_cache.py`: Manages caching and retrieval of Eleven Labs voices
- `database.py`: Handles conversation history storage and retrieval
- `requirements.txt`: Lists all Python dependencies

## Customization

You can customize the bot's behavior by modifying the `bot.py` file. Some areas you might want to customize include:

- The default model in `config.py`
- The default system message in `config.py`
- The text-to-speech parameters in the `generate_speech` function
- The periodic update intervals for model and voice caches
- The number of conversations to retrieve in the history command

## System Messages
The bot allows each user to set their own system message, which influences how the AI responds to their queries. Here's how it works:

Each user can set their own custom system message using the /set_system_message command.
If a user hasn't set a custom message, the bot uses the default system message defined in config.py.
The system message is stored per user and persists across conversations until changed.
Users can view their current system message with the /get_system_message command.

This feature allows for personalized AI interactions, as each user can tailor the AI's behavior to their preferences or needs.

## Running as a Service on Ubuntu

To run the bot as a background service on Ubuntu:

1. Create a service file:
   ```
   sudo nano /etc/systemd/system/telegram-bot.service
   ```

2. Add the following content to the file, replacing the placeholders with your actual paths and username:
   ```ini
   [Unit]
   Description=Multi-Functional Telegram Bot Service
   After=network.target

   [Service]
   ExecStart=/usr/bin/python3 /path/to/your/main.py
   WorkingDirectory=/path/to/your/project
   User=yourusername
   Group=yourusergroup
   Restart=always
   RestartSec=10
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

3. Save the file and exit the text editor.

4. Reload the systemd manager:
   ```
   sudo systemctl daemon-reload
   ```

5. Start the service:
   ```
   sudo systemctl start telegram-bot
   ```

6. Enable the service to start on boot:
   ```
   sudo systemctl enable telegram-bot
   ```

7. Check the status of your service:
   ```
   sudo systemctl status telegram-bot
   ```

To view the bot's logs:
```
sudo journalctl -u telegram-bot
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Anthropic](https://www.anthropic.com/) for their powerful language models
- [OpenAI](https://openai.com/) for their image generation and analysis capabilities
- [Eleven Labs](https://elevenlabs.io/) for their text-to-speech API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for the Telegram bot framework
