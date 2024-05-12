from datetime import datetime

from openai import OpenAI
from sqlmodel import Field, SQLModel, create_engine, Session, select, Relationship

from configuration import get_config


sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url)


def get_session():
    return Session(engine)


class Thread(SQLModel, table=True):
    id: str = Field(default=None, primary_key=True)
    guild_id: str
    name: str
    created_at: datetime = datetime.now()
    assistants: list["Assistant"] = Relationship(back_populates="thread")


class Assistant(SQLModel, table=True):
    id: str = Field(default=None, primary_key=True)
    guild_id: str
    name: str
    created_at: datetime = datetime.now()
    thread_id: str | None = Field(default=None, foreign_key="thread.id")
    thread: Thread | None = Relationship(back_populates="assistants")


def get_thread(guild_id: str, name: str, assistant_id: str, client: OpenAI = OpenAI()):
    with get_session() as session:
        statement = select(Thread).where(Thread.name == name).where(Thread.guild_id == guild_id)
        results = session.exec(statement)
        thread_record = results.first()
        assistant_record = get_assistant_record_by_id(assistant_id=assistant_id)

        if thread_record:
            thread = client.beta.threads.retrieve(thread_id=thread_record.id)
        else:
            thread = client.beta.threads.create()
            # new record
            thread_entry = Thread(id=thread.id, guild_id=guild_id, name=name)
            session.add(thread_entry)
            session.commit()

        if not assistant_record.thread_id:
            assistant_record.thread_id = thread.id
            session.add(assistant_record)
            session.commit()

        return thread


def get_assistant_by_name(guild_id: str, name: str, client: OpenAI = OpenAI()):
    with get_session() as session:
        statement = select(Assistant).where(Assistant.guild_id == guild_id).where(Assistant.name == name)
        results = session.exec(statement)

        assistant_record = results.first()
        if assistant_record:
            assistant = client.beta.assistants.retrieve(assistant_id=assistant_record.id)
        else:
            config = get_config()
            assistant = client.beta.assistants.create(model=config.get("OPENAI", "chat_model"))
            assistant_entry = Assistant(id=assistant.id, guild_id=guild_id, name=name)
            session = get_session()
            session.add(assistant_entry)
            session.commit()

        return assistant


def get_assistant_record_by_id(assistant_id: str):
    with get_session() as session:
        statement = select(Assistant).where(Assistant.id == assistant_id)
        results = session.exec(statement)
        return results.first()


if __name__ == "__main__":
    sqlite_file_name = "database.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, echo=True)
    SQLModel.metadata.create_all(engine)
