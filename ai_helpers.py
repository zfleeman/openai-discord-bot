"""
Helper functions that interact with OpenAI
"""

from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from openai import AsyncOpenAI
from openai.types.responses import Response

from db_utils import CommandContext, get_api_key, get_response_id, update_chat


def get_config():
    """
    Read the configuration specified in the config ini
    """
    config = ConfigParser()
    config.read("config.ini")
    return config


async def get_openai_client(guild_id: int) -> AsyncOpenAI:
    """
    Return the guild-assigned API key
    """
    api_key = await get_api_key(guild_id=guild_id)
    openai_client = AsyncOpenAI(api_key=api_key)

    return openai_client


async def new_response(
    context: CommandContext,
    prompt: str,
    openai_client: Optional[AsyncOpenAI] = None,
    model: str = "gpt-4o-mini",
) -> Response:
    """
    Generate a new response with the OpenAI Response API and store its ID
    """
    config = get_config()

    # topic-specific models
    if context.params.get("topic") == "talk_quotes":
        model = "gpt-4o"

    # use command-specified custom instructions --> for future commands
    instructions = context.params.get("custom_instructions") or config.get(
        "OPENAI_INSTRUCTIONS", context.params.get("topic")
    )

    # limit the response output to conform to Discord character limit
    max_output_tokens = config.getint("OPENAI_GENERAL", "max_output_tokens", fallback=500)

    if not openai_client:
        openai_client = await get_openai_client(guild_id=context.guild_id)

    previous_response_id = await get_response_id(context=context)

    response = await openai_client.responses.create(
        input=prompt,
        model=model,
        instructions=instructions,
        previous_response_id=previous_response_id,
        max_output_tokens=max_output_tokens,
    )

    await update_chat(response_id=response.id, context=context)

    return response


async def generate_speech(
    context: CommandContext,
    file_name: str,
    tts: str,
    voice: str = "onyx",
    openai_client: Optional[AsyncOpenAI] = None,
) -> Path:
    """
    Use OpenAI's Speech API to create a text-to-speech audio file
    """
    config = get_config()

    if not openai_client:
        openai_client = await get_openai_client(guild_id=context.guild_id)

    async with openai_client.audio.speech.with_streaming_response.create(
        model=config.get("OPENAI_GENERAL", "speech_model", fallback="tts-1"),
        voice=voice,
        input=tts,
        response_format=config.get("OPENAI_GENERAL", "speech_file_format", fallback="wav"),
    ) as speech:
        file_path = content_path(context=context, file_name=file_name)
        await speech.stream_to_file(file_path)

    return file_path


async def speak_and_spell(
    context: CommandContext,
    prompt: str,
) -> Tuple[str, Path]:
    """
    Create a new response and WAV file in one nice function.
    """
    openai_client = await get_openai_client(guild_id=context.guild_id)

    response = await new_response(context=context, prompt=prompt, openai_client=openai_client)

    tts = response.output_text

    file_path = await generate_speech(
        context=context, tts=tts, file_name=f"{response.id}.wav", openai_client=openai_client
    )

    return tts, file_path


def content_path(context: CommandContext, file_name: str) -> Path:
    """
    Create a path to store the content generated by OpenAI.
    """
    ts = datetime.now().strftime(format="%Y-%m-%d - %A")
    dir_path = Path(f"generated_content/guild_{context.guild_id}/{ts}/{context.command_name}")
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / file_name
