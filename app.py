# pylint: disable=C0116
"""
A simple Discord Bot that utilizes the OpenAI API.
"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional
from urllib.request import Request, urlopen

import discord
from discord import Embed, FFmpegOpusAudio, Intents, Interaction, app_commands

from ai_helpers import content_path, generate_speech, get_config, get_openai_client, new_response, speak_and_spell
from db_utils import create_command_context

# Bot Client
intents = Intents.default()
intents.messages = True
intents.guilds = True

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

USER_AGENT = "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.3"


@tree.command(name="join", description="Join the voice channel that the user is currently in.")
async def join(interaction: Interaction) -> None:
    context = await create_command_context(interaction)

    if interaction.user.voice:
        await interaction.user.voice.channel.connect()
        await interaction.response.send_message(content="I have joined the voice chat.", delete_after=3.0)
    else:
        await interaction.response.send_message(content=f"{interaction.user.name} is not in a voice channel.")

    return await context.save()


@tree.command(name="leave", description="Leave the voice channel that the bot is currently in.")
async def leave(interaction: Interaction) -> None:
    context = await create_command_context(interaction)

    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message(content="I have left the voice chat.", delete_after=3.0)

    return await context.save()


@tree.command(name="clean", description="Delete messages sent by the bot within a specified timeframe.")
@app_commands.describe(number_of_minutes="The number of minutes to look back for message deletion.")
async def clean(interaction: Interaction, number_of_minutes: int) -> None:
    context = await create_command_context(interaction, params={"number_of_minutes": number_of_minutes})
    config = get_config()

    max_clean_minutes = int(config.get("GENERAL", "max_clean_minutes", fallback=1440))
    if max_clean_minutes < number_of_minutes:
        await interaction.response.send_message(content=f"Can't clean more than {max_clean_minutes} minutes back.")
        return

    after_time = datetime.now() - timedelta(minutes=number_of_minutes)
    messages = interaction.channel.history(after=after_time)

    bot_id = bot.user.id
    sleep_seconds = float(config.get("GENERAL", "clean_sleep", fallback=0.75))

    await interaction.response.send_message(content="Deleting messages...")

    async for message in messages:
        if message.author.id == bot_id:
            await asyncio.sleep(sleep_seconds)
            await message.delete()

    return await context.save()


@tree.command(name="talk", description="Start a loop where the bot talks about a specified topic at regular intervals.")
@app_commands.describe(
    topic="The topic the bot will talk about.", wait_minutes="The interval in minutes between each message."
)
async def talk(interaction: Interaction, topic: Literal["nonsense", "quotes"], wait_minutes: float = 5.0) -> None:
    context = await create_command_context(interaction, params={"topic": f"talk_{topic}", "wait_minutes": wait_minutes})
    interval = wait_minutes * 60

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
                context=context,
                prompt=prompt,
            )
            source = FFmpegOpusAudio(file_path)
            _ = voice.play(source)

            # create our file object
            discord_file = discord.File(fp=file_path, filename=file_path.name)

            await interaction.channel.send(content=tts, file=discord_file)
            await asyncio.sleep(interval)
        else:
            break

    return await context.save()


@tree.command(name="rather", description="Play a 'Would You Rather' game with a specified topic.")
@app_commands.describe(topic="The subject for the generated hypothetical question.")
async def rather(interaction: Interaction, topic: Literal["normal", "adult", "games", "fitness"] = "normal") -> None:
    context = await create_command_context(interaction, params={"topic": f"rather_{topic}"})
    config = get_config()
    topic = f"rather_{topic}"
    new_hypothetical_prompt = config.get("PROMPTS", "new_hypothetical")

    await interaction.response.defer()

    tts, file_path = await speak_and_spell(
        context=context,
        prompt=new_hypothetical_prompt,
    )

    # play over a voice channel
    if voice := discord.utils.get(bot.voice_clients, guild=interaction.guild):
        source = FFmpegOpusAudio(file_path)
        _ = voice.play(source)

    # create our file object
    discord_file = discord.File(file_path, filename=file_path.name)

    await interaction.followup.send(content=tts, file=discord_file)

    return await context.save()


@tree.command(name="say", description="Make the bot say a specified text.")
@app_commands.describe(text_to_speech="The text you want the bot to say.", voice="The OpenAI voice model to use.")
async def say(
    interaction: Interaction,
    text_to_speech: str,
    voice: Literal["alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"] = "onyx",
) -> None:
    context = await create_command_context(interaction, params={"text_to_speech": text_to_speech, "voice": voice})
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{ts}.wav"
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild_id)

    await interaction.response.defer()

    file_path = await generate_speech(
        context=context,
        file_name=file_name,
        tts=text_to_speech,
        voice=voice,
    )

    if voice_client:
        source = FFmpegOpusAudio(file_path)
        _ = voice_client.play(source)

    # create our file object
    discord_file = discord.File(fp=file_path, filename=file_path.name)

    await interaction.followup.send(content=text_to_speech, file=discord_file)

    return await context.save()


@tree.command(name="image", description="Generate an image using a prompt and a specified model.")
@app_commands.describe(
    image_prompt="The prompt used for image generation.", image_model="The OpenAI image model to use."
)
async def image(
    interaction: Interaction,
    image_prompt: str,
    image_model: Literal["dall-e-2", "dall-e-3", "dall-e-3-hd"] = "dall-e-3",
) -> None:
    context = await create_command_context(interaction, params={"image_prompt": image_prompt, "model": image_model})
    image_quality = "standard"

    if image_model == "dall-e-3-hd":
        image_model, image_quality = "dall-e-3", "hd"

    await interaction.response.defer()

    openai_client = await get_openai_client(interaction.guild_id)

    # create image and get relevant information
    image_response = await openai_client.images.generate(prompt=image_prompt, model=image_model, quality=image_quality)

    image_object = image_response.data[0]

    # create the output path
    file_name = f"image_{image_response.created}.png"
    path = content_path(context=context, file_name=file_name)

    # download the image from OpenAI
    with urlopen(image_object.url) as response:
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
    if image_object.revised_prompt:
        embed.set_footer(text=f"Revised Prompt:\n{image_object.revised_prompt}")

    # attach our file object
    file_upload = discord.File(fp=path, filename=file_name)

    await interaction.followup.send(file=file_upload, embed=embed)

    return await context.save()


@tree.command(name="vision", description="Describe or interpret an image using a prompt.")
@app_commands.describe(
    attachment="The image file you want to describe or interpret.",
    vision_prompt="The prompt to be used when describing the image.",
)
async def vision(interaction: Interaction, attachment: discord.Attachment, vision_prompt: str = "") -> None:
    context = await create_command_context(
        interaction, params={"vision_prompt": vision_prompt, "attachment": attachment.filename}
    )
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

    openai_client = await get_openai_client(interaction.guild_id)

    response = await openai_client.responses.create(
        model=config.get("OPENAI_GENERAL", "vision_model", fallback="gpt-4o"),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": vision_prompt},
                    {"type": "input_image", "image_url": image_url},
                ],
            }
        ],
        max_output_tokens=config.getint("OPENAI_GENERAL", "max_output_tokens", fallback=500),
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
    embed.set_footer(text=response.output_text)

    await interaction.followup.send(embed=embed, file=discord_file)

    Path(attachment.filename).unlink()

    return await context.save()


@tree.command(name="chat", description="Have a conversation with an OpenAI Chat Model, like you would with ChatGPT.")
@app_commands.describe(
    input_text="The text of your question or statement that you wan the Chat Model to address.",
    keep_chatting="Continue the conversation from your last prompt.",
    model="The OpenAI Chat Model to use.",
    custom_instructions="Help the Chat Model respond to your prompt the way YOU want it to.",
)
async def chat(
    interaction: Interaction,
    input_text: str,
    keep_chatting: Literal["Yes", "No"] = "No",
    model: Literal["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4.5-preview", "gpt-4o"] = "gpt-4o-mini",
    custom_instructions: Optional[str] = None,
) -> None:

    if not custom_instructions:
        config = get_config()
        custom_instructions = config.get(
            "OPENAI_INSTRUCTIONS",
            "chat_helper",
            fallback="Ensure your response is under 2,000 characters and uses markdown compatible with Discord.",
        )

    context = await create_command_context(
        interaction,
        params={
            "input_text": input_text,
            "topic": str(interaction.user.id),
            "custom_instructions": custom_instructions,
            "keep_chatting": keep_chatting == "Yes",
            "model": model,
        },
    )

    await interaction.response.defer()

    response = await new_response(context=context, prompt=input_text, model=model)

    title = f"🤖 `{model}` Response{' (Continued)' if response.previous_response_id else ''}"

    embed = Embed(title=title, description=response.output_text)

    await interaction.followup.send(content=f"> {input_text}", embed=embed)

    return await context.save()


@bot.event
async def on_ready():

    await tree.sync()  # Sync slash commands globally
    print(f"Logged in as {bot.user}")


bot.run(os.getenv("DISCORD_BOT_KEY"))
