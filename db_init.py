from sqlmodel import SQLModel, create_engine
from openai import OpenAI

client = OpenAI()

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=True)


if __name__ == "__main__":
    SQLModel.metadata.create_all(engine)
