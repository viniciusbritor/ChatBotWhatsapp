"""Proactive Worker - generates proactive messages based on Calendar + topics.

Triggered by Cloud Scheduler:
- Every 15 minutes: scan upcoming Calendar events (1h, 3h before)
- Daily 8h BRT (Tue+Fri): scan relevant topics based on conversation history

Applies 8-layer anti-spam (core.proactive_gate) before sending.
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from core.proactive_gate import (
    check,
    is_dry_run,
    record_sent,
    is_prohibited_template,
)
from tools.google_calendar import list_events
from core.secrets import get_secret

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("proactive_worker")

WHATSAPP_AGENTE_URL = os.getenv("WHATSAPP_AGENTE_URL") or get_secret("WHATSAPP_AGENTE_URL")
WHATSAPP_AGENTE_SA_TOKEN = os.getenv("AGENTS_RUNTIME_SA_TOKEN") or get_secret("AGENTS_RUNTIME_SA_TOKEN")

PROACTIVE_RELEVANCE_MIN = 0.75
MAX_PROACTIVE_PER_RUN = 5


async def scan_upcoming_events() -> List[Dict[str, Any]]:
    """Scan Calendar for events in next 1h, 3h, 24h."""
    now = datetime.now(timezone.utc)
    brt_offset = timedelta(hours=-3)
    now_brt = now + brt_offset

    windows = [
        ("1h", now_brt, now_brt + timedelta(hours=1)),
        ("3h", now_brt + timedelta(hours=1), now_brt + timedelta(hours=3)),
        ("24h", now_brt + timedelta(hours=3), now_brt + timedelta(hours=24)),
    ]

    candidates = []
    for label, start, end in windows:
        result = await list_events(
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            max_results=20,
        )
        for event in result.get("events", []):
            candidates.append({
                "trigger": f"calendar_{label}",
                "event": event,
                "relevance_score": 0.85,
            })

    return candidates


def generate_event_message(event: Dict[str, Any], window: str) -> str:
    """Generate a motivational message for an upcoming event."""
    title = event.get("summary", "Reuniao")
    if window == "1h":
        return f"Sua reuniao '{title}' comeca em 1h. Confia no que voce preparou - vai dar bom!"
    elif window == "3h":
        return f"Lembrete: '{title}' em 3h. Bom momento pra revisar seus pontos."
    elif window == "24h":
        return f"Amanha tem '{title}'. Quer que eu prepare algo (pauta, contexto, links)?"
    return f"Lembrete: '{title}' em breve."


async def score_relevance_with_llm(message: str, context: str) -> float:
    """Score message relevance using LLM (0-1)."""
    llm = LLMProvider()
    if not llm.is_available():
        return 0.85

    try:
        result = llm.chat(
            system_prompt=(
                "Voce avalia a relevancia de uma mensagem proativa para o usuario. "
                "Responda APENAS com um JSON: {\"score\": 0.X, \"reason\": \"...\"}"
            ),
            user_prompt=(
                f"Contexto: {context}\n\n"
                f"Mensagem: {message}\n\n"
                "Esta mensagem e relevante? Score de 0 a 1."
            ),
            model="deepseek-v4-flash",
            temperature=0.2,
            max_tokens=100,
            json_mode=True,
        )
        content = result["content"]
        try:
            import re
            match = re.search(r'\"score\":\s*([\d.]+)', content)
            if match:
                score = float(match.group(1))
                return max(0.0, min(1.0, score))
        except Exception:
            pass
        return 0.85
    except LLMError:
        return 0.85


def _get_contact_state(phone: str) -> Dict[str, Any]:
    """Get contact state from Firestore (best effort)."""
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return {}
        db = firestore.Client(project=project)
        doc = db.collection("contatos").document(phone).get()
        if doc.exists:
            return doc.to_dict()
    except Exception:
        pass
    return {}


async def send_proactive_message(phone: str, message: str, trigger: str, instance: str = "jennifer") -> bool:
    """Send a proactive message via WhatsappAgente /send endpoint."""
    if is_dry_run():
        logger.info(f"DRY-RUN: Would send to {phone}: {message[:60]}")
        return False

    if not WHATSAPP_AGENTE_URL or not WHATSAPP_AGENTE_SA_TOKEN:
        logger.error("WhatsappAgente not configured")
        return False

    delay_ms = int(len(message.split()) * 600)
    delay_ms = min(delay_ms, 15000)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WHATSAPP_AGENTE_URL.rstrip('/')}/send",
                json={
                    "phone": phone,
                    "text": message,
                    "instance": instance,
                    "delay_ms": delay_ms,
                },
                headers={
                    "Authorization": f"Bearer {WHATSAPP_AGENTE_SA_TOKEN}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                record_sent(phone)
                logger.info(f"Proactive sent to {phone} (trigger={trigger})")
                return True
            logger.warning(f"Send failed: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Send exception: {e}")
        return False


async def process_candidate(candidate: Dict[str, Any]) -> bool:
    """Process a single proactive candidate."""
    trigger = candidate["trigger"]
    relevance = candidate.get("relevance_score", 0.85)

    if "event" in candidate:
        event = candidate["event"]
        window = trigger.replace("calendar_", "")
        message = generate_event_message(event, window)
        phone = event.get("attendees", [None])[0] if event.get("attendees") else "+5511966830020"

        if not phone:
            return False

        if is_prohibited_template(message):
            logger.warning(f"Prohibited template blocked: {message[:60]}")
            return False

        contact_state = _get_contact_state(phone)
        is_group = bool(event.get("group_jid"))
        allowed, reason = check(
            phone=phone,
            group_jid=event.get("group_jid"),
            is_group_member=True,
            contact_state=contact_state,
            relevance_score=relevance,
        )

        if not allowed:
            logger.info(f"Proactive blocked ({reason}): {phone}")
            return False

        return await send_proactive_message(phone, message, trigger)

    return False


async def run_events_scan() -> Dict[str, Any]:
    """Run the upcoming events scan."""
    candidates = await scan_upcoming_events()
    logger.info(f"Found {len(candidates)} upcoming event candidates")

    sent = 0
    blocked = 0
    for candidate in candidates[:MAX_PROACTIVE_PER_RUN]:
        if await process_candidate(candidate):
            sent += 1
        else:
            blocked += 1

    return {
        "candidates": len(candidates),
        "sent": sent,
        "blocked": blocked,
    }


async def main():
    logger.info("Proactive Worker starting (events scan mode)...")
    result = await run_events_scan()
    logger.info(f"Proactive Worker done: {result}")
    return result


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(main())
    print(json.dumps(result, indent=2))