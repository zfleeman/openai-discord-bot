"""
A simple Discord Bot that utilizes the OpenAI API.
"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.request import Request, urlopen

import discord
from discord import Embed, FFmpegOpusAudio, Intents, Interaction, app_commands
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

USER_AGENT = "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.3"


@tree.command(name="join", description="Join the voice channel that the user is currently in.")
async def join(interaction: Interaction) -> None:
    """
    Joins the voice channel that the command sender is currently in.
    """

    if interaction.user.voice:
        await interaction.user.voice.channel.connect()
        await interaction.response.send_message(content="I have joined the voice chat.", delete_after=3.0)
    else:
        await interaction.response.send_message(content=f"{interaction.user} is not in a voice channel.")

    return


@tree.command(name="leave", description="Leave the voice channel that the bot is currently in.")
async def leave(interaction: Interaction) -> None:
    """
    Leaves the voice channel that the bot is currently in.
    """
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message(content="I have left the voice chat.", delete_after=3.0)

    return


@tree.command(name="clean", description="Delete messages sent by the bot within a specified timeframe.")
@app_commands.describe(number_of_minutes="The number of minutes to look back for message deletion.")
async def clean(interaction: Interaction, number_of_minutes: int) -> None:
    """
    Deletes messages sent by the bot in the channel within a specified timeframe.

    Parameters:
    number_of_minutes (int): The number of minutes to look back for message deletion.
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

    await interaction.response.send_message(content="Deleting messages...", delete_after=5.0)

    async for message in messages:
        if message.author.id == bot_id:
            await asyncio.sleep(sleep_seconds)
            await message.delete()

    return


@tree.command(name="talk", description="Start a loop where the bot talks about a specified topic at regular intervals.")
@app_commands.describe(
    topic="The topic the bot will talk about.", minutes="The interval in minutes between each message."
)
async def talk(interaction: Interaction, topic: Literal["nonsense", "quotes"], minutes: float = 5.0) -> None:
    """
    Starts a loop where the bot talks about a specified topic at regular intervals.

    Parameters:
    topic (Literal): The topic for discussion.
    minutes (float): The interval in minutes between each message.
    """

    interval = minutes * 60

    config = get_config()
    prompt = config.get("PROMPTS", topic)

    if not discord.utils.get(bot.voice_clients, guild=interaction.guild):
        await interaction.response.send_message(content="I must be in a voice channel before you use this command.")
        return

    await interaction.response.send_message(content="Starting talk loop.", delete_after=3.0)

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
            _ = voice.play(source)

            # create our file object
            discord_file = discord.File(fp=file_path, filename=file_path.name)

            await interaction.channel.send(content=tts, file=discord_file)
            await asyncio.sleep(interval)
        else:
            break

    return


@tree.command(name="rather", description="Play a 'Would You Rather' game with a specified topic.")
@app_commands.describe(topic="The subject for the generated hypothetical question.")
async def rather(interaction: Interaction, topic: Literal["normal", "sexy", "games", "fitness"] = "normal") -> None:
    """
    Plays a 'Would You Rather' game with a specified topic.

    Parameters:
    topic (Literal): The subject for the generated hypothetical question.
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
        _ = voice.play(source)

    # create our file object
    discord_file = discord.File(file_path, filename=file_path.name)

    await interaction.followup.send(content=tts, file=discord_file)

    return


@tree.command(name="say", description="Make the bot say a specified text.")
@app_commands.describe(text_to_speech="The text you want the bot to say.")
async def say(interaction: Interaction, text_to_speech: str) -> None:
    """
    Makes the bot say a specified text.

    Parameters:
    text_to_speech (str): The text you want the bot to say.
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
    discord_file = discord.File(fp=file_path, filename=file_path.name)

    await interaction.followup.send(content=text_to_speech, file=discord_file)

    return


@tree.command(name="image", description="Generate an image using a prompt and a specified model.")
@app_commands.describe(
    image_prompt="The prompt used for image generation.", image_model="The OpenAI image model to use."
)
async def image(
    interaction: Interaction,
    image_prompt: str,
    image_model: Literal["dall-e-2", "dall-e-3", "dall-e-3-hd"] = "dall-e-3",
) -> None:
    """
    Generates an image using a prompt and a specified model.

    Parameters:
    image_prompt (str): The prompt used for image generation.
    image_model (Literal): The OpenAI image model to use.
    """

    image_quality = "standard"

    if image_model == "dall-e-3-hd":
        image_model, image_quality = "dall-e-3", "hd"

    await interaction.response.defer()

    # create image and get relevant information
    images = await openai_client.images.generate(prompt=image_prompt, model=image_model, quality=image_quality)

    image_object = images.data[0]
    url = image_object.url
    revised_prompt = image_object.revised_prompt

    # create the output path
    file_name = f"image_{images.created}.png"
    path = content_path(guild_id=interaction.guild.id, compartment="image", file_name=file_name)

    # download the image from OpenAI
    with urlopen(url) as response:
        image_data = response.read()
        with open(path, "wb") as file:
            file.write(image_data)

    # create our embed object
    embed = Embed(
        color=10181046,
        title="Image Response",
        description=f"User Input:\n```{image_prompt}```",
    )
    embed.set_image(url=f"attachment://{file_name}")
    if revised_prompt:
        embed.set_footer(text=f"Revised Prompt:\n{revised_prompt}")

    # attach our file object
    file_upload = discord.File(fp=path, filename=file_name)

    await interaction.followup.send(file=file_upload, embed=embed)

    return


@tree.command(name="vision", description="Describe or interpret an image using a prompt.")
@app_commands.describe(
    attachment="The image file you want to describe or interpret.",
    vision_prompt="The prompt to be used when describing the image.",
)
async def vision(interaction: Interaction, attachment: discord.Attachment, vision_prompt: str = "") -> None:
    """
    Describes or interprets an image using a prompt.

    Parameters:
    attachment (discord.Attachment): The image file you want to describe or interpret.
    vision_prompt (str): The prompt to be used when describing the image.
    """

    config = get_config()
    if not vision_prompt:
        vision_prompt = config.get("PROMPTS", "vision_prompt", fallback="What is in this image?")

    try:
        image_url = attachment.url
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

    embed = Embed(
        color=5763719,
        title="Vision Response",
        description=f"User Input:\n```{vision_prompt}```",
    )

    req = Request(
        url=attachment.url,
        headers={"User-Agent": USER_AGENT},
    )

    # Download the image from the URL
    with urlopen(req) as img_response:
        image_data = img_response.read()
        with open(attachment.filename, "wb") as file:
            file.write(image_data)

    discord_file = discord.File(fp=attachment.filename, filename=attachment.filename)

    embed.set_image(url=f"attachment://{attachment.filename}")
    embed.set_footer(text=response.choices[0].message.content)

    await interaction.followup.send(embed=embed, file=discord_file)

    Path(attachment.filename).unlink()

    return


@bot.event
async def on_ready():
    """
    Function to sync the command tree.
    """
    await tree.sync()  # Sync slash commands globally
    print(f"Logged in as {bot.user}")


bot.run(os.getenv("DISCORD_BOT_KEY"))
