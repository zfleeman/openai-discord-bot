"""
Helper functions that interact with OpenAI
"""

from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from typing import Tuple

from openai import AsyncOpenAI
from openai.types.responses import Response

from db_utils import get_api_key, get_response_id, update_response


def get_config():
    config = ConfigParser()
    config.read("config.ini")
    return config


async def get_openai_client(guild_id: str) -> AsyncOpenAI:
    """
    Each guild is assigned an API key
    """
    api_key = await get_api_key(guild_id=guild_id)
    openai_client = AsyncOpenAI(api_key=api_key)

    return openai_client


async def new_response(discord_id: str, name: str, prompt: str, openai_client: AsyncOpenAI) -> Response:
    config = get_config()

    previous_response_id = await get_response_id(discord_id=discord_id, name=name)

    instructions = config.get("OPENAI_INSTRUCTIONS", name)
    response = await openai_client.responses.create(
        input=prompt, model="gpt-4o", instructions=instructions, previous_response_id=previous_response_id
    )

    await update_response(response_id=response.id, discord_id=discord_id, name=name)

    return response


async def generate_speech(
    guild_id: str, compartment: str, file_name: str, tts: str, openai_client: AsyncOpenAI = AsyncOpenAI()
) -> Path:
    config = get_config()
    async with openai_client.audio.speech.with_streaming_response.create(
        model=config.get("OPENAI_GENERAL", "speech_model", fallback="tts-1"),
        voice=config.get("OPENAI_GENERAL", "voice", fallback="onyx"),
        input=tts,
        response_format=config.get("OPENAI_GENERAL", "speech_file_format", fallback="wav"),
    ) as speech:
        file_path = content_path(guild_id=guild_id, compartment=compartment, file_name=file_name)
        await speech.stream_to_file(file_path)

    return file_path


async def speak_and_spell(
    thread_name: str,
    prompt: str,
    guild_id: str,
    compartment: str = "default",
    openai_client: AsyncOpenAI = AsyncOpenAI(),
) -> Tuple[str, Path]:
    response = await new_response(
        discord_id=guild_id,
        name=thread_name,
        prompt=prompt,
        openai_client=openai_client,
    )

    tts = response.output_text

    file_path = await generate_speech(
        guild_id=guild_id, compartment=compartment, tts=tts, file_name=f"{response.id}.wav", openai_client=openai_client
    )

    return tts, file_path


def content_path(guild_id: str, compartment: str, file_name: str):
    config = get_config()
    ts = datetime.now().strftime(config.get("GENERAL", "session_strftime", fallback="dall-e-2"))
    dir_path = Path(f"generated_content/guild_{guild_id}/{ts}/{compartment}")
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / file_name


def dict_to_ordered_string(data: dict) -> str:
    # Sort the dictionary items by value in descending order
    sorted_items = sorted(data.items(), key=lambda item: item[1], reverse=True)

    # Format the sorted items into a numbered list
    formatted_string = "\n".join([f"{i+1}. **{key}**: {value}" for i, (key, value) in enumerate(sorted_items)])

    return formatted_string
