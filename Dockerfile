FROM python:3-alpine
RUN mkdir -p /usr/src/app/
WORKDIR /usr/app/
COPY requirements.txt .
ENV TZ="America/Denver"
RUN pip install -r requirements.txt
ENTRYPOINT ["python", "app.py"]