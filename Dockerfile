FROM python:3-alpine
RUN mkdir -p /usr/app/
WORKDIR /usr/app/
COPY requirements.txt .
ENV DISCORD_BOT_KEY=""
ENV FERNET_KEY=""
RUN pip install -r requirements.txt
ENTRYPOINT ["python", "app.py"]