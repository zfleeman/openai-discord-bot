"""
Helper functions that interact with OpenAI
"""

from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from openai import AsyncOpenAI
from openai.types.responses import Response

from db_utils import get_api_key, get_response_id, update_response


def get_config():
    """
    Read the configuration specified in the config ini
    """
    config = ConfigParser()
    config.read("config.ini")
    return config


async def get_openai_client(guild_id: str) -> AsyncOpenAI:
    """
    Return the guild-assigned API key
    """
    api_key = await get_api_key(guild_id=guild_id)
    openai_client = AsyncOpenAI(api_key=api_key)

    return openai_client


async def new_response(
    guild_id: str,
    command_name: str,
    prompt: str,
    openai_client: Optional[AsyncOpenAI] = None,
    model: str = "gpt-4o-mini",
) -> Response:
    """
    Generate a new response with the OpenAI Response API and store its ID
    """
    config = get_config()

    # command-specific models
    if command_name == "talk_quotes":
        model = "gpt-4o"

    if not openai_client:
        openai_client = await get_openai_client(guild_id=guild_id)

    previous_response_id = await get_response_id(guild_id=guild_id, command_name=command_name)

    instructions = config.get("OPENAI_INSTRUCTIONS", command_name)
    response = await openai_client.responses.create(
        input=prompt, model=model, instructions=instructions, previous_response_id=previous_response_id
    )

    await update_response(response_id=response.id, guild_id=guild_id, command_name=command_name)

    return response


async def generate_speech(
    guild_id: str, compartment: str, file_name: str, tts: str, openai_client: Optional[AsyncOpenAI] = None
) -> Path:
    """
    Use OpenAI's Speech API to create a text-to-speech audio file
    """
    config = get_config()

    if not openai_client:
        openai_client = await get_openai_client(guild_id=guild_id)

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
    command_name: str,
    prompt: str,
    guild_id: str,
    compartment: str = "default",
) -> Tuple[str, Path]:
    """
    Create a new response and WAV file in one nice function.
    """

    openai_client = await get_openai_client(guild_id=guild_id)

    response = await new_response(
        guild_id=guild_id, command_name=command_name, prompt=prompt, openai_client=openai_client
    )

    tts = response.output_text

    file_path = await generate_speech(
        guild_id=guild_id, compartment=compartment, tts=tts, file_name=f"{response.id}.wav", openai_client=openai_client
    )

    return tts, file_path


def content_path(guild_id: str, compartment: str, file_name: str) -> Path:
    """
    Create a path to store the content generated by OpenAI.
    """
    config = get_config()
    ts = datetime.now().strftime(config.get("GENERAL", "session_strftime", fallback="dall-e-2"))
    dir_path = Path(f"generated_content/guild_{guild_id}/{ts}/{compartment}")
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / file_name
