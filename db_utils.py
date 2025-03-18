"""
Functions to work with the database
"""

from datetime import datetime
from typing import Union

from sqlmodel import Field, Session, SQLModel, create_engine, select

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url)


def get_session():
    return Session(engine)


class Key(SQLModel, table=True):
    guild_id: str = Field(default=None, primary_key=True)
    api_key: str


class Response(SQLModel, table=True):
    response_id: str = Field(default=None, primary_key=True)
    name: str
    discord_id: str
    updated: datetime


async def get_response_id(discord_id: str, name: str) -> Union[str, None]:
    with get_session() as session:
        statement = select(Response).where(Response.discord_id == discord_id).where(Response.name == name)
        results = session.exec(statement=statement)
        response_record = results.first()

        return response_record.response_id


async def update_response(response_id: str, discord_id: str, name: str) -> None:
    with get_session() as session:
        statement = select(Response).where(Response.discord_id == discord_id).where(Response.name == name)
        results = session.exec(statement=statement)
        response = results.one_or_none()

        if response:
            response.response_id = response_id
            session.add(response)
            session.commit()
        else:
            entry = Response(response_id=response_id, name=name, discord_id=discord_id, updated=datetime.now())
            session.add(entry)
            session.commit()

    return


async def get_api_key(guild_id: str) -> str:
    with get_session() as session:
        statement = select(Key).where(Key.guild_id == guild_id)
        results = session.exec(statement=statement)
        key_record = results.first()

        if not key_record:
            raise ValueError(f"No API token found for guild_id: {guild_id}")

        return key_record.api_key


if __name__ == "__main__":
    sqlite_file_name = "database.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, echo=True)
    SQLModel.metadata.create_all(engine)
