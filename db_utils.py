"""
Functions to work with the database
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional, Union

from cryptography.fernet import Fernet
from discord import Interaction
from sqlmodel import JSON, Column, Field, Session, SQLModel, create_engine, select

SQLITE_FILE_NAME = "database.db"
SQLITE_URL = f"sqlite:///{SQLITE_FILE_NAME}"
engine = create_engine(SQLITE_URL)


class CommandContext(SQLModel, table=True):
    """
    Table for storing information about the command interaction
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    guild_id: int = Field(index=True)
    user_id: int = Field(index=True)
    user: str
    command_name: str
    timestamp: datetime = Field(default_factory=datetime.now)
    params: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    async def save(self) -> bool:
        with get_session() as session:
            session.add(self)
            session.commit()
        return True


class Key(SQLModel, table=True):
    """
    Table for storing OpenAI API keys.
    """

    guild_id: int = Field(default=None, primary_key=True)
    guild_name: str
    api_key: str


class Chat(SQLModel, table=True):
    """
    Table for storing OpenAI Response IDs
    """

    response_id: str = Field(default=None, primary_key=True)
    topic: str
    guild_id: int
    updated: datetime


async def create_command_context(interaction: Interaction, **kwargs) -> CommandContext:
    """
    Helper function to create CommandContext entry.
    """
    context = CommandContext(
        guild_id=interaction.guild_id,
        user_id=interaction.user.id,
        user=interaction.user.name,
        command_name=interaction.command.name,
        **kwargs,
    )

    return context


def get_session() -> Session:
    """
    Returns a database session for queries 'n' things.
    """
    return Session(engine)


async def get_response_id(context: CommandContext) -> Union[str, None]:
    """
    Looks for a previous reponse id if one exists for a given "command" in the Chat table
    """
    with get_session() as session:
        statement = (
            select(Chat).where(Chat.guild_id == context.guild_id).where(Chat.topic == context.params.get("topic"))
        )
        results = session.exec(statement=statement)
        response_record = results.one_or_none()

        return response_record.response_id if response_record else None


async def update_chat(response_id: str, context: CommandContext) -> None:
    """
    Update the command's record in the Chat table.
    """
    with get_session() as session:
        statement = (
            select(Chat).where(Chat.guild_id == context.guild_id).where(Chat.topic == context.params.get("topic"))
        )
        results = session.exec(statement=statement)
        response = results.one_or_none()

        if response:
            response.response_id = response_id
            response.updated = datetime.now()
            session.add(response)
            session.commit()
        else:
            entry = Chat(
                response_id=response_id,
                topic=context.params.get("topic"),
                guild_id=context.guild_id,
                updated=datetime.now(),
            )
            session.add(entry)
            session.commit()

    return


async def get_api_key(guild_id: int) -> str:
    """
    Retrieve the top-secret API key from the incredibly secure database.
    """
    fernet_key = os.getenv("FERNET_KEY")
    if not fernet_key:
        raise ValueError("FERNET_KEY environment variable not set!")

    cipher = Fernet(fernet_key.encode())

    with get_session() as session:
        statement = select(Key).where(Key.guild_id == guild_id)
        results = session.exec(statement=statement)
        key_record = results.first()

        if not key_record:
            raise ValueError(f"No API token found for guild_id: {guild_id}")

        return cipher.decrypt(key_record.api_key.encode()).decode()


if __name__ == "__main__":
    SQLModel.metadata.create_all(engine)

    with get_session() as db_session:
        with open("encrypted_api_keys.txt", mode="r", encoding="UTF-8") as f:
            rows = f.readlines()
            for row in rows:
                data_list = row.split(",")
                db_entry = Key(guild_id=int(data_list[0]), guild_name=data_list[1], api_key=data_list[2])
                db_session.add(db_entry)
        db_session.commit()
