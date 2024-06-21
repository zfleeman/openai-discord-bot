import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request
from typing import Union
from collections import Counter
from configparser import ConfigParser

import ffmpeg
import discord
from discord.ext.commands import Context, Bot
from discord import FFmpegOpusAudio, Embed, Intents
from openai import AsyncOpenAI
from PIL import Image

from db_utils import get_thread_id


# OpenAI Client
client = AsyncOpenAI()

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
    tts, path = await gs_intro_song(ctx.guild.id, arg1)
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
    tts, path = await would_you_rather(guild_id=ctx.guild.id, topic=arg1)
    source = FFmpegOpusAudio(path)
    player = voice.play(source)
    await ctx.send(tts)


@bot.command()
async def trivia(ctx: Context, arg1: int = 5, arg2: int = 30):
    """
    :param arg1: number of questions to ask
    :param arg2: seconds to wait before sharing the answer
    """

    config = get_config()
    trivia_sleep = int(config.get("GENERAL", "trivia_sleep", fallback=5))
    trivia_points = int(config.get("GENERAL", "trivia_points", fallback=10))
    trivia_penalty = int(config.get("GENERAL", "trivia_penalty", fallback=-10))

    # get our channel to find the message reactions later
    channel = ctx.channel

    scores = {}
    round = 0
    while round < arg1:
        response_dict = await get_trivia_question(guild_id=ctx.guild.id)

        question = response_dict.get("question")
        answer = response_dict.get("answer")
        multiplier = float(response_dict.get("multiplier", 1))

        # lazy text formatting
        question += "\n\n"

        # attach emoji to the question, and find the winning emoji for later use
        numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        answer_emoji = ""
        for number, choice in zip(numbers, response_dict["choices"]):
            question += f"{number} {choice}\n\n"

            if choice == answer:
                answer_emoji = number

        # if the AI did not follow the requestion JSON format/data
        if not answer_emoji:
            await ctx.send("The answer string could not be matched to any of the choices. This is a big problem.")
            return

        question_embed = Embed(title="Trivia Question", description=question, color=3447003)
        question_embed.set_footer(text=f"{multiplier}x score multiplier.")

        # send the question and attach the emojis as reactions
        message = await ctx.send(embed=question_embed)
        for number in numbers:
            await message.add_reaction(number)

        # wait between questions
        await asyncio.sleep(arg2)

        # begin working with the results
        message = await channel.fetch_message(message.id)
        reactions = message.reactions

        result_dict = {}
        entries = []
        for reaction in reactions:
            if reaction.emoji in numbers:
                result_dict[reaction.emoji] = {}
                correct_answer = reaction.emoji == answer_emoji
                users = [user.display_name async for user in reaction.users() if not user.bot]
                entries.extend(users)
                result_dict[reaction.emoji]["users"] = users
                result_dict[reaction.emoji]["is_answer"] = correct_answer

        # new users
        for entry in entries:
            if entry not in scores.keys():
                scores[entry] = 0

        # users with multiple votes
        counts = Counter(entries)
        duplicates = [string for string, count in counts.items() if count > 1]
        if duplicates:
            for duplicate in duplicates:
                scores[duplicate] -= trivia_penalty

        for value in result_dict.values():
            if value["is_answer"]:
                for user in value["users"]:
                    if user not in duplicates:
                        scores[user] += trivia_points * multiplier

        answer_embed = Embed(
            title="Trivia Answer",
            description=f"The correct answer is **{answer}**.",
            color=5763719,
        )
        if duplicates:
            answer_embed.set_footer(
                text=f"{', '.join(duplicates)} ➡️ Docked points because they voted on more than one answer."
            )

        not_last_round = (round + 1) != arg1

        if not_last_round:
            answer_embed.description += f"\n\nScores:\n{dict_to_ordered_string(scores)}"

        await ctx.send(embed=answer_embed)

        if not_last_round:
            await asyncio.sleep(trivia_sleep)
        else:
            await asyncio.sleep(2)
        round += 1

    # find our winner(s)
    winning_score = max(scores.values())
    winners = [key for key, value in scores.items() if value == winning_score]

    winner_embed = Embed(
        title="END OF TRIVIA GAME",
        description=f"Congratulations, **{', '.join(winners)}**. You won!\n\nResults:\n{dict_to_ordered_string(scores)}",
        color=16776960,
    )

    await ctx.send(embed=winner_embed)


@bot.command()
async def say(ctx: Context, *, arg: str = ""):
    """
    say whatever somebody types
    :param arg: string of text to speak
    """

    if not arg:
        await ctx.send("You need to type something after the command.")
        return
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{ts}.wav"
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    path = await generate_speech(guild_id=ctx.guild.id, compartment="say", file_name=file_name, tts=arg)
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
        arg2 = config.get("OPENAI_GENERAL", "image_model", fallback="dall-e-2")

    # create image and get relevant information
    image_response = await client.images.generate(prompt=arg1, model=arg2)
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
async def vision(ctx: Context, *, arg: str = ""):
    """
    Describe/interpret an image
    :param arg: A prompt to be used when describing/interpreting the image
    """

    config = get_config()
    if not arg:
        arg = config.get("PROMPTS", "vision_prompt", fallback="What is in this image?")

    image_url = ctx.message.attachments[0].url

    response = await client.chat.completions.create(
        model=config.get("OPENAI_GENERAL", "vision_model", fallback="gpt-4o"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": arg},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
    )
    await ctx.send(response.choices[0].message.content)


@bot.command()
async def edit(ctx: Context, *, arg: str = ""):
    """
    Edit an image using the original image and its mask
    :param arg: A prompt to be used when describing the desired image edit
    """

    config = get_config()
    images = [(ctx.message.attachments[0].url, "original"), (ctx.message.attachments[1].url, "mask")]

    ts = datetime.now().strftime("%Y%m%d%H%M%S")

    image_paths = []

    for image in images:
        req = Request(
            url=image[0],
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.3"
            },
        )
        # download the image from Discord
        with urlopen(req) as response:
            image_data = response.read()
            path = content_path(guild_id=ctx.guild.id, compartment="edit", file_name=f"{image[1]}_{ts}.png")
            image_paths.append(path)
            with open(path, "wb") as file:
                file.write(image_data)

        if not is_square_image(path):
            await ctx.send("Images used in OpenAI's Image Edit mode need to be square.")
            return

    image_response = await client.images.edit(
        model=config.get("OPENAI_GENERAL", "image_edit_model", fallback="dall-e-2"),
        image=open(image_paths[0], "rb"),
        mask=open(image_paths[1], "rb"),
        prompt=arg,
        n=int(config.get("OPENAI_GENERAL", "num_image_edits", fallback="1")),
        size=config.get("OPENAI_GENERAL", "image_edit_resolution", fallback="1024x1024"),
    )

    file_name = f"edit_{image_response.created}.png"
    path = content_path(guild_id=ctx.guild.id, compartment="edit", file_name=file_name)
    url = image_response.data[0].url

    # download the image from OpenAI
    with urlopen(url) as response:
        image_data = response.read()
        with open(path, "wb") as file:
            file.write(image_data)

    # create our embed object
    embed = Embed(
        title=config.get("DISCORD", "edit_embed_title", fallback="B4NG AI Edit Image Response"),
        description=f"User Input:\n```{arg}```",
    )
    embed.set_image(url=f"attachment://{file_name}")

    # attach our file object
    file_upload = discord.File(path, filename=file_name)

    await ctx.send(file=file_upload, embed=embed)


async def new_thread_response(
    thread_name: str, prompt: str = "", guild_id: str = "", response_format: Union[str, dict] = "auto"
):

    config = get_config()
    assistant_id = config.get("OPENAI_ASSISTANTS", thread_name)

    thread_id = await get_thread_id(guild_id=guild_id, name=thread_name, assistant_id=assistant_id, client=client)

    # add a message to the thread
    await client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt,
    )

    # run the thread with the assistant and monitor the situation
    run = await client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=assistant_id, response_format=response_format
    )

    messages = await client.beta.threads.messages.list(thread_id=thread_id)

    # get the most recent response from the assistant
    response = messages.data[0]

    return response


async def generate_speech(guild_id: str, compartment: str, file_name: str, tts: str) -> str:
    config = get_config()
    async with client.audio.speech.with_streaming_response.create(
        model=config.get("OPENAI_GENERAL", "speech_model", fallback="tts-1"),
        voice=config.get("OPENAI_GENERAL", "voice", fallback="onyx"),
        input=tts,
        response_format=config.get("OPENAI_GENERAL", "speech_file_format", fallback="wav"),
    ) as speech:
        file_path = content_path(guild_id=guild_id, compartment=compartment, file_name=file_name)
        await speech.stream_to_file(file_path)

    return file_path


async def gs_intro_song(guild_id: str, name: str):
    config = get_config()
    name = f"{name}_theme"

    prompt = config.get("PROMPTS", name)

    # openai api work
    ## generate the show intro text
    response = await new_thread_response(prompt=prompt, guild_id=guild_id, thread_name=name)

    ## generate a speech wav
    tts = response.content[0].text.value
    file_path = await generate_speech(
        guild_id=guild_id, compartment="theme", tts=tts, file_name=f"{name}_{response.id}.wav"
    )

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


async def would_you_rather(guild_id: str, topic: str):
    config = get_config()
    thread_name = f"rather_{topic}"

    new_hypothetical_prompt = config.get("PROMPTS", "new_hypothetical")

    response = await new_thread_response(thread_name=thread_name, prompt=new_hypothetical_prompt, guild_id=guild_id)
    tts = response.content[0].text.value
    file_path = await generate_speech(guild_id=guild_id, compartment="rather", tts=tts, file_name=f"{response.id}.wav")

    return tts, file_path


async def get_trivia_question(guild_id: str) -> dict:
    config = get_config()
    trivia_prompt = config.get("PROMPTS", "trivia_game")

    response = await new_thread_response(
        thread_name="trivia_game", prompt=trivia_prompt, guild_id=guild_id, response_format={"type": "json_object"}
    )

    text_json = response.content[0].text.value

    response_dict = json.loads(text_json)

    # may be something to do, here.

    return response_dict


def content_path(guild_id: str, compartment: str, file_name: str):
    config = get_config()
    ts = datetime.now().strftime(config.get("GENERAL", "session_strftime", fallback="dall-e-2"))
    dir_path = Path(f"generated_content/guild_{guild_id}/{ts}/{compartment}")
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / file_name


def is_square_image(image_path: Path):
    with Image.open(image_path) as img:
        width, height = img.size
        return width == height


def dict_to_ordered_string(data: dict) -> str:
    # Sort the dictionary items by value in descending order
    sorted_items = sorted(data.items(), key=lambda item: item[1], reverse=True)

    # Format the sorted items into a numbered list
    formatted_string = "\n".join([f"{i+1}. **{key}**: {value}" for i, (key, value) in enumerate(sorted_items)])

    return formatted_string


def get_config():
    config = ConfigParser()
    config.read("config.ini")
    return config


bot.run(os.getenv("DISCORD_BOT_KEY"))
