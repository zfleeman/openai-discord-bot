"""
Functions to work with the database
"""

import os
from datetime import datetime
from typing import Union

from cryptography.fernet import Fernet
from sqlmodel import Field, Session, SQLModel, create_engine, select

SQLITE_FILE_NAME = "database.db"
SQLITE_URL = f"sqlite:///{SQLITE_FILE_NAME}"
engine = create_engine(SQLITE_URL)


class Key(SQLModel, table=True):
    guild_id: str = Field(default=None, primary_key=True)
    guild_name: str
    api_key: str


class Response(SQLModel, table=True):
    response_id: str = Field(default=None, primary_key=True)
    thread_name: str
    guild_id: str
    updated: datetime


def get_session():
    return Session(engine)


async def get_response_id(guild_id: str, thread_name: str) -> Union[str, None]:
    with get_session() as session:
        statement = select(Response).where(Response.guild_id == guild_id).where(Response.thread_name == thread_name)
        results = session.exec(statement=statement)
        response_record = results.one_or_none()

        return response_record.response_id if response_record else None


async def update_response(response_id: str, guild_id: str, thread_name: str) -> None:
    with get_session() as session:
        statement = select(Response).where(Response.guild_id == guild_id).where(Response.thread_name == thread_name)
        results = session.exec(statement=statement)
        response = results.one_or_none()

        if response:
            response.response_id = response_id
            response.updated = datetime.now()
            session.add(response)
            session.commit()
        else:
            entry = Response(response_id=response_id, thread_name=thread_name, guild_id=guild_id, updated=datetime.now())
            session.add(entry)
            session.commit()

    return


async def get_api_key(guild_id: str) -> str:
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
                db_entry = Key(guild_id=data_list[0], guild_name=data_list[1], api_key=data_list[2])
                db_session.add(db_entry)
        db_session.commit()
