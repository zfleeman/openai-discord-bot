from datetime import datetime

from openai import AsyncOpenAI
from sqlmodel import Field, Session, SQLModel, create_engine, select

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url)


def get_session():
    return Session(engine)


class Thread(SQLModel, table=True):
    id: str = Field(default=None, primary_key=True)
    guild_id: str
    name: str
    created_at: datetime


async def get_thread_id(guild_id: str, name: str, openai_client: AsyncOpenAI = AsyncOpenAI()) -> str:
    with get_session() as session:
        statement = select(Thread).where(Thread.name == name).where(Thread.guild_id == guild_id)
        results = session.exec(statement)
        thread_record = results.first()

        if not thread_record:
            thread = await openai_client.beta.threads.create()
            # new record
            thread_record = Thread(id=thread.id, guild_id=guild_id, name=name, created_at=datetime.now())
            session.add(thread_record)
            session.commit()

        return thread_record.id


if __name__ == "__main__":
    sqlite_file_name = "database.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, echo=True)
    SQLModel.metadata.create_all(engine)
