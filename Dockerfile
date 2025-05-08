FROM python:3-alpine
RUN apk add --no-cache ffmpeg
RUN mkdir -p /usr/src/app/
WORKDIR /usr/src/app/
COPY requirements.txt .
ENV TZ="America/Denver"
RUN pip install -r requirements.txt
ENTRYPOINT ["python", "app.py"]