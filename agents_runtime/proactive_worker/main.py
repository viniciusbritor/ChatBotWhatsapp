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


def _known_phones() -> List[str]:
    """Resolve phones to iterate in this run (Fase D)."""
    env_phones = os.getenv("PROACTIVE_WORKER_PHONES")
    if env_phones:
        return [p.strip() for p in env_phones.split(",") if p.strip()]
    return []


async def scan_upcoming_events(phone: str) -> List[Dict[str, Any]]:
    """Scan Calendar for events in next 1h, 3h, 24h for the given user."""
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
            phone,
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            max_results=20,
        )
        for event in result.get("events", []):
            candidates.append({
                "trigger": f"calendar_{label}",
                "event": event,
                "phone": phone,
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
        result = await llm.chat(
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
    """Run the upcoming events scan across known users (Fase D)."""
    phones = _known_phones()
    if not phones:
        logger.info("No phones configured for proactive worker (PROACTIVE_WORKER_PHONES)")
        return {"candidates": 0, "sent": 0, "blocked": 0, "users": 0}

    all_candidates: List[Dict[str, Any]] = []
    for phone in phones:
        try:
            user_candidates = await scan_upcoming_events(phone)
            all_candidates.extend(user_candidates)
        except Exception:
            logger.exception(f"scan_upcoming_events failed for {phone}")

    logger.info(f"Found {len(all_candidates)} upcoming event candidates across {len(phones)} users")

    sent = 0
    blocked = 0
    for candidate in all_candidates[:MAX_PROACTIVE_PER_RUN]:
        if await process_candidate(candidate):
            sent += 1
        else:
            blocked += 1

    return {
        "candidates": len(all_candidates),
        "sent": sent,
        "blocked": blocked,
        "users": len(phones),
    }


async def _get_eligible_contacts() -> List[Dict[str, Any]]:
    """Get contacts eligible for proactive topics messages."""
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return []
        db = firestore.Client(project=project)
        docs = db.collection("contatos").where("opted_in", "==", True).stream()
        contacts = []
        for doc in docs:
            data = doc.to_dict()
            phone = data.get("phone", doc.id)
            if data.get("proactive_mode", "normal") not in ("off", "zen"):
                contacts.append({"phone": phone, **data})
        return contacts
    except Exception as e:
        logger.warning(f"Failed to get contacts: {e}")
        return []


async def _get_recent_history(phone: str, limit: int = 10) -> str:
    """Get recent chat history for a contact."""
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return ""
        db = firestore.Client(project=project)
        docs = (
            db.collection("contatos").document(phone)
            .collection("historico")
            .order_by("ts", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        messages = []
        for d in docs:
            data = d.to_dict()
            direction = data.get("direction", "in")
            text = data.get("text", "")[:100]
            name = data.get("sender_name", "")
            prefix = name if direction == "in" else "Jennifer"
            messages.append(f"{prefix}: {text}")
        return "\n".join(reversed(messages))
    except Exception:
        return ""


async def _generate_topic_message(contact: Dict[str, Any], history: str) -> Optional[Dict[str, Any]]:
    """Generate a contextual proactive message using LLM."""
    phone = contact.get("phone", "")
    display_name = contact.get("display_name", contact.get("preferred_name", ""))

    llm = LLMProvider()
    if not llm.is_available():
        return None

    system_prompt = (
        "Voce e o agente de proatividade da Jennifer. Analise o historico recente do usuario "
        "e sugira UMA mensagem proativa curta (max 2 linhas) que traga valor real:\n"
        "- Se houver assunto pendente: lembre gentilmente\n"
        "- Se houver interesse em topico: compartilhe algo relevante\n"
        "- Se conversa parada ha dias: 'Saudades! Como vao as coisas?'\n"
        "- Nunca pergunte 'tudo bem?' generico\n"
        "- Tom: amigavel, profissional, caloroso\n"
        "- JAMAIS faca spam, venda, ou pressione\n"
        "- Se nao houver contexto relevante, responda exatamente: SKIP\n"
        "Responda APENAS com JSON: {\"message\": \"...\", \"relevance\": 0.X, \"topic\": \"...\"}"
    )

    user_prompt = (
        f"Contato: {display_name} ({phone})\n"
        f"Historico recente:\n{history or '(sem historico)'}\n\n"
        "Qual mensagem proativa voce sugere?"
    )

    try:
        result = await llm.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="deepseek-v4-flash",
            temperature=0.7,
            max_tokens=200,
            json_mode=True,
        )
        content = result.get("content", "")
        if "SKIP" in content.upper():
            return None
        import re
        msg_match = re.search(r'"message":\s*"([^"]+)"', content)
        rel_match = re.search(r'"relevance":\s*([\d.]+)', content)
        topic_match = re.search(r'"topic":\s*"([^"]+)"', content)
        if msg_match:
            return {
                "message": msg_match.group(1),
                "relevance": float(rel_match.group(1)) if rel_match else 0.7,
                "topic": topic_match.group(1) if topic_match else "conversation",
                "phone": phone,
                "trigger": "topics_scan",
            }
    except Exception as e:
        logger.warning(f"Topic generation failed for {phone}: {e}")
    return None


async def run_topics_scan() -> Dict[str, Any]:
    """Run the topics-based proactive scan (Tue+Fri 8h BRT)."""
    contacts = await _get_eligible_contacts()
    logger.info(f"Topics scan: {len(contacts)} eligible contacts")

    sent = 0
    blocked = 0
    skipped = 0

    for contact in contacts[:MAX_PROACTIVE_PER_RUN * 2]:
        phone = contact.get("phone", "")
        history = await _get_recent_history(phone, limit=8)
        candidate = await _generate_topic_message(contact, history)
        if not candidate:
            skipped += 1
            continue

        if is_prohibited_template(candidate["message"]):
            blocked += 1
            continue

        contact_state = _get_contact_state(phone)
        allowed, reason = check(
            phone=phone,
            group_jid=None,
            is_group_member=False,
            contact_state=contact_state,
            relevance_score=candidate.get("relevance", 0.7),
        )
        if not allowed:
            logger.info(f"Topic blocked ({reason}): {phone}")
            blocked += 1
            continue

        success = await send_proactive_message(
            phone=phone,
            message=candidate["message"],
            trigger="topics_scan",
        )
        if success:
            sent += 1
        else:
            blocked += 1

    return {
        "candidates": len(contacts),
        "sent": sent,
        "blocked": blocked,
        "skipped": skipped,
    }


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["events", "topics", "all"], default="events")
    args, _ = parser.parse_known_args()
    logger.info(f"Proactive Worker starting (mode={args.mode})...")
    if args.mode == "topics":
        result = await run_topics_scan()
    elif args.mode == "all":
        events_result = await run_events_scan()
        topics_result = await run_topics_scan()
        result = {"events": events_result, "topics": topics_result}
    else:
        result = await run_events_scan()
    logger.info(f"Proactive Worker done: {result}")
    return result


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(main())
    print(json.dumps(result, indent=2))
