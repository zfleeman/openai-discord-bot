# An OpenAI Discord Bot
No more, no less.

This repository contains the code and configurations for a Discord Bot created with the [`discord.py`](https://discordpy.readthedocs.io/en/stable/) package and the official [OpenAI Python API library](https://github.com/openai/openai-python).

## Commands

[`app.py`](app.py) contains the bot-decorated functions.

- **/join**: Join the voice channel that the user is currently in.
- **/leave**: Leave the voice channel that the bot is currently in.
- **/clean**: Delete messages sent by the bot within a specified timeframe.
- **/talk**: Start a loop where the bot talks about a specified topic at regular intervals.
- **/rather**: Play a "Would You Rather" game with a specified topic.
- **/say**: Make the bot say a specified text.
- **/image**: Generate an image using a prompt and a specified model.
- **/vision**: Describe or interpret an image using a prompt.
