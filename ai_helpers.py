import json
from configparser import ConfigParser
from datetime import datetime
from typing import Union, Tuple
from pathlib import Path

import ffmpeg
from PIL import Image

from db_utils import get_thread_id
from openai import AsyncOpenAI


# OpenAI Client
client = AsyncOpenAI()


def get_config():
    config = ConfigParser()
    config.read("config.ini")
    return config


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


async def generate_speech(guild_id: str, compartment: str, file_name: str, tts: str) -> Path:
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


async def speak_and_spell(
    thread_name: str, prompt: str, guild_id: str, compartment: str = "default"
) -> Tuple[str, Path]:
    response = await new_thread_response(thread_name=thread_name, prompt=prompt, guild_id=guild_id)
    tts = response.content[0].text.value
    file_path = await generate_speech(
        guild_id=guild_id, compartment=compartment, tts=tts, file_name=f"{response.id}.wav"
    )

    return tts, file_path


async def gs_intro_song(guild_id: str, name: str):
    config = get_config()
    name = f"{name}_theme"

    prompt = config.get("PROMPTS", name)

    tts, file_path = await speak_and_spell(thread_name="gs_host", prompt=prompt, guild_id=guild_id, compartment="theme")

    # ffmpeg work to combine streams
    ## load both audio files
    theme_song = ffmpeg.input("gameshow.mp3").audio
    words = ffmpeg.input(file_path).audio

    ## adjust volumes
    theme_song = theme_song.filter("volume", 0.25)
    words = words.filter("volume", 3)

    ## merge and output
    dt_string = datetime.now().strftime("%Y%m%d%H%M%S")
    ouput_file = content_path(guild_id=guild_id, compartment="theme", file_name=f"intro_{dt_string}.wav")
    merged_audio = ffmpeg.filter((theme_song, words), "amix")
    out = ffmpeg.output(merged_audio, str(ouput_file)).overwrite_output()
    out.run(quiet=True)

    return tts, ouput_file


async def would_you_rather(guild_id: str, topic: str):
    config = get_config()
    thread_name = f"rather_{topic}"

    new_hypothetical_prompt = config.get("PROMPTS", "new_hypothetical")

    return await speak_and_spell(
        thread_name=thread_name, prompt=new_hypothetical_prompt, guild_id=guild_id, compartment="rather"
    )


async def nonsense_talk(guild_id: str):
    config = get_config()
    prompt = config.get("PROMPTS", "nonsense_talk", fallback="Let's hear it.")

    return await speak_and_spell(
        thread_name="nonsense_talk", prompt=prompt, compartment="nonsense_talk", guild_id=guild_id
    )


async def get_trivia_question(guild_id: str) -> dict:
    config = get_config()
    trivia_prompt = config.get("PROMPTS", "trivia_game")

    response = await new_thread_response(
        thread_name="trivia_game", prompt=trivia_prompt, guild_id=guild_id, response_format={"type": "json_object"}
    )

    text_json = response.content[0].text.value
    response_dict = json.loads(text_json)

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
