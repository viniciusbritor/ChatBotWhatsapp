"""Shim re-export for backward compatibility.

The audio transcription module lives in ``core/audio_transcribe.py``; older
seeds and external callers still import ``tools.audio_transcribe``. This
shim keeps both paths working without duplicating logic.
"""
from core.audio_transcribe import (  # noqa: F401
    AUDIO_MAX_BYTES,
    AUDIO_MAX_DURATION_SEC,
    AUDIO_URL_ALLOWED_HOSTS,
    transcribe_bytes,
    transcribe_base64,
    transcribe_url,
    fallback_stats,
)
