import os
import time
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen

import ffmpeg
import discord
from discord.ext.commands import Context, Bot
from discord import FFmpegOpusAudio, Embed, Intents
from openai import OpenAI
from openai.types.beta.assistant import Assistant

from db_utils import get_assistant_by_name, get_thread
from configuration import get_config


# OpenAI Client
client = OpenAI()

# Bot Client
intents = Intents.default()
intents.message_content = True
bot = Bot(command_prefix="!", intents=intents)


@bot.command()
async def ttsjoin(ctx: Context):
    if ctx.author.voice:
        voice = await ctx.author.voice.channel.connect()
    else:
        await ctx.send(f"{ctx.author} is not in a voice channel.")


@bot.command()
async def ttsleave(ctx: Context):
    if ctx.voice_client:
        await ctx.guild.voice_client.disconnect()


@bot.command()
async def theme(ctx: Context, arg1: str):
    """
    Creates an intro theme song for a game
    :param arg1: the game you want a theme song for
    """

    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    tts, path = gs_intro_song(ctx.guild.id, arg1)
    source = FFmpegOpusAudio(path)
    player = voice.play(source)
    await ctx.send(tts)


@bot.command()
async def rather(ctx: Context, arg1: str = "normal"):
    """
    Play the 'would you rather' game
    :param arg1: The assistant/game's name
    """

    arg1 = arg1.lower()
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    tts, path = would_you_rather(guild_id=ctx.guild.id, topic=arg1)
    source = FFmpegOpusAudio(path)
    player = voice.play(source)
    await ctx.send(tts)


@bot.command()
async def quiz(ctx: Context, arg1: str = ""):
    """
    Play the 'quiz question' game
    :param arg1: 'question' or 'answer'
    """

    arg1 = arg1.lower()
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    tts, path = quiz(guild_id=ctx.guild.id, qa=arg1)
    if not path:
        await ctx.send(tts)
    source = FFmpegOpusAudio(path)
    player = voice.play(source)
    await ctx.send(tts)


@bot.command()
async def say(ctx: Context, arg1: str = "", arg2: str = "onyx"):
    """
    say whatever somebody types
    :param arg1: string of quoted text to speak
    :param arg2: AI speaker to use
    """

    if not arg1:
        await ctx.send("You need to type something in quotes after the command.")
        return
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{ts}.wav"
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    path = generate_speech(guild_id=ctx.guild.id, compartment="say", file_name=file_name, tts=arg1, voice=arg2)
    source = FFmpegOpusAudio(path)
    player = voice.play(source)


@bot.command()
async def image(ctx: Context, arg1: str, arg2: str = ""):
    """
    Generate an image using prompts and a model
    :param arg1: The prompt used for image generation
    :param arg2: The model to use
    """

    config = get_config()

    if not arg2:
        arg2 = config.get("OPENAI", "image_model", fallback="dall-e-2")

    # create image and get relevant information
    image_response = client.images.generate(prompt=arg1, model=arg2)
    url = image_response.data[0].url
    revised_prompt = image_response.data[0].revised_prompt

    # create the output path
    file_name = f"image_{image_response.created}.png"
    path = content_path(guild_id=ctx.guild.id, compartment="image", file_name=file_name)

    # download the image from OpenAI
    with urlopen(url) as response:
        image_data = response.read()
        with open(path, "wb") as file:
            file.write(image_data)

    # create our embed object
    embed = Embed(
        title=config.get("DISCORD", "embed_title", fallback="B4NG AI Image Response"),
        description=f"User Input:\n```{arg1}```",
    )
    embed.set_image(url=f"attachment://{file_name}")
    if revised_prompt:
        embed.set_footer(text=f"Revised Prompt:\n{revised_prompt}")

    # attach our file object
    file_upload = discord.File(path, filename=file_name)

    await ctx.send(file=file_upload, embed=embed)


@bot.command()
async def vision(ctx: Context, arg1: str = ""):
    """
    Describe/interpret an image
    :param arg1: A prompt to be used when describing/interpreting the image
    """

    config = get_config()
    if not arg1:
        arg1 = config.get("PROMPTS", "vision_prompt", fallback="What is in this image?")

    image_url = ctx.message.attachments[0].url

    response = client.chat.completions.create(
        model=config.get("OPENAI", "vision_model", fallback="gpt-4o"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": arg1},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
    )
    await ctx.send(response.choices[0].message.content)


def new_response(assistant: Assistant, thread_name: str, prompt: str = "", guild_id: str = ""):

    thread = get_thread(guild_id=guild_id, name=thread_name, client=client, assistant_id=assistant.id)

    # add a message to the thread
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=prompt,
    )

    # run the thread with the assistant and monitor the situation
    run = client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant.id)

    while run.status != "completed":
        time.sleep(0.25)

    messages = client.beta.threads.messages.list(thread_id=thread.id)

    # the most recent message in the thread is from the assistant
    response = messages.data[0]

    return response


def content_path(guild_id: str, compartment: str, file_name: str):
    config = get_config()
    ts = datetime.now().strftime(config.get("GENERAL", "session_strftime", fallback="dall-e-2"))
    dir_path = Path(f"generated_content/guild_{guild_id}/{ts}/{compartment}")
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / file_name


def generate_speech(guild_id: str, compartment: str, file_name: str, tts: str, voice: str = "onyx") -> str:
    config = get_config()
    with client.audio.speech.with_streaming_response.create(
        model=config.get("OPENAI", "speech_model", fallback="tts-1"),
        voice=voice,
        input=tts,
        response_format=config.get("OPENAI", "speech_file_format", fallback="wav"),
    ) as speech:
        file_path = content_path(guild_id=guild_id, compartment=compartment, file_name=file_name)
        speech.stream_to_file(file_path)

    return file_path


def gs_intro_song(guild_id: str, name: str):
    config = get_config()
    name = f"{name}_theme"
    assistant = get_assistant_by_name(guild_id=guild_id, name="gs_host", client=client)

    # check if this is a new assistant
    if not assistant.instructions:
        assistant_instructions = config.get("PROMPTS", "gs_host")
        assistant = client.beta.assistants.update(
            assistant_id=assistant.id, instructions=assistant_instructions, name="gs_host"
        )

    prompt = config.get("PROMPTS", name)

    # openai api work
    ## generate the show intro text
    response = new_response(assistant=assistant, prompt=prompt, guild_id=guild_id, thread_name=name)

    ## generate a speech wav
    tts = response.content[0].text.value
    file_path = generate_speech(guild_id=guild_id, compartment="theme", tts=tts, file_name=f"{name}_{response.id}.wav")

    # ffmpeg work to combine streams
    ## load both audio files
    theme_song = ffmpeg.input("gameshow.mp3").audio
    words = ffmpeg.input(file_path).audio

    ## adjust volumes
    theme_song = theme_song.filter("volume", 0.25)
    words = words.filter("volume", 3)

    ## merge and output
    dt_string = datetime.now().strftime("%Y%m%d%H%M%S")
    ouput_file = Path(f"intro_{dt_string}.wav").resolve()
    merged_audio = ffmpeg.filter((theme_song, words), "amix")
    out = ffmpeg.output(merged_audio, str(ouput_file)).overwrite_output()
    out.run(quiet=True)

    return tts, ouput_file


def would_you_rather(guild_id: str, topic: str):
    config = get_config()
    assistant_name = f"rather_{topic}"
    assistant = get_assistant_by_name(guild_id=guild_id, name=assistant_name, client=client)

    # check if this is a new assistant
    if not assistant.instructions:
        prompt = config.get("PROMPTS", assistant_name)
        assistant_instructions = prompt
        assistant = client.beta.assistants.update(
            assistant_id=assistant.id, instructions=assistant_instructions, name=assistant_name
        )

    new_hypothetical_prompt = config.get("PROMPTS", "new_hypothetical")

    response = new_response(
        assistant=assistant, thread_name=assistant_name, prompt=new_hypothetical_prompt, guild_id=guild_id
    )
    tts = response.content[0].text.value
    file_path = generate_speech(guild_id=guild_id, compartment="rather", tts=tts, file_name=f"{response.id}.wav")

    return tts, file_path


def quiz(guild_id: str, qa: str = ""):
    config = get_config()
    assistant_name = f"quiz_{qa}"

    if qa == "question":
        assistant = get_assistant_by_name(guild_id=guild_id, name=assistant_name, client=client)
        assistant_instructions = config.get("PROMPTS", assistant_name)
        prompt = "Ask me a new question."
    elif qa == "answer":
        assistant = get_assistant_by_name(guild_id=guild_id, name=assistant_name, client=client)
        assistant_instructions = config.get("PROMPTS", assistant_name)
        prompt = "Answer the question that was just asked with one word or phrase. "
    else:
        return "That is not a valid input.", False

    # check if this is a new assistant
    if not assistant.instructions:
        assistant = client.beta.assistants.update(
            assistant_id=assistant.id, instructions=assistant_instructions, name=assistant_name
        )

    response = new_response(assistant=assistant, thread_name="quiz", prompt=prompt, guild_id=guild_id)
    tts = response.content[0].text.value
    file_path = generate_speech(guild_id=guild_id, compartment="quiz", tts=tts, file_name=f"{qa}_{response.id}.wav")

    return tts, file_path


bot.run(os.getenv("DISCORD_BOT_KEY"))
