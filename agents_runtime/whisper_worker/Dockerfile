FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app

ENV PYTHONUNBUFFERED=1 LOG_LEVEL=INFO WHISPER_MODEL=base WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16

CMD exec python3 main.py
