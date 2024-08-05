# An OpenAI Discord Bot
No more, no less.

This repository contains the code and configurations for a Discord Bot created with the [`discord.py`](https://discordpy.readthedocs.io/en/stable/) package and the official [OpenAI Python API library](https://github.com/openai/openai-python).

## Commands

The Bot's commands are documented in the [docs](docs/) folder. [`app.py`](app.py) contains the bot-decorated functions.

## Run-it-Yourself!

While I currently do not have a desire to distribute this Bot to the public, you can run this yourself if you have a Discord Developer account and an OpenAI API key.

### Steps to Run

1. **Create a Bot**: Create a Discord Bot with the following permissions:
   <img width="500" src="https://github.com/user-attachments/assets/e41a42db-a035-4d6c-af33-77599ec4b2ea"/>

2. **Set Environment Variables**:
   ```sh
   OPENAI_API_KEY=your_openai_api_key
   DISCORD_BOT_TOKEN=your_discord_bot_token
   ```
3. **Run in Docker**: Use the provided [`Dockerfile`](Dockerfile) to build and run the Bot in a Docker container if that's your thing (it should be).
