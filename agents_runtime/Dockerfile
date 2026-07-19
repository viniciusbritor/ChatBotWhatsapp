FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/whisper_models && python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8', download_root='/app/whisper_models')"

COPY . /app

ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    ENVIRONMENT=test \
    PORT=8080 \
    TZ=America/Sao_Paulo \
    WHISPER_DOWNLOAD_ROOT=/app/whisper_models \
    WHISPER_MODEL=base \
    WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8 \
    AUDIO_MAX_BYTES=26214400 \
    AUDIO_MAX_DURATION_SEC=300 \
    AUDIO_DOWNLOAD_TIMEOUT_SEC=30 \
    AUDIO_URL_ALLOWED_HOSTS=evolution.coherenceai.com.br

EXPOSE 8080

CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1