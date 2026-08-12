"""Pipeline de transcrição de áudio compartilhado entre /chat e /pubsub/push.

A transcrição real (MiniMax primário + Gemini fallback, com guarda SSRF no
download via URL da Evolution) fica em ``core.audio_transcribe``. Este módulo
resolve o payload do envelope (``has_audio`` + ``audio_base64``/``audio_url``)
em texto transcrito, para que o caminho de produção (/webhook → Pub/Sub →
orquestrador) NÃO entregue ``[audio]`` direto ao LLM (que é texto puro e não
transcreve).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from core.masker import mask_pii

logger = logging.getLogger(__name__)


async def transcribe_envelope_audio(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Transcreve o áudio do envelope quando ``extra.has_audio`` é verdadeiro.

    Retorna:
      - ``{"transcript": None}``         — payload sem áudio.
      - ``{"transcript": str, ...}``     — sucesso.
      - ``{"error": str}``               — falha (código curto).
    """
    extra = payload.get("extra") or {}
    if not extra.get("has_audio"):
        return {"transcript": None}

    from core.audio_transcribe import transcribe_base64, transcribe_url

    mimetype = extra.get("audio_mimetype", "audio/ogg")
    instance = payload.get("instance", "Jennifer")
    try:
        if extra.get("audio_base64"):
            result = await transcribe_base64(extra["audio_base64"], mimetype, instance=instance)
            source = "base64"
        elif extra.get("audio_url"):
            result = await transcribe_url(extra["audio_url"], mimetype, instance=instance)
            source = "url"
        else:
            return {"error": "audio_payload_missing"}
    except (ValueError, RuntimeError) as exc:
        logger.warning("audio_transcription_rejected code=%s", exc)
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.error("audio_transcription_failed type=%s", type(exc).__name__)
        return {"error": f"unavailable:{type(exc).__name__}"}

    transcript = result.get("transcript") or ""
    logger.info(
        "Audio transcribed: source=%s provider=%s chars=%s",
        source,
        result.get("provider", "minimax:MiniMax-M3"),
        len(transcript),
    )
    return {
        "transcript": mask_pii(transcript),
        "provider": result.get("provider", "minimax:MiniMax-M3"),
        "reason": result.get("reason", ""),
        "source": source,
    }
