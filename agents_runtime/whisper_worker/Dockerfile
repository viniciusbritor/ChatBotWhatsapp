FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    WHISPER_MODEL=base \
    WHISPER_DEVICE=cuda \
    WHISPER_COMPUTE_TYPE=float16

CMD exec python3 main.py
