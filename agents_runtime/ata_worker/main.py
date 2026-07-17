"""Ata Worker - Cloud Run Job that generates meeting minutes.

Triggered by Cloud Scheduler every 10 minutes.
Scans Calendar events that ended 30±10 minutes ago, generates ata via LLM,
saves to Drive, notifies organizer via WhatsApp.

Idempotency: each event_id is processed at most once (tracked in ata_runs/).
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from tools.ata_helper import generate_ata_markdown, save_ata_to_drive, notify_organizer
from tools.google_calendar import list_events
from tools.google_gmail import search_messages, get_thread
from core.secrets import get_secret

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("ata_worker")

ATA_LOOKBACK_MIN = 30
ATA_LOOKBACK_WINDOW_MIN = 10
ATA_MAX_PER_RUN = 20


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return None
        return firestore.Client(project=project)
    except Exception:
        return None


def _already_processed(event_id: str) -> bool:
    db = _get_firestore()
    if db is None:
        return False
    try:
        docs = db.collection("ata_runs").where("event_id", "==", event_id).limit(1).stream()
        for doc in docs:
            return True
        return False
    except Exception:
        return False


def _mark_processed(event_id: str, status: str, drive_file_id: Optional[str] = None, notified: bool = False):
    db = _get_firestore()
    if db is None:
        return
    try:
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP
        db.collection("ata_runs").add({
            "event_id": event_id,
            "status": status,
            "drive_file_id": drive_file_id,
            "organizer_notified": notified,
            "run_at": SERVER_TIMESTAMP,
        })
    except Exception as e:
        logger.warning(f"Failed to mark processed: {e}")


async def find_recent_meetings() -> List[Dict[str, Any]]:
    """Find meetings that ended 30±10 minutes ago."""
    now = datetime.now(timezone.utc)
    brt_offset = timedelta(hours=-3)
    now_brt = now + brt_offset
    window_start_brt = now_brt - timedelta(minutes=ATA_LOOKBACK_MIN + ATA_LOOKBACK_WINDOW_MIN)
    window_end_brt = now_brt - timedelta(minutes=ATA_LOOKBACK_MIN - ATA_LOOKBACK_WINDOW_MIN)

    result = await list_events(
        time_min=window_start_brt.isoformat(),
        time_max=window_end_brt.isoformat(),
        max_results=ATA_MAX_PER_RUN,
    )

    events = result.get("events", [])
    return [e for e in events if e.get("id") and not _already_processed(e["id"])]


async def find_event_thread(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find Gmail thread related to the event."""
    event_title = event.get("summary", "")
    event_date = event.get("start", "")[:10]
    query = f'subject:"{event_title}" OR from:me after:{event_date}'
    result = await search_messages(query, max_results=10)
    messages = result.get("messages", [])

    if not messages:
        return []

    first_msg = messages[0]
    thread_id = first_msg.get("thread_id")
    if not thread_id:
        return messages

    thread_result = await get_thread(thread_id)
    return thread_result.get("messages", [])


async def generate_ata_via_llm(event: Dict[str, Any], emails: List[Dict[str, Any]]) -> str:
    """Generate ata markdown using LLM."""
    system_prompt = (
        "Voce gera atas de reuniao profissionais em portugues brasileiro. "
        "Use tom objetivo, listas claras, identificando decisoes e proximos passos. "
        "NAO invente informacoes - use apenas o que foi fornecido. "
        "Se informacoes estiverem incompletas, escreva '(pendente)'."
    )

    event_info = (
        f"Titulo: {event.get('summary', 'N/A')}\n"
        f"Data/Hora: {event.get('start', 'N/A')} - {event.get('end', 'N/A')}\n"
        f"Participantes: {', '.join(event.get('attendees', []))}\n"
        f"Descricao: {event.get('description', '(sem descricao)')}\n"
    )

    emails_summary = "Nenhuma mensagem na thread."
    if emails:
        emails_summary = "\n\n".join([
            f"De: {e.get('from', 'unknown')}\nData: {e.get('date', 'N/A')}\n{e.get('body', '')[:500]}"
            for e in emails[:10]
        ])

    user_prompt = (
        f"=== EVENTO ===\n{event_info}\n\n"
        f"=== MENSAGENS RELACIONADAS ===\n{emails_summary}\n\n"
        "Gere uma ata em markdown com secoes: "
        "# Titulo | ## Data e Participantes | ## Pauta | ## Discussao | ## Decisoes | ## Proximos Passos"
    )

    llm = LLMProvider()
    if not llm.is_available():
        logger.warning("LLM not available, falling back to template")
        return await generate_ata_markdown(event, emails)

    try:
        result = await llm.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="deepseek-v4-pro",
            temperature=0.3,
            max_tokens=2500,
            thinking_disabled=False,
        )
        return result["content"]
    except LLMError as e:
        logger.error(f"LLM failed: {e}, falling back to template")
        return await generate_ata_markdown(event, emails)


async def extract_organizer_email(event: Dict[str, Any]) -> Optional[str]:
    """Extract organizer email from event attendees."""
    attendees = event.get("attendees", [])
    if not attendees:
        return None
    if attendees:
        return attendees[0]
    return None


async def process_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single meeting: generate ata, save, notify."""
    event_id = event.get("id", "unknown")
    logger.info(f"Processing event {event_id}: {event.get('summary', '')}")

    try:
        emails = await find_event_thread(event)

        ata_markdown = await generate_ata_via_llm(event, emails)
        ata_markdown = mask_pii(ata_markdown)

        save_result = await save_ata_to_drive(event, ata_markdown)
        if "error" in save_result:
            logger.error(f"Failed to save ata: {save_result['error']}")
            _mark_processed(event_id, "save_failed")
            return {"event_id": event_id, "status": "save_failed"}

        drive_file = save_result.get("file", {})
        drive_link = drive_file.get("web_view_link", "")

        organizer_email = await extract_organizer_email(event)
        notified = False
        if organizer_email:
            summary = ata_markdown[:500]
            notify_result = await notify_organizer(
                organizer_email, event.get("summary", "Reuniao"), drive_link, summary
            )
            notified = "message" in notify_result

        _mark_processed(
            event_id,
            "completed",
            drive_file_id=drive_file.get("id"),
            notified=notified,
        )
        return {
            "event_id": event_id,
            "status": "completed",
            "drive_file_id": drive_file.get("id"),
            "drive_link": drive_link,
            "notified": notified,
        }
    except Exception as e:
        logger.exception(f"Error processing event {event_id}")
        _mark_processed(event_id, "error")
        return {"event_id": event_id, "status": "error", "error": str(e)}


async def main():
    """Main entry point for Cloud Run Job."""
    logger.info("Ata Worker starting...")

    events = await find_recent_meetings()
    logger.info(f"Found {len(events)} events to process")

    results = []
    for event in events:
        result = await process_event(event)
        results.append(result)
        logger.info(f"Result: {result}")

    logger.info(f"Ata Worker done. Processed {len(results)} events.")
    return {"processed": len(results), "results": results}


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(main())
    print(json.dumps(result, indent=2))