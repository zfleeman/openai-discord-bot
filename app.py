import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.request import urlopen

import discord
from discord import Embed, FFmpegOpusAudio, Intents, Interaction
from discord.ext.commands import (
    BadArgument,
    BadLiteralArgument,
    CommandError,
    CommandNotFound,
    Context,
    MissingRequiredArgument,
)
from openai import AsyncOpenAI

from ai_helpers import (
    content_path,
    generate_speech,
    get_config,
    speak_and_spell,
)

# OpenAI Client
openai_client = AsyncOpenAI()

# Bot Client
intents = Intents.default()
intents.messages = True
intents.guilds = True

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)


@tree.command(name="help", description="Get help with a specific command")
async def help(
    interaction: Interaction, command: Literal["clean", "image", "join", "leave", "rather", "say", "talk", "vision"]
):

    folder = Path("docs")
    file = folder / f"{command}.md"
    help_text = file.read_text()

    embed = Embed(color=15844367, description=help_text)

    await interaction.response.send_message(embed=embed)


@tree.command(name="join", description="Join the voice channel that the user is in.")
async def join(interaction: Interaction):
    """
    joins the voice channel the command sender is in
    """

    if interaction.user.voice:
        _ = await interaction.user.voice.channel.connect()
        await interaction.response.send_message("I have joined the voice chat.", delete_after=5.0)
    else:
        await interaction.response.send_message(f"{interaction.user} is not in a voice channel.")


@tree.command(name="leave", description="Leave the voice channel that the user is in.")
async def leave(interaction: Interaction):
    """
    Leave a voice call
    """
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("I have left the voice chat.", delete_after=5.0)


@tree.command(name="clean", description="Delete everything shared by the bot in a given timeframe.")
async def clean(interaction: Interaction, number_of_minutes: int):
    """
    delete everything shared by the bot in the channel in which this is called
    :param number_of_minutes: amount of minutes to look back for deletion
    """
    config = get_config()

    max_clean_minutes = int(config.get("GENERAL", "max_clean_minutes", fallback=1440))
    if max_clean_minutes < number_of_minutes:
        await interaction.response.send_message(content=f"Can't clean more than {max_clean_minutes} minutes back.")
        return

    after_time = datetime.now() - timedelta(minutes=number_of_minutes)
    messages = interaction.channel.history(after=after_time)

    bot_id = bot.user.id
    sleep_seconds = float(config.get("GENERAL", "clean_sleep", fallback=0.75))

    async for message in messages:
        if message.author.id == bot_id:
            await asyncio.sleep(sleep_seconds)
            await message.delete()

    await interaction.response.send_message(content="All clean!", delete_after=5.0)


@tree.command(name="talk", description="Start a talk loop.")
async def talk(interaction: Interaction, topic: Literal["nonsense", "quotes"], minutes: float = 5.0):
    """
    Start a talk loop
    :param topic: the topic for discussion.
    :param time_interval: the time to wait before speaking random nonsense (minutes)
    """

    interval = minutes * 60

    config = get_config()
    prompt = config.get("PROMPTS", topic)

    if not discord.utils.get(bot.voice_clients, guild=interaction.guild):
        await interaction.response.send_message("I must be in a voice channel before you use this command.")
        return

    await interaction.response.send_message(content="Starting talk loop.", delete_after=10.0)

    while True:

        # check to see if a voice connection is still active
        if voice := discord.utils.get(bot.voice_clients, guild=interaction.guild):

            tts, file_path = await speak_and_spell(
                thread_name=topic,
                prompt=prompt,
                compartment="talk",
                guild_id=interaction.guild.id,
                openai_client=openai_client,
            )
            source = FFmpegOpusAudio(file_path)
            player = voice.play(source)

            # create our file object
            discord_file = discord.File(file_path, filename=file_path.name)

            await interaction.channel.send(tts, file=discord_file)
            await asyncio.sleep(interval)
        else:
            break


@tree.command(name="rather", description="Play a 'would you rather' game.")
async def rather(interaction: Interaction, topic: Literal["normal", "sexy", "games", "fitness"] = "normal"):
    """
    Play the 'would you rather' game
    :param topic: The assistant/game's name
    """

    topic = topic.lower()
    config = get_config()
    thread_name = f"rather_{topic}"
    new_hypothetical_prompt = config.get("PROMPTS", "new_hypothetical")

    await interaction.response.defer()

    tts, file_path = await speak_and_spell(
        thread_name=thread_name,
        prompt=new_hypothetical_prompt,
        guild_id=interaction.guild.id,
        compartment="rather",
        openai_client=openai_client,
    )

    # play over a voice channel
    if voice := discord.utils.get(bot.voice_clients, guild=interaction.guild):
        source = FFmpegOpusAudio(file_path)
        player = voice.play(source)

    # create our file object
    discord_file = discord.File(file_path, filename=file_path.name)

    await interaction.followup.send(content=tts, file=discord_file)


@tree.command(name="say", description="Have the bot say whatever somebody types.")
async def say(interaction: Interaction, text_to_speech: str):
    """
    say whatever somebody types
    :param text_to_speech: string of text to speak
    """

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{ts}.wav"
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    await interaction.response.defer()

    file_path = await generate_speech(
        guild_id=interaction.guild.id,
        compartment="say",
        file_name=file_name,
        tts=text_to_speech,
        openai_client=openai_client,
    )

    if voice:
        source = FFmpegOpusAudio(file_path)
        _ = voice.play(source)

    # create our file object
    discord_file = discord.File(file_path, filename=file_path.name)

    await interaction.followup.send(content=text_to_speech, file=discord_file)


@tree.command(name="image", description="Generate an image using prompts and a model.")
async def image(
    interaction: Interaction,
    image_prompt: str,
    image_model: Literal["dall-e-2", "dall-e-3", "dall-e-3-hd"] = "dall-e-3",
    num_images: int = 1,
):
    """
    Generate an image using prompts and a model
    :param image_prompt: The prompt used for image generation
    :param image_model: The model to use
    :param image_quality: Is this an HD image? Only works with dall-e-3.
    """

    image_quality = "standard"

    if image_model == "dall-e-3-hd":
        image_model, image_quality = "dall-e-3", "hd"

    if "dall-e-3" in image_model and num_images > 1:
        await interaction.response.send_message(f"For `dall-e-3` models, `[num_images]` has to be equal to 1.")
        return

    await interaction.response.defer()

    # create image and get relevant information
    images = await openai_client.images.generate(
        prompt=image_prompt, model=image_model, quality=image_quality, n=num_images
    )

    for i in range(len(images.data)):
        image = images.data[i]
        url = image.url
        revised_prompt = image.revised_prompt

        # create the output path
        file_name = f"image_{images.created}_{i+1}.png"
        path = content_path(guild_id=interaction.guild.id, compartment="image", file_name=file_name)

        # download the image from OpenAI
        with urlopen(url) as response:
            image_data = response.read()
            with open(path, "wb") as file:
                file.write(image_data)

        # create our embed object
        embed = Embed(
            title="Image Response",
            description=f"User Input:\n```{image_prompt}```",
        )
        embed.set_image(url=f"attachment://{file_name}")
        if revised_prompt:
            embed.set_footer(text=f"Revised Prompt:\n{revised_prompt}")

        # attach our file object
        file_upload = discord.File(path, filename=file_name)

        await interaction.channel.send(file=file_upload, embed=embed)
    await interaction.followup.send("I have generated the image(s). Enjoy?")


@tree.command(name="vision", description="Describe or interpret an image.")
async def vision(interaction: Interaction, file: discord.Attachment, vision_prompt: str = ""):
    """
    Describe/interpret an image
    :param vision_prompt: A prompt to be used when describing/interpreting the image
    """

    config = get_config()
    if not vision_prompt:
        vision_prompt = config.get("PROMPTS", "vision_prompt", fallback="What is in this image?")

    try:
        image_url = file.url
    except IndexError:
        await interaction.response.send_message(
            "```plaintext\nError: Unable to retrieve the image attachment. Did you attach an image?\n```"
        )
        return

    await interaction.response.defer()

    response = await openai_client.chat.completions.create(
        model=config.get("OPENAI_GENERAL", "vision_model", fallback="gpt-4o"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
    )
    await interaction.followup.send(response.choices[0].message.content)


@bot.event
async def on_command_error(ctx: Context, error: CommandError):
    """
    Bot event handler for a user command error.
    """

    if isinstance(error, CommandNotFound):
        # Not a command
        await ctx.message.reply("This is not a supported command.")
        await ctx.invoke(tree.get_command("help"))

    elif isinstance(error, MissingRequiredArgument):
        # Missing required argument
        await ctx.message.reply(f"Missing required argument: `<{error.param.name}>`")
        await ctx.invoke(tree.get_command("help"), ctx.command.name)

    elif isinstance(error, BadArgument):
        # Type error (gave int when expected string or the like)
        await ctx.message.reply(
            "Invalid argument type. Please provide the correct type (string, integer, float, ...) of arguments."
        )
        await ctx.invoke(tree.get_command("help"), ctx.command.name)

    elif isinstance(error, BadLiteralArgument):
        # A Literal was not satisfied
        await ctx.message.reply(
            f"The value you provided for `{error.param.name}` is not valid.\nThe allowed values are `{'`, `'.join(error.literals)}`."
        )
        await ctx.invoke(tree.get_command("help"), ctx.command.name)

    else:
        # Unknown error
        await ctx.send(f"An error occurred.\n```plaintext\n{error}\n```")


@bot.event
async def on_ready():
    await tree.sync()  # Sync slash commands globally
    print(f"Logged in as {bot.user}")


bot.run(os.getenv("DISCORD_BOT_KEY"))
