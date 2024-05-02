import ffmpeg
import os
import discord
from discord import FFmpegOpusAudio, Embed
from discord.ext import commands
from openai import OpenAI
from pathlib import Path
from datetime import datetime
import time
from openai import OpenAI
from openai.types.beta.assistant import Assistant
from db_utils import get_assistant_by_name, get_thread

# OpenAI Client
client = OpenAI()

# Bot Client
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command()
async def ttsjoin(ctx):
    if ctx.author.voice:
        voice = await ctx.author.voice.channel.connect()
    else:
        await ctx.send(f"{ctx.author} is not in a voice channel.")


@bot.command()
async def theme(ctx, game: str):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    tts, path = gs_intro_song(ctx.guild.id, game)
    source = FFmpegOpusAudio(path)
    player = voice.play(source)
    await ctx.send(tts)


@bot.command()
async def rather(ctx, arg1: str = "normal"):
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
async def quiz(ctx, arg1: str = ""):
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
async def say(ctx, arg1: str = ""):
    """
    say whatever somebody types
    :param arg1: string of quoted text to speak
    """
    if not arg1:
        await ctx.send("You need to type something in quotes after the command.")
        return
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    file_path = f"{ctx.guild.id}_{ts}_say.wav"
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    path = generate_speech(tts=arg1, file_path=file_path)
    source = FFmpegOpusAudio(path)
    player = voice.play(source)


@bot.command()
async def ttsleave(ctx):
    if ctx.voice_client:
        await ctx.guild.voice_client.disconnect()


@bot.command()
async def image(ctx, arg1: str, arg2: str = "dall-e-2"):

    image_response = client.images.generate(prompt=arg1, model=arg2)

    url = image_response.data[0].url
    revised_prompt = image_response.data[0].revised_prompt

    embed = Embed(title="B4NG AI Image Response", description=f"User Input:\n```{arg1}```")
    embed.set_image(url=url)
    embed.set_footer(text=f"Revised Prompt:\n{revised_prompt}")

    await ctx.send(embed=embed)


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
        time.sleep(0.5)

    messages = client.beta.threads.messages.list(thread_id=thread.id)

    # the most recent message in the thread is from the assistant
    response = messages.data[0]

    return response


def generate_speech(tts: str, file_path: str = "", voice: str = "onyx") -> str:

    if file_path not in os.listdir():

        with client.audio.speech.with_streaming_response.create(
            model="tts-1", voice=voice, input=tts, response_format="wav"
        ) as speech:
            speech.stream_to_file(file_path)

    return file_path


def gs_intro_song(guild_id: str, name: str, assistant_name="gs_host"):

    name = f"{name}_theme"

    assistant = get_assistant_by_name(guild_id=guild_id, name=assistant_name, client=client)

    # check if this is a new assistant
    if not assistant.instructions:
        assistant_instructions = "You are an assistant that has the personality of a 1970s game show host that is inebriated and sassy. Be as irreverant and mean as possible."
        assistant = client.beta.assistants.update(
            assistant_id=assistant.id, instructions=assistant_instructions, name=assistant_name
        )

    prompts = {
        "rather_theme": "Create a sarcastic, one-sentence intro to a game show that asks hypothetical questions to your stupid friends. The game show's title is made up each time. It is unlike any of the other titles that you have come up with. The game show's title has to do with the fact that this is a hypotetical question game show.",
        "quiz_theme": "Create a sarcastic, one-sentence intro to a game show that asks simple to complex quiz questions. The game show's title is made up each time. It is unlike any of the other titles that you have come up with. The game show's title has to do with the fact that this is a Trivial Pursuit-style quiz question show.",
    }

    # openai api work
    ## generate the show intro text
    response = new_response(assistant=assistant, prompt=prompts[name], guild_id=guild_id, thread_name=name)

    ## generate a speech wav
    file_path = Path(".").resolve() / f"{response.id}.wav"  # store each file in a session dir
    tts = response.content[0].text.value
    file_path = generate_speech(tts=tts, file_path=file_path)

    # ffmpeg work to combine streams
    ## load both audio files
    theme_song = ffmpeg.input("gameshow.mp3").audio  # find more game show intros
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

    assistant_name = f"rather_{topic}"

    instructions = {
        "sexy": "You are an assistant that provides sexually-suggestive, adult-themed hypothetical questions in the format of 'would you rather' that would spur interesting conversation in an online chat room.",
        "games": "You are an assistant that provides hypothetical questions in the form of 'would you rather' that involves video games from the late 1990s or early 2000s. Be specific about the game's title.",
        "fitness": "You are an assistant that provides hypothetical questions in the form of 'would you rather' that involve a physical feat or endurance test of some kind. This hypothetical should spur interesting conversation in an online chat room. Only ask the question.",
        "normal": "You are an assistant that provides hypothetical questions in the form of 'would you rather' that would spur interesting conversation in an online chat room.",
    }

    if topic not in instructions.keys():
        file_path = f"error_{topic}_.wav"
        tts = f"I do not know how to ask {topic} hypothetical questions."
        return tts, generate_speech(tts=tts, file_path=file_path)

    assistant = get_assistant_by_name(guild_id=guild_id, name=assistant_name, client=client)

    # check if this is a new assistant
    if not assistant.instructions:
        assistant_instructions = instructions[topic]
        assistant = client.beta.assistants.update(
            assistant_id=assistant.id, instructions=assistant_instructions, name=assistant_name
        )

    # TODO: replace with a config
    # new_hypothetical_prompt = "Ask me a new hypothetical question. Stick to your assistant instructions."
    new_hypothetical_prompt = """
        Ask me a new hypothetical question. The question should relate to your assistant instructions.
        Make sure it is completely unlike every other hypothetical question in this thread.
        The question should start an interesting conversation in a chat room.
    """

    # TODO: should new_response just go ahead and do speech? this is redundant for each game
    response = new_response(
        assistant=assistant, thread_name="rather", prompt=new_hypothetical_prompt, guild_id=guild_id
    )
    file_path = Path(".").resolve() / f"{response.id}.wav"  # store each file in a session dir
    tts = response.content[0].text.value
    file_path = generate_speech(tts=tts, file_path=file_path)

    return tts, file_path


def quiz(guild_id: str, qa: str = ""):

    assistant_name = f"quiz_{qa}"

    if qa == "question":
        assistant = get_assistant_by_name(guild_id=guild_id, name=assistant_name, client=client)
        assistant_instructions = "You are an assistant that asks Trivial Pursuit-style quiz questions that could stump the averge Jeopardy contestant. Make sure the question is at most two sentences long. Make it a tricky quesiton."
        prompt = "Ask me a new question."
    elif qa == "answer":
        assistant = get_assistant_by_name(guild_id=guild_id, name=assistant_name, client=client)
        assistant_instructions = "You are an assistant that answers questions as briefly as possible. Do not repeat the context of the question. Use one word or two to structure your answer if possible. After you provide the answer answer, provide a fun fact about the answer."
        prompt = "Answer the question that was just asked with one word or phrase. "
    else:
        return "That is not a valid input.", False

    # check if this is a new assistant
    if not assistant.instructions:
        assistant = client.beta.assistants.update(
            assistant_id=assistant.id, instructions=assistant_instructions, name=assistant_name
        )

    response = new_response(assistant=assistant, thread_name="quiz", prompt=prompt, guild_id=guild_id)
    file_path = Path(".").resolve() / f"{response.id}.wav"  # store each file in a session dir
    tts = response.content[0].text.value
    file_path = generate_speech(tts=tts, file_path=file_path)

    return tts, file_path


bot.run(os.getenv("DISCORD_BOT_KEY"))
