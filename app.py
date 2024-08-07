import asyncio
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from random import randint
from urllib.request import urlopen, Request

import discord
from discord.ext.commands import Context, Bot, CommandNotFound, MissingRequiredArgument, CommandError, BadArgument
from discord import FFmpegOpusAudio, Embed, Intents
from openai import AsyncOpenAI

from ai_helpers import (
    gs_intro_song,
    speak_and_spell,
    get_config,
    get_trivia_question,
    dict_to_ordered_string,
    generate_speech,
    content_path,
    is_square_image,
)


# OpenAI Client
openai_client = AsyncOpenAI()

# Bot Client
intents = Intents.default()
intents.message_content = True
bot = Bot(command_prefix="!", intents=intents, help_command=None)


@bot.command()
async def help(ctx: Context, command: str = ""):

    folder = Path("docs")
    files_without_suffix = [file.stem for file in folder.iterdir() if file.is_file()]

    if not command:
        await ctx.send(
            f"You can call `!help` on the following commands: `{'`, `'.join(files_without_suffix)}`\nFor example: `!help {files_without_suffix[0]}`"
        )
        return
    elif command not in files_without_suffix:
        await ctx.send(f"`!{command}` is not a recognized command. Get real.")
        return

    file = folder / f"{command}.md"
    help_text = file.read_text()

    embed = Embed(color=15844367, description=help_text)

    await ctx.send(embed=embed)


@bot.command()
async def join(ctx: Context):
    """
    joins the voice channel the command sender is in
    """

    if ctx.author.voice:
        voice = await ctx.author.voice.channel.connect()
    else:
        await ctx.send(f"{ctx.author} is not in a voice channel.")


@bot.command()
async def leave(ctx: Context):
    """
    Leave a voice call
    """
    if ctx.voice_client:
        await ctx.guild.voice_client.disconnect()


@bot.command()
async def clean(ctx: Context, number_of_minutes: int):
    """
    delete everything shared by the bot in the channel in which this is called
    :param number_of_minutes: amount of minutes to look back for deletion
    """
    config = get_config()

    after_time = datetime.now() - timedelta(minutes=number_of_minutes)
    messages = ctx.channel.history(after=after_time)

    bot_id = bot.user.id
    sleep_seconds = float(config.get("GENERAL", "clean_sleep", fallback=0.25))

    async for message in messages:
        if message.author.id == bot_id:
            await asyncio.sleep(sleep_seconds)
            await message.delete()


@bot.command()
async def talk(ctx: Context, topic: str = "nonsense", minutes: float = 5):
    """
    Start a talk loop
    :param topic: the topic for discussion. Options: "nonsense" or "quotes"
    :param time_interval: the time to wait before speaking random nonsense (minutes)
    """

    interval = minutes * 60

    config = get_config()
    prompt = config.get("PROMPTS", minutes)

    while True:

        if voice := discord.utils.get(bot.voice_clients, guild=ctx.guild):

            tts, file_path = await speak_and_spell(
                thread_name=topic,
                prompt=prompt,
                compartment="talk",
                guild_id=ctx.guild.id,
                openai_client=openai_client,
            )
            source = FFmpegOpusAudio(file_path)
            player = voice.play(source)

            await ctx.send(tts)
            await asyncio.sleep(interval)
        else:
            break


@bot.command()
async def theme(ctx: Context, game: str):
    """
    Creates an intro theme song for a game
    :param game: the game you want a theme song for
    """

    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    tts, file_path = await gs_intro_song(ctx.guild.id, game, openai_client=openai_client)
    source = FFmpegOpusAudio(file_path)
    player = voice.play(source)
    await ctx.send(tts)


@bot.command()
async def rather(ctx: Context, topic: str = "normal"):
    """
    Play the 'would you rather' game
    :param topic: The assistant/game's name
    """

    topic = topic.lower()
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice:
        await ctx.send("You must be in a voice channel when using this command.")
        return

    config = get_config()
    thread_name = f"rather_{topic}"

    new_hypothetical_prompt = config.get("PROMPTS", "new_hypothetical")

    tts, file_path = await speak_and_spell(
        thread_name=thread_name,
        prompt=new_hypothetical_prompt,
        guild_id=ctx.guild.id,
        compartment="rather",
        openai_client=openai_client,
    )
    source = FFmpegOpusAudio(file_path)
    player = voice.play(source)
    await ctx.send(tts)


@bot.command()
async def trivia(ctx: Context, number_of_questions: int = 5, answer_time: int = 30, start_delay: int = 0):
    """
    :param number_of_questions: number of questions to ask
    :param answer_time: seconds to wait before sharing the answer
    :param start_delay: seconds to wait before starting the trivia game. notifies channel if > 0
    """

    config = get_config()
    trivia_sleep = int(config.get("GENERAL", "trivia_sleep", fallback=5))
    trivia_points = int(config.get("GENERAL", "trivia_points", fallback=10))
    trivia_penalty = int(config.get("GENERAL", "trivia_penalty", fallback=-10))
    max_questions = int(config.get("GENERAL", "max_questions", fallback=20))
    max_time = int(config.get("GENERAL", "max_time", fallback=300))

    if number_of_questions > max_questions:
        await ctx.send(f"You can't have the bot ask more than **{max_questions}** questions.")
        return

    if (answer_time > max_time) or (start_delay > max_time):
        await ctx.send(f"You can't have the bot wait more than **{max_time}** seconds.")
        return

    # get our channel to find the message reactions later
    channel = ctx.channel

    notification_content = ""
    if start_delay:
        notification_content = f"@here A new Trivia game will start in {start_delay} seconds! Get ready!"

    # trivia start embed
    start_embed = Embed(
        title="Trivia Game Initiated",
        description=f"A new trivia game is starting.\n\n- **{number_of_questions} questions** will be asked\n- Players have **{answer_time} seconds** to pick an answer.",
        color=16776960,
    )

    await ctx.send(content=notification_content, embed=start_embed)
    await asyncio.sleep(start_delay)

    scores = {}
    round = 0
    while round < number_of_questions:
        response_dict = await get_trivia_question(guild_id=ctx.guild.id, openai_client=openai_client)

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

        question_embed = Embed(
            title=f"Trivia Question {round+1}/{number_of_questions}", description=question, color=3447003
        )
        question_embed.set_footer(text=f"{multiplier}x score multiplier.")

        # send the question and attach the emojis as reactions
        message = await ctx.send(embed=question_embed)
        for number in numbers:
            await message.add_reaction(number)

        # wait between questions
        await asyncio.sleep(answer_time)

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

        not_last_round = (round + 1) != number_of_questions

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
async def say(ctx: Context, *, text_to_speech: str):
    """
    say whatever somebody types
    :param text_to_speech: string of text to speak
    """

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{ts}.wav"
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    path = await generate_speech(
        guild_id=ctx.guild.id, compartment="say", file_name=file_name, tts=text_to_speech, openai_client=openai_client
    )
    source = FFmpegOpusAudio(path)
    player = voice.play(source)


@bot.command()
async def image(ctx: Context, image_prompt: str, image_model: str = ""):
    """
    Generate an image using prompts and a model
    :param image_prompt: The prompt used for image generation
    :param image_model: The model to use
    """

    config = get_config()

    if not image_model:
        image_model = config.get("OPENAI_GENERAL", "image_model", fallback="dall-e-2")

    # create image and get relevant information
    image_response = await openai_client.images.generate(prompt=image_prompt, model=image_model)
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
        description=f"User Input:\n```{image_prompt}```",
    )
    embed.set_image(url=f"attachment://{file_name}")
    if revised_prompt:
        embed.set_footer(text=f"Revised Prompt:\n{revised_prompt}")

    # attach our file object
    file_upload = discord.File(path, filename=file_name)

    await ctx.send(file=file_upload, embed=embed)


@bot.command()
async def vision(ctx: Context, *, vision_prompt: str = ""):
    """
    Describe/interpret an image
    :param vision_prompt: A prompt to be used when describing/interpreting the image
    """

    config = get_config()
    if not vision_prompt:
        vision_prompt = config.get("PROMPTS", "vision_prompt", fallback="What is in this image?")

    image_url = ctx.message.attachments[0].url

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
    await ctx.send(response.choices[0].message.content)


@bot.command()
async def edit(ctx: Context, *, edit_prompt: str):
    """
    Edit an image using the original image and its mask
    :param edit_prompt: A prompt to be used when describing the desired image edit
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

    image_response = await openai_client.images.edit(
        model=config.get("OPENAI_GENERAL", "image_edit_model", fallback="dall-e-2"),
        image=open(image_paths[0], "rb"),
        mask=open(image_paths[1], "rb"),
        prompt=edit_prompt,
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
        description=f"User Input:\n```{edit_prompt}```",
    )
    embed.set_image(url=f"attachment://{file_name}")

    # attach our file object
    file_upload = discord.File(path, filename=file_name)

    await ctx.send(file=file_upload, embed=embed)


@bot.event
async def on_command_error(ctx: Context, error: CommandError):
    """
    Bot event handler for a user command error.
    """

    if isinstance(error, CommandNotFound):
        # Not a command
        await ctx.send("This is not a supported command.")
        await ctx.invoke(bot.get_command("help"))

    elif isinstance(error, MissingRequiredArgument):
        # Missing required argument
        await ctx.send(f"Missing required argument: `<{error.param.name}>`")
        await ctx.invoke(bot.get_command("help"), ctx.command.name)

    elif isinstance(error, BadArgument):
        # Type error (gave int when expected string or the like)
        await ctx.send(
            "Invalid argument type. Please provide the correct type (string, integer, float, ...) of arguments."
        )
        await ctx.invoke(bot.get_command("help"), ctx.command.name)

    else:
        # Unknown error
        await ctx.send(f"An error occurred.\n```plaintext\n{error}\n```")


bot.run(os.getenv("DISCORD_BOT_KEY"))
