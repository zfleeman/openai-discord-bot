FROM python:3-alpine
RUN apk add --no-cache ffmpeg
RUN mkdir -p /usr/app/
WORKDIR /usr/app/
COPY requirements.txt .
ENV DISCORD_BOT_KEY=""
ENV OPENAI_API_KEY=""
RUN pip install -r requirements.txt
ENTRYPOINT ["python", "app.py"]